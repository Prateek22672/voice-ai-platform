"""TTS Service — streaming synthesis, ElevenLabs-shaped API.
POST /v1/tts               : {"text","voice"} -> audio/wav (or chunked PCM stream w/ ?stream=1)
WS   /v1/tts/stream        : JSON {"text","voice"} in -> binary PCM16 chunks out, then {"type":"done"}
POST /v1/tts/voices        : upload reference wav -> cloned voice id (backend-dependent)
GET  /v1/tts/voices        : list voices
Pipeline: normalize -> sentence split -> adapter.synth_stream -> ~200ms chunks. First chunk ships
while later sentences still synthesize — this is what makes it feel real-time."""
import asyncio, io, json, os, struct, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi import FastAPI, WebSocket, UploadFile, File, Form, Depends, HTTPException, Header
from fastapi.responses import StreamingResponse, Response
from shared.auth import verify_api_key
from normalizer import normalize, split_sentences
from adapters.base import load_adapter

app = FastAPI(title="tts-service", version="1.0.0")

# ---- Built-in Kokoro voice catalog: the single source of truth for the Voice Studio. ----
# id = Kokoro voice id (1st letter a=American/b=British, 2nd f=female/m=male). grade = Kokoro's
# own quality grade. featured = the ones we recommend first.
VOICE_CATALOG = [
    {"id": "af_heart",    "name": "Heart",    "accent": "American", "gender": "Female", "grade": "A",  "tag": "Flagship — warmest, most natural", "featured": True},
    {"id": "af_bella",    "name": "Bella",    "accent": "American", "gender": "Female", "grade": "A-", "tag": "Expressive and lively",             "featured": True},
    {"id": "af_nicole",   "name": "Nicole",   "accent": "American", "gender": "Female", "grade": "B-", "tag": "Soft, intimate"},
    {"id": "af_aoede",    "name": "Aoede",    "accent": "American", "gender": "Female", "grade": "C+", "tag": "Clear and neutral"},
    {"id": "af_kore",     "name": "Kore",     "accent": "American", "gender": "Female", "grade": "C+", "tag": "Bright, professional"},
    {"id": "af_sarah",    "name": "Sarah",    "accent": "American", "gender": "Female", "grade": "C+", "tag": "Calm and friendly"},
    {"id": "af_nova",     "name": "Nova",     "accent": "American", "gender": "Female", "grade": "C",  "tag": "Youthful"},
    {"id": "af_sky",      "name": "Sky",      "accent": "American", "gender": "Female", "grade": "C-", "tag": "Light and airy"},
    {"id": "am_michael",  "name": "Michael",  "accent": "American", "gender": "Male",   "grade": "C+", "tag": "Warm and steady",                  "featured": True},
    {"id": "am_fenrir",   "name": "Fenrir",   "accent": "American", "gender": "Male",   "grade": "C+", "tag": "Deep and confident"},
    {"id": "am_puck",     "name": "Puck",     "accent": "American", "gender": "Male",   "grade": "C+", "tag": "Playful, energetic"},
    {"id": "am_echo",     "name": "Echo",     "accent": "American", "gender": "Male",   "grade": "C",  "tag": "Neutral and even"},
    {"id": "am_eric",     "name": "Eric",     "accent": "American", "gender": "Male",   "grade": "C",  "tag": "Clear, business"},
    {"id": "am_onyx",     "name": "Onyx",     "accent": "American", "gender": "Male",   "grade": "C",  "tag": "Low, authoritative"},
    {"id": "bf_emma",     "name": "Emma",     "accent": "British",  "gender": "Female", "grade": "B-", "tag": "Refined and warm",                 "featured": True},
    {"id": "bf_isabella", "name": "Isabella", "accent": "British",  "gender": "Female", "grade": "C",  "tag": "Elegant"},
    {"id": "bf_alice",    "name": "Alice",    "accent": "British",  "gender": "Female", "grade": "C",  "tag": "Crisp"},
    {"id": "bf_lily",     "name": "Lily",     "accent": "British",  "gender": "Female", "grade": "C",  "tag": "Gentle"},
    {"id": "bm_george",   "name": "George",   "accent": "British",  "gender": "Male",   "grade": "C",  "tag": "Classic RP, mature",               "featured": True},
    {"id": "bm_fable",    "name": "Fable",    "accent": "British",  "gender": "Male",   "grade": "C",  "tag": "Storyteller"},
    {"id": "bm_lewis",    "name": "Lewis",    "accent": "British",  "gender": "Male",   "grade": "C+", "tag": "Deep, resonant"},
    {"id": "bm_daniel",   "name": "Daniel",   "accent": "British",  "gender": "Male",   "grade": "C",  "tag": "Polished"},
    # more American voices (variety)
    {"id": "af_alloy",    "name": "Alloy",    "accent": "American", "gender": "Female", "grade": "C",  "tag": "Balanced, modern"},
    {"id": "af_jessica",  "name": "Jessica",  "accent": "American", "gender": "Female", "grade": "D",  "tag": "Casual, relaxed"},
    {"id": "af_river",    "name": "River",    "accent": "American", "gender": "Female", "grade": "D",  "tag": "Soft-spoken"},
    {"id": "am_liam",     "name": "Liam",     "accent": "American", "gender": "Male",   "grade": "D",  "tag": "Casual, friendly"},
    # Hindi / Indian voices — speak Hindi and Hinglish naturally (set the call language accordingly)
    {"id": "hf_alpha",    "name": "Priya",    "accent": "Hindi",    "gender": "Female", "grade": "C",  "tag": "Warm Hindi/Hinglish",              "featured": True},
    {"id": "hf_beta",     "name": "Ananya",   "accent": "Hindi",    "gender": "Female", "grade": "C",  "tag": "Clear Hindi/Hinglish"},
    {"id": "hm_omega",    "name": "Arjun",    "accent": "Hindi",    "gender": "Male",   "grade": "C",  "tag": "Steady Hindi/Hinglish",            "featured": True},
    {"id": "hm_psi",      "name": "Rohan",    "accent": "Hindi",    "gender": "Male",   "grade": "C",  "tag": "Energetic Hindi/Hinglish"},
    # Telugu — open-source Meta MMS-TTS model (facebook/mms-tts-tel), no API cost
    {"id": "te_mms",      "name": "Vani",     "accent": "Telugu",   "gender": "Female", "grade": "C",  "tag": "Telugu (open-source MMS)",         "featured": True},
]
VALID_VOICE_IDS = {v["id"] for v in VOICE_CATALOG}

