"""TTS Service — streaming synthesis, ElevenLabs-shaped API.
POST /v1/tts               : {"text","voice"} -> audio/wav (or chunked PCM stream w/ ?stream=1)
WS   /v1/tts/stream        : JSON {"text","voice"} in -> binary PCM16 chunks out, then {"type":"done"}
POST /v1/tts/voices        : upload reference wav -> cloned voice id (backend-dependent)
GET  /v1/tts/voices        : list voices
Pipeline: normalize -> sentence split -> adapter.synth_stream -> ~200ms chunks. First chunk ships
while later sentences still synthesize — this is what makes it feel real-time."""
import asyncio, io, json, os, struct, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi import FastAPI, WebSocket, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import StreamingResponse, Response
from shared.auth import verify_api_key
from normalizer import normalize, split_sentences
from adapters.base import load_adapter

app = FastAPI(title="tts-service", version="1.0.0")

# Dev CORS: lets the browser dashboard on :3000 call this service (enroll/list/delete voices).
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)

_adapter = None

def get_adapter():
    global _adapter
    if _adapter is None:
        _adapter = load_adapter(os.getenv("TTS_BACKEND", "kokoro"))
    return _adapter

def wav_header(sr: int, data_len: int) -> bytes:
    return (b"RIFF" + struct.pack("<I", 36 + data_len) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, sr, sr*2, 2, 16) +
            b"data" + struct.pack("<I", data_len))

@app.on_event("startup")
async def _prewarm():
    """Load the TTS model in a background thread at boot so the first WS connection
    doesn't block the event loop (which caused gateway handshake timeouts)."""
    asyncio.get_event_loop().run_in_executor(None, get_adapter)

@app.get("/health")
def health():
    return {"ok": True, "service": "tts", "backend": os.getenv("TTS_BACKEND", "kokoro")}

@app.post("/v1/tts")
async def synth(body: dict, tenant=Depends(verify_api_key)):
    ad = get_adapter()
    text = normalize(body["text"])
    voice = body.get("voice")
    t0 = time.time()
    chunks = []
    first_chunk_ms = None
    for sentence in split_sentences(text):
        async for chunk in ad.synth_stream(sentence, voice):
            if first_chunk_ms is None:
                first_chunk_ms = int((time.time()-t0)*1000)
            chunks.append(chunk)
    pcm = b"".join(chunks)
    audio = wav_header(ad.sample_rate, len(pcm)) + pcm
    return Response(content=audio, media_type="audio/wav",
                    headers={"X-First-Chunk-Ms": str(first_chunk_ms or -1)})

@app.websocket("/v1/tts/stream")
async def synth_stream_ws(ws: WebSocket):
    await ws.accept()
    ad = await asyncio.get_event_loop().run_in_executor(None, get_adapter)
    try:
        while True:
            msg = await ws.receive_text()
            req = json.loads(msg)
            if req.get("event") == "close":
                break
            text = normalize(req["text"])
            t0 = time.time()
            first = None
            for sentence in split_sentences(text):
                async for chunk in ad.synth_stream(sentence, req.get("voice")):
                    if first is None:
                        first = int((time.time()-t0)*1000)
                    await ws.send_bytes(chunk)
            await ws.send_text(json.dumps({"type": "done", "sample_rate": ad.sample_rate,
                                           "first_chunk_ms": first}))
    except Exception:
        pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass

@app.post("/v1/tts/voices")
async def clone_voice(name: str = Form(...), file: UploadFile = File(...),
                      transcript: str = Form(""), tenant=Depends(verify_api_key)):
    """Store an enrolled voice reference. Works on any backend (saves the wav); actually
    SPEAKING in the voice needs a cloning backend (f5tts/xtts)."""
    import re
    safe = re.sub(r"[^a-z0-9_]+", "", name.lower())
    if not safe:
        raise HTTPException(400, "invalid voice name")
    vdir = os.getenv("VOICE_DIR", "./voices")
    os.makedirs(vdir, exist_ok=True)
    data = await file.read()
    with open(os.path.join(vdir, safe + ".wav"), "wb") as f:
        f.write(data)
    if transcript.strip():
        with open(os.path.join(vdir, safe + ".txt"), "w", encoding="utf-8") as f:
            f.write(transcript.strip())
    backend = os.getenv("TTS_BACKEND", "kokoro")
    clonable = backend in ("f5tts", "xtts")
    return {"voice_id": safe, "stored": True, "clonable_now": clonable, "backend": backend,
            "note": "" if clonable else "Voice saved. Switch TTS_BACKEND to f5tts (GPU) to speak in it."}

@app.delete("/v1/tts/voices/{name}")
async def delete_voice(name: str, tenant=Depends(verify_api_key)):
    import re
    safe = re.sub(r"[^a-z0-9_]+", "", name.lower())
    vdir = os.getenv("VOICE_DIR", "./voices")
    removed = False
    for ext in (".wav", ".txt"):
        p = os.path.join(vdir, safe + ext)
        if os.path.exists(p):
            os.remove(p); removed = True
    if not removed:
        raise HTTPException(404, "voice not found")
    return {"deleted": safe}

@app.get("/v1/tts/voices")
async def list_voices(tenant=Depends(verify_api_key)):
    vd = os.getenv("VOICE_DIR", "./voices")
    voices = []
    if os.path.isdir(vd):
        voices = [f[:-4] for f in os.listdir(vd) if f.endswith(".wav")]
    return {"voices": voices, "backend": os.getenv("TTS_BACKEND", "kokoro")}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8002")))
