"""API Gateway — public front door (like api.elevenlabs.io).
API key auth (hashed, Postgres) + rate limiting + reverse proxy to internal services.
Routes:
  /v1/tts*        -> tts-service
  /v1/stt*        -> stt-service
  /v1/sessions*   -> conversation-service
  /v1/calls*      -> telephony-service
  /v1/recordings* -> recording-service
  /v1/usage       -> analytics-service
Also: POST /admin/keys (create tenant API key — protect behind JWT in prod)."""
import hashlib, os, secrets, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, JSONResponse

app = FastAPI(title="api-gateway", version="1.0.0")

# Dev CORS so the admin dashboard (:3000) can call the /admin endpoints.
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)

# Admin panel password. If set, every /admin/* call must send header X-Admin-Password.
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

def check_admin(request: Request):
    if os.getenv("ALLOW_ADMIN", "true") != "true":
        raise HTTPException(403, "Admin disabled")
    if ADMIN_PASSWORD and request.headers.get("x-admin-password", "") != ADMIN_PASSWORD:
        raise HTTPException(401, "Invalid admin password")

ROUTES = {
    "/v1/tts":        os.getenv("TTS_URL",  "http://tts-service:8002"),
    "/v1/stt":        os.getenv("STT_URL",  "http://stt-service:8001"),
    "/v1/sessions":   os.getenv("CONV_URL", "http://conversation-service:8003"),
    "/v1/calls":      os.getenv("TEL_URL",  "http://telephony-service:8004"),
    "/v1/recordings": os.getenv("REC_URL",  "http://recording-service:8005"),
    "/v1/usage":      os.getenv("ANA_URL",  "http://analytics-service:8006"),
}

_pool = None
async def db():
    global _pool
    if _pool is None:
        import asyncpg
        url = os.getenv("POSTGRES_URL", "postgresql://voice:voice@postgres:5432/voiceai")
        url = url.replace("postgresql+asyncpg://", "postgresql://")
        _pool = await asyncpg.create_pool(url)
    return _pool

# --- naive in-memory rate limiter (per key, requests/min). Redis-backed in prod. ---
_rl: dict[str, list[float]] = {}
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_MIN", "300"))

def check_rate(key: str):
    now = time.time()
    win = _rl.setdefault(key, [])
    win[:] = [t for t in win if now - t < 60]
    if len(win) >= RATE_LIMIT:
        raise HTTPException(429, "Rate limit exceeded")
    win.append(now)

# --- live connection tracking (so the dashboard shows who's connected) ---
_activity = {}   # tenant_id -> {"count": n, "last": ts, "paths": {route: n}}
def _touch(tenant_id, path):
    a = _activity.setdefault(tenant_id, {"count": 0, "last": 0.0, "paths": {}})
    a["count"] += 1; a["last"] = time.time()
    route = "/" + "/".join(path.split("/")[:2])   # e.g. /v1/stt
    a["paths"][route] = a["paths"].get(route, 0) + 1

# --- precise traffic metrics: counts, latency, failures (in-memory; resets on restart) ---
_metrics = {"requests": 0, "errors": 0, "lat_ms": [], "by_tenant": {}, "since": time.time()}
_recent_errors = []       # newest-first ring of the last 50 failures
_voice = {"sessions": 0, "active": 0, "turns": 0, "first_audio_ms": []}   # live voice sessions

def _rec_request(tenant_id, path, status, ms, error=""):
    _metrics["requests"] += 1
    _metrics["lat_ms"].append(ms)
    if len(_metrics["lat_ms"]) > 2000:
        _metrics["lat_ms"] = _metrics["lat_ms"][-1000:]
    t = _metrics["by_tenant"].setdefault(tenant_id, {"requests": 0, "errors": 0, "lat_ms": []})
    t["requests"] += 1
    t["lat_ms"].append(ms)
    if len(t["lat_ms"]) > 500:
        t["lat_ms"] = t["lat_ms"][-250:]
    if status >= 400:
        _metrics["errors"] += 1; t["errors"] += 1
        _recent_errors.insert(0, {"ts": int(time.time()), "tenant": tenant_id, "path": "/" + path,
                                  "status": status, "detail": (error or "")[:200]})
        del _recent_errors[50:]

def _lat_stats(vals):
    if not vals:
        return {"avg_ms": None, "p95_ms": None}
    s = sorted(vals)
    return {"avg_ms": round(sum(s) / len(s)), "p95_ms": s[min(len(s) - 1, int(len(s) * 0.95))]}

# --- emergency kill-switch (persisted in Postgres so it survives restarts) ---
_service_enabled = True

async def _settings_table():
    pool = await db()
    await pool.execute("CREATE TABLE IF NOT EXISTS settings (key text PRIMARY KEY, value text)")
    return pool

