"""Recording Service — stores call/session audio + transcripts. MinIO/S3 blobs, Postgres index.
POST /v1/recordings                : upload {call_id, kind: in|out|merged} + audio file
GET  /v1/recordings/{call_id}      : list artifacts + presigned download URLs
POST /v1/recordings/{call_id}/transcript : attach transcript JSON
GET  /v1/recordings/{call_id}/transcript"""
import io, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from shared.auth import verify_api_key

app = FastAPI(title="recording-service", version="1.0.0")
_minio = None; _pool = None

def minio():
    global _minio
    if _minio is None:
        from minio import Minio
        _minio = Minio(os.getenv("MINIO_ENDPOINT", "minio:9000"),
                       access_key=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
                       secret_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
                       secure=False)
        bucket = os.getenv("MINIO_BUCKET", "recordings")
        if not _minio.bucket_exists(bucket):
            _minio.make_bucket(bucket)
    return _minio

async def db():
    global _pool
    if _pool is None:
        import asyncpg
        url = os.getenv("POSTGRES_URL", "postgresql://voice:voice@postgres:5432/voiceai")
        _pool = await asyncpg.create_pool(url.replace("postgresql+asyncpg://", "postgresql://"))
    return _pool

BUCKET = os.getenv("MINIO_BUCKET", "recordings")

@app.get("/health")
def health():
    return {"ok": True, "service": "recording"}

@app.post("/v1/recordings")
async def upload(call_id: str = Form(...), kind: str = Form("merged"),
                 file: UploadFile = File(...), tenant=Depends(verify_api_key)):
    data = await file.read()
    key = f"{tenant['tenant_id']}/{call_id}/{kind}_{int(time.time())}.wav"
    minio().put_object(BUCKET, key, io.BytesIO(data), len(data), content_type="audio/wav")
    pool = await db()
    await pool.execute(
        "INSERT INTO recordings (tenant_id, call_id, kind, object_key, size_bytes) "
        "VALUES ($1,$2,$3,$4,$5)", tenant["tenant_id"], call_id, kind, key, len(data))
    return {"object_key": key, "size": len(data)}

@app.get("/v1/recordings/{call_id}")
async def list_recordings(call_id: str, tenant=Depends(verify_api_key)):
    pool = await db()
    rows = await pool.fetch(
        "SELECT kind, object_key, size_bytes, created_at FROM recordings "
        "WHERE call_id=$1 AND tenant_id=$2", call_id, tenant["tenant_id"])
    from datetime import timedelta
    out = []
    for r in rows:
        url = minio().presigned_get_object(BUCKET, r["object_key"], expires=timedelta(hours=1))
        out.append({"kind": r["kind"], "size": r["size_bytes"],
                    "created_at": str(r["created_at"]), "download_url": url})
    return {"call_id": call_id, "recordings": out}

@app.post("/v1/recordings/{call_id}/transcript")
async def save_transcript(call_id: str, body: dict, tenant=Depends(verify_api_key)):
    pool = await db()
    await pool.execute(
        "INSERT INTO transcripts (tenant_id, call_id, content) VALUES ($1,$2,$3) "
        "ON CONFLICT (call_id) DO UPDATE SET content=$3",
        tenant["tenant_id"], call_id, json.dumps(body))
    return {"ok": True}

@app.get("/v1/recordings/{call_id}/transcript")
async def get_transcript(call_id: str, tenant=Depends(verify_api_key)):
    pool = await db()
    row = await pool.fetchrow(
        "SELECT content FROM transcripts WHERE call_id=$1 AND tenant_id=$2",
        call_id, tenant["tenant_id"])
    if not row:
        raise HTTPException(404, "No transcript")
    return json.loads(row["content"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8005")))