# Runtime-selectable default voice (what the live agent speaks with). Persisted to a small
# file so the choice survives restarts; falls back to KOKORO_VOICE env, then af_heart.
_VOICE_STATE_FILE = os.path.join(os.getenv("VOICE_DIR", "./voices"), "_default_voice.txt")

def _voice_ok(v):
    """A voice is usable if it's a built-in Kokoro voice OR an 'eleven:<id>' premium voice
    (only when the ElevenLabs key is configured)."""
    return v in VALID_VOICE_IDS or (v.startswith("eleven:") and bool(os.getenv("ELEVENLABS_API_KEY")))

def _load_default_voice():
    try:
        with open(_VOICE_STATE_FILE, encoding="utf-8") as f:
            v = f.read().strip()
            if _voice_ok(v):
                return v
    except Exception:
        pass
    return os.getenv("KOKORO_VOICE", "af_heart")

def _save_default_voice(v):
    try:
        os.makedirs(os.path.dirname(_VOICE_STATE_FILE), exist_ok=True)
        with open(_VOICE_STATE_FILE, "w", encoding="utf-8") as f:
            f.write(v)
    except Exception:
        pass

_DEFAULT_VOICE = _load_default_voice()

# Dev CORS: lets the browser dashboard on :3000 call this service (enroll/list/delete voices).
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)

_adapter = None
_eleven = None
_mms = None

def get_adapter():
    global _adapter
    if _adapter is None:
        _adapter = load_adapter(os.getenv("TTS_BACKEND", "kokoro"))
    return _adapter