@app.on_event("startup")
async def _load_service_state():
    global _service_enabled
    try:
        pool = await _settings_table()
        row = await pool.fetchrow("SELECT value FROM settings WHERE key='service_enabled'")
        if row:
            _service_enabled = row["value"] == "1"
    except Exception:
        pass   # DB not up yet -> default enabled; toggle still works once it is

async def authenticate(request: Request) -> dict:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization: Bearer <api_key>")
    raw = auth.removeprefix("Bearer ").strip()
    if raw == os.getenv("DEV_API_KEY", ""):  # dev shortcut when set
        check_rate(raw)
        return {"tenant_id": "dev"}
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    pool = await db()
    row = await pool.fetchrow(
        "SELECT tenant_id FROM api_keys WHERE key_hash=$1 AND revoked=false", hashed)
    if not row:
        raise HTTPException(401, "Invalid API key")
    check_rate(raw)
    return dict(row)

@app.get("/health")
def health():
    return {"ok": True, "service": "api-gateway"}

@app.get("/v1/service_state")
def service_state():
    """Public flag: is the service accepting traffic? The websocket-gateway checks this on every
    new voice session; integrations can use it for their status dot too."""
    return {"enabled": _service_enabled}

@app.post("/admin/service")
async def set_service(request: Request, body: dict):
    """Emergency kill-switch. enabled=false -> REST returns 503 and new voice sessions are refused."""
    check_admin(request)
    global _service_enabled
    _service_enabled = bool(body.get("enabled", True))
    try:
        pool = await _settings_table()
        await pool.execute(
            "INSERT INTO settings (key, value) VALUES ('service_enabled', $1) "
            "ON CONFLICT (key) DO UPDATE SET value=$1", "1" if _service_enabled else "0")
    except Exception:
        pass
    return {"enabled": _service_enabled}

@app.get("/admin/metrics")
async def metrics(request: Request):
    """Precise traffic numbers for the admin panel: request counts, latency, failures, voice sessions."""
    check_admin(request)
    tenants = [{"tenant_id": t, "requests": v["requests"], "errors": v["errors"],
                **_lat_stats(v["lat_ms"])}
               for t, v in sorted(_metrics["by_tenant"].items(),
                                  key=lambda kv: -kv[1]["requests"])]
    return {"enabled": _service_enabled,
            "since": int(_metrics["since"]),
            "requests": _metrics["requests"], "errors": _metrics["errors"],
            **_lat_stats(_metrics["lat_ms"]),
            "voice": {"sessions": _voice["sessions"], "active": _voice["active"],
                      "turns": _voice["turns"],
                      "first_audio": _lat_stats(_voice["first_audio_ms"])},
            "by_tenant": tenants, "recent_errors": _recent_errors}

@app.post("/internal/voice")
async def internal_voice(request: Request, body: dict):
    """Called by the websocket-gateway (internal key) to report voice sessions:
    {event:'start'} on connect; {event:'end', turns, first_audio_ms:[...]} on disconnect."""
    auth = request.headers.get("authorization", "")
    if auth.removeprefix("Bearer ").strip() != os.getenv("DEV_API_KEY", "dev-test-key"):
        raise HTTPException(401, "internal only")
    if body.get("event") == "start":
        _voice["sessions"] += 1; _voice["active"] += 1
        _touch("voice-session", "v1/agent/stream")
    elif body.get("event") == "end":
        _voice["active"] = max(0, _voice["active"] - 1)
        _voice["turns"] += int(body.get("turns", 0))
        for ms in (body.get("first_audio_ms") or [])[:50]:
            if isinstance(ms, (int, float)):
                _voice["first_audio_ms"].append(int(ms))
        if len(_voice["first_audio_ms"]) > 1000:
            _voice["first_audio_ms"] = _voice["first_audio_ms"][-500:]
    return {"ok": True}

@app.get("/admin/activity")
async def activity(request: Request):
    """Live view of which API clients are calling the service (for the dashboard)."""
    check_admin(request)
    now = time.time()
    clients = [{"tenant_id": t, "requests": v["count"], "paths": v["paths"],
                "seconds_ago": round(now - v["last"], 1), "active": (now - v["last"]) < 120}
               for t, v in sorted(_activity.items(), key=lambda kv: -kv[1]["last"])]
    return {"clients": clients, "any_active": any(c["active"] for c in clients)}

@app.get("/admin/verify")
async def admin_verify(request: Request):
    """Password check for the admin panel login gate."""
    check_admin(request)
    return {"ok": True, "password_required": bool(ADMIN_PASSWORD)}

