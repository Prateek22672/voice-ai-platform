"""API key auth. Keys stored hashed (sha256) in Postgres. Bearer token check."""
import hashlib
from fastapi import Header, HTTPException

def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()

async def verify_api_key(authorization: str = Header(None), db=None) -> dict:
    """FastAPI dependency. Returns tenant record or raises 401."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Authorization: Bearer <api_key>")
    raw = authorization.removeprefix("Bearer ").strip()
    hashed = hash_key(raw)
    if db is None:
        # standalone mode: accept the seeded dev key
        import os
        dev = os.getenv("DEV_API_KEY", "dev-test-key")
        if raw == dev:
            return {"tenant_id": "dev", "name": "dev-tenant"}
        raise HTTPException(401, "Invalid API key")
    row = await db.fetchrow("SELECT tenant_id, name FROM api_keys WHERE key_hash=$1 AND revoked=false", hashed)
    if not row:
        raise HTTPException(401, "Invalid API key")
    return dict(row)
