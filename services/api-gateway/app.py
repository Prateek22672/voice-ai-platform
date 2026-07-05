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

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request):
    tenant = await authenticate(request)
    _touch(tenant["tenant_id"], path)   # record for the live connection view
    target = None
    for prefix, base in ROUTES.items():
        if ("/" + path).startswith(prefix):
            target = base
            break
    if not target:
        raise HTTPException(404, f"No route for /{path}")
    async with httpx.AsyncClient(timeout=120) as client:
        body = await request.body()
        headers = dict(request.headers)
        headers.pop("host", None); headers.pop("content-length", None)
        # the gateway is the auth boundary: it validated the tenant's public vk_ key, then talks to
        # internal services with the trusted internal key so they accept the proxied request.
        headers["authorization"] = f"Bearer {os.getenv('DEV_API_KEY', 'dev-test-key')}"
        headers["x-tenant-id"] = tenant["tenant_id"]
        r = await client.request(request.method, f"{target}/{path}",
                                 content=body, headers=headers,
                                 params=dict(request.query_params))
        return Response(content=r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