@app.post("/admin/keys")
async def create_key(request: Request, body: dict):
    """Mint a tenant API key. Returns the raw key ONCE (hashed at rest)."""
    check_admin(request)
    tenant = body.get("tenant_id") or f"tenant_{secrets.token_hex(4)}"
    raw = "vk_" + secrets.token_urlsafe(32)
    pool = await db()
    await pool.execute(
        "INSERT INTO tenants (tenant_id, name) VALUES ($1,$2) ON CONFLICT DO NOTHING",
        tenant, body.get("name", tenant))
    await pool.execute(
        "INSERT INTO api_keys (tenant_id, name, key_hash) VALUES ($1,$2,$3)",
        tenant, body.get("name", "default"), hashlib.sha256(raw.encode()).hexdigest())
    return {"tenant_id": tenant, "api_key": raw,
            "note": "Store this now — it is not retrievable later."}

@app.get("/admin/keys")
async def list_keys(request: Request):
    """List keys (metadata only — never the raw key or hash)."""
    check_admin(request)
    pool = await db()
    rows = await pool.fetch(
        "SELECT id, tenant_id, name, revoked, created_at FROM api_keys ORDER BY created_at DESC")
    return {"keys": [{"id": r["id"], "tenant_id": r["tenant_id"], "name": r["name"],
                      "revoked": r["revoked"], "created_at": r["created_at"].isoformat()}
                     for r in rows]}

@app.post("/admin/keys/{key_id}/revoke")
async def revoke_key(key_id: int, request: Request):
    check_admin(request)
    pool = await db()
    await pool.execute("UPDATE api_keys SET revoked=true WHERE id=$1", key_id)
    return {"revoked": key_id}

@app.get("/v1/status")
async def status(request: Request):
    """Public health probe for external integrations (the green/red 'connected' dot).
    Open (no key needed) so a frontend can poll it. If a Bearer key IS sent, we also
    report whether that key is valid — without spending the rate-limit budget."""
    checks = {
        "voice_ws": os.getenv("GW_URL",  "http://websocket-gateway:8000") + "/health",
        "stt":      os.getenv("STT_URL", "http://stt-service:8001") + "/health",
        "tts":      os.getenv("TTS_URL", "http://tts-service:8002") + "/health",
        "llm":      os.getenv("CONV_URL","http://conversation-service:8003") + "/health",
    }
    components = {}
    async with httpx.AsyncClient(timeout=3) as c:
        for name, url in checks.items():
            try:
                r = await c.get(url)
                components[name] = "up" if r.status_code < 500 else "down"
            except Exception:
                components[name] = "down"
    # Optional API-key validity (does not consume the rate limiter).
    key_valid = None
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        raw = auth.removeprefix("Bearer ").strip()
        if raw and raw == os.getenv("DEV_API_KEY", ""):
            key_valid = True
        elif raw:
            try:
                pool = await db()
                row = await pool.fetchrow(
                    "SELECT tenant_id FROM api_keys WHERE key_hash=$1 AND revoked=false",
                    hashlib.sha256(raw.encode()).hexdigest())
                key_valid = bool(row)
            except Exception:
                key_valid = None
    return {"ok": _service_enabled and all(v == "up" for v in components.values()),
            "service": "voice-ai", "enabled": _service_enabled,
            "components": components, "api_key_valid": key_valid, "time": int(time.time())}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    if not _service_enabled:
        raise HTTPException(503, "Service disabled by admin")
    tenant = await authenticate(request)
    _touch(tenant["tenant_id"], path)   # record for the live connection view
    target = None
    for prefix, base in ROUTES.items():
        if ("/" + path).startswith(prefix):
            target = base
            break
    if not target:
        raise HTTPException(404, f"No route for /{path}")
    t0 = time.time()
    async with httpx.AsyncClient(timeout=120) as client:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None); headers.pop("content-length", None)
        # the gateway is the auth boundary: it validated the tenant's public vk_ key, then talks to
        # internal services with the trusted internal key so they accept the proxied request.
        headers["authorization"] = f"Bearer {os.getenv('DEV_API_KEY', 'dev-test-key')}"
        headers["x-tenant-id"] = tenant["tenant_id"]
        try:
            r = await client.request(request.method, f"{target}/{path}",
                                     content=body, headers=headers,
                                     params=dict(request.query_params))
        except Exception as e:
            _rec_request(tenant["tenant_id"], path, 502, int((time.time()-t0)*1000), str(e))
            raise HTTPException(502, f"Upstream unreachable: {e}")
        ms = int((time.time()-t0)*1000)
        err = r.text[:200] if r.status_code >= 400 else ""
        _rec_request(tenant["tenant_id"], path, r.status_code, ms, err)
        return Response(content=r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
