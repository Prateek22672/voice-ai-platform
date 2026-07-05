"""Analytics Service — usage metering + latency metrics.
POST /v1/events        : ingest {tenant_id, type, value, meta} (stt_ms, tts_first_chunk_ms,
                         llm_first_token_ms, call_minutes, tts_chars, stt_seconds, interruption...)
GET  /v1/usage         : per-tenant usage rollup (billing basis)
GET  /metrics          : Prometheus exposition"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from collections import defaultdict
from fastapi import FastAPI, Depends, Response, Header
from shared.auth import verify_api_key

app = FastAPI(title="analytics-service", version="1.0.0")
_pool = None

async def db():
    global _pool
    if _pool is None:
        import asyncpg
        url = os.getenv("POSTGRES_URL", "postgresql://voice:voice@postgres:5432/voiceai")
        _pool = await asyncpg.create_pool(url.replace("postgresql+asyncpg://", "postgresql://"))
    return _pool

# in-memory prometheus counters/histograms (simple, no client lib dependency)
_counters = defaultdict(float)
_lat = defaultdict(list)

@app.get("/health")
def health():
    return {"ok": True, "service": "analytics"}

@app.post("/v1/events")
async def ingest(body: dict, x_tenant_id: str = Header(default="dev")):
    etype = body.get("type", "unknown")
    value = float(body.get("value", 1))
    _counters[f"{etype}_total"] += value
    if etype.endswith("_ms"):
        _lat[etype].append(value)
        _lat[etype] = _lat[etype][-1000:]
    pool = await db()
    await pool.execute(
        "INSERT INTO usage_events (tenant_id, event_type, value, meta) VALUES ($1,$2,$3,$4)",
        x_tenant_id, etype, value, str(body.get("meta", {})))
    return {"ok": True}

@app.get("/v1/usage")
async def usage(tenant=Depends(verify_api_key)):
    pool = await db()
    rows = await pool.fetch(
        "SELECT event_type, SUM(value) AS total, COUNT(*) AS n FROM usage_events "
        "WHERE tenant_id=$1 GROUP BY event_type", tenant["tenant_id"])
    return {"tenant_id": tenant["tenant_id"],
            "usage": {r["event_type"]: {"total": float(r["total"]), "count": r["n"]} for r in rows}}

@app.get("/metrics")
def metrics():
    lines = []
    for k, v in _counters.items():
        lines.append(f"voiceai_{k} {v}")
    for k, vals in _lat.items():
        if vals:
            s = sorted(vals)
            lines.append(f"voiceai_{k}_p50 {s[len(s)//2]}")
            lines.append(f"voiceai_{k}_p95 {s[int(len(s)*0.95)]}")
    return Response("\n".join(lines) + "\n", media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8006")))