def adapter_for(voice):
    """Hybrid per-voice routing: a voice id of the form 'eleven:<elevenlabs_voice_id>' is spoken
    through ElevenLabs (premium, ultra-natural — e.g. the 'Anushri' e-commerce voice from their
    library) while every other voice uses the default backend (Kokoro). Lets ONE deployment mix
    free and premium voices per session instead of switching the whole backend.
    Returns (adapter, voice_id_for_that_adapter)."""
    global _eleven, _mms
    if voice and voice.startswith("eleven:"):
        if os.getenv("ELEVENLABS_API_KEY"):
            if _eleven is None:
                from adapters.elevenlabs_adapter import ElevenLabsAdapter
                _eleven = ElevenLabsAdapter()
            return _eleven, voice.split(":", 1)[1]
        # no key configured -> degrade gracefully to the default backend's default voice
        return get_adapter(), None
    if voice and voice.startswith("te_"):
        # Telugu -> open-source Meta MMS-TTS (Kokoro has no Telugu). Lazy-loaded on first use.
        if _mms is None:
            from adapters.mms_adapter import MMSAdapter
            _mms = MMSAdapter()
        return _mms, voice
    return get_adapter(), voice

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
    text = normalize(body["text"])
    ad, voice = adapter_for(body.get("voice") or _DEFAULT_VOICE)
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
            sad, voice = adapter_for(req.get("voice") or _DEFAULT_VOICE)
            # announce the sample rate BEFORE any audio: adapters differ (Kokoro 24k, MMS 16k)
            # and the client must never guess-play at the wrong speed
            await ws.send_text(json.dumps({"type": "meta", "sample_rate": sad.sample_rate}))
            t0 = time.time()
            first = None
            for sentence in split_sentences(text):
                async for chunk in sad.synth_stream(sentence, voice):
                    if first is None:
                        first = int((time.time()-t0)*1000)
                    await ws.send_bytes(chunk)
            await ws.send_text(json.dumps({"type": "done", "sample_rate": sad.sample_rate,
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

@app.get("/v1/tts/catalog")
def voice_catalog():
    """All built-in natural voices + the one the live agent currently uses. Open (no key)
    so the Voice Studio can render the gallery."""
    return {"voices": VOICE_CATALOG, "default": _DEFAULT_VOICE,
            "backend": os.getenv("TTS_BACKEND", "kokoro")}

@app.get("/v1/tts/default_voice")
def get_default_voice():
    return {"voice": _DEFAULT_VOICE}

@app.post("/v1/tts/default_voice")
async def set_default_voice(body: dict, x_admin_password: str = Header(default="")):
    """Set the live agent voice. Guarded by the admin password when ADMIN_PASSWORD is set."""
    admin = os.getenv("ADMIN_PASSWORD", "")
    if admin and x_admin_password != admin:
        raise HTTPException(401, "bad admin password")
    v = (body.get("voice") or "").strip()
    if not _voice_ok(v):
        raise HTTPException(400, "unknown voice (built-in id, or eleven:<voice_id> with an ElevenLabs key)")
    global _DEFAULT_VOICE
    _DEFAULT_VOICE = v
    _save_default_voice(v)
    return {"voice": _DEFAULT_VOICE, "ok": True}

@app.post("/v1/tts/preview")
async def preview(body: dict):
    """Short, unauthenticated preview for the Voice Studio — built-in voices only, text capped."""
    v = body.get("voice") or _DEFAULT_VOICE
    if v not in VALID_VOICE_IDS:
        raise HTTPException(400, "unknown voice")
    text = normalize((body.get("text") or "")[:300]) or "Hello — this is a preview of my voice."
    ad = get_adapter()
    chunks = []
    for sentence in split_sentences(text):
        async for chunk in ad.synth_stream(sentence, v):
            chunks.append(chunk)
    pcm = b"".join(chunks)
    return Response(content=wav_header(ad.sample_rate, len(pcm)) + pcm, media_type="audio/wav")

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
