"""STT Service — streaming + batch transcription.
WS  /v1/stt/stream : send 16kHz mono PCM16 binary frames; receive JSON partial/final transcripts.
POST /v1/stt       : upload audio file, get full transcript.
Pipeline: PCM in -> Silero VAD -> faster-whisper -> text out.
"""
import asyncio, io, json, time, os, sys, wave
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import numpy as np
from fastapi import FastAPI, WebSocket, UploadFile, File, Depends, HTTPException
from fastapi.responses import JSONResponse
from shared.auth import verify_api_key

app = FastAPI(title="stt-service", version="1.0.0")

# Dev CORS so the dashboard (:3000) can read /health and /v1/usage_stt cross-origin.
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)

_model = None
_vad = None

# STT_BACKEND: "whisper" = self-hosted faster-whisper (default) | "openai" = OpenAI's
# gpt-4o-transcribe API (ChatGPT-level accuracy, no GPU needed, ~$0.006/min).
STT_BACKEND = os.getenv("STT_BACKEND", "whisper").lower()

# ---- OpenAI usage tracking (powers the Insights page) ----
import threading
_usage_lock = threading.Lock()
_USAGE_FILE = os.path.join(os.getenv("VOICE_DIR", "./voices"), "openai_usage.json")
# USD per minute of audio (approximate list price). Groq Whisper is far cheaper than OpenAI.
STT_RATES = {
    "gpt-4o-transcribe": 0.006, "gpt-4o-mini-transcribe": 0.003, "whisper-1": 0.006,   # OpenAI
    "whisper-large-v3": 0.00185, "whisper-large-v3-turbo": 0.000667,                    # Groq ($0.111/$0.04 per hr)
    "distil-whisper-large-v3-en": 0.000333,                                             # Groq ($0.02/hr)
}
# Cloud STT providers (OpenAI-compatible transcription API shape).
CLOUD_STT = {
    "openai": {"url": "https://api.openai.com/v1/audio/transcriptions",
               "key": "OPENAI_API_KEY", "model_env": "OPENAI_STT_MODEL",
               "model_default": "gpt-4o-transcribe"},
    "groq":   {"url": "https://api.groq.com/openai/v1/audio/transcriptions",
               "key": "GROQ_API_KEY", "model_env": "GROQ_STT_MODEL",
               "model_default": "whisper-large-v3"},   # full large-v3 = top accuracy, no quality drop
}

def _record_usage(model, seconds):
    with _usage_lock:
        try:
            data = json.load(open(_USAGE_FILE)) if os.path.exists(_USAGE_FILE) else {}
        except Exception:
            data = {}
        data["calls"] = data.get("calls", 0) + 1
        data["audio_seconds"] = data.get("audio_seconds", 0.0) + seconds
        bm = data.setdefault("by_model", {})
        m = bm.setdefault(model, {"calls": 0, "seconds": 0.0})
        m["calls"] += 1; m["seconds"] += seconds
        try:
            json.dump(data, open(_USAGE_FILE, "w"))
        except Exception:
            pass

def _usage_summary():
    with _usage_lock:
        try:
            data = json.load(open(_USAGE_FILE)) if os.path.exists(_USAGE_FILE) else {}
        except Exception:
            data = {}
    total_cost, by = 0.0, []
    for m, v in data.get("by_model", {}).items():
        rate = STT_RATES.get(m, 0.006); c = v["seconds"] / 60 * rate; total_cost += c
        by.append({"model": m, "calls": v["calls"], "minutes": round(v["seconds"]/60, 3),
                   "cost_usd": round(c, 4)})
    return {"backend": STT_BACKEND, "total_calls": data.get("calls", 0),
            "total_minutes": round(data.get("audio_seconds", 0.0)/60, 3),
            "est_cost_usd": round(total_cost, 4), "usd_inr": 85,
            "est_cost_inr": round(total_cost * 85, 2), "by_model": by}

def get_model():
    global _model
    if STT_BACKEND in CLOUD_STT:
        return None  # no local model needed; transcription goes to the cloud API
    if _model is None:
        from faster_whisper import WhisperModel
        size   = os.getenv("WHISPER_MODEL", "small")
        device = os.getenv("WHISPER_DEVICE", "auto")
        compute = os.getenv("WHISPER_COMPUTE", "default")
        _model = WhisperModel(size, device=device, compute_type=compute)
    return _model

def _pcm_to_wav(audio_f32, sr=16000):
    """float32 [-1,1] mono -> 16-bit PCM WAV bytes (for the OpenAI upload)."""
    import io, struct, wave
    pcm = (np.clip(audio_f32, -1, 1) * 32767).astype(np.int16).tobytes()
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm)
    return b.getvalue()

_key_rr = {}   # backend -> round-robin index

# One pooled HTTP client with keep-alive: reusing the TLS connection to Groq/OpenAI saves
# a fresh handshake (~100-300ms) on EVERY transcription call.
_http_client = None
def _http():
    global _http_client
    if _http_client is None:
        import httpx
        _http_client = httpx.Client(timeout=30,
                                    limits=httpx.Limits(max_keepalive_connections=4,
                                                        keepalive_expiry=60))
    return _http_client

def _keys_for(env_name):
    """Support ONE key or a comma-separated list of keys (for rotation across free tiers)."""
    return [k.strip() for k in os.getenv(env_name, "").split(",") if k.strip()]

def _confident(segments):
    """True only if the transcription looks like REAL speech, not a gibberish/noise
    hallucination. Uses Whisper's own per-segment scores (returned in verbose_json):
      - avg_logprob : how sure the model is (near 0 = sure; very negative = guessing)
      - no_speech_prob : chance the audio is actually silence/noise
      - compression_ratio : high = repetitive/invented text
    Each check ONLY applies when that field is actually present, so a backend that omits a
    score never causes a false drop. Thresholds are env-tunable (no redeploy needed)."""
    def _num(vals):  # keep only numeric values that are present
        return [v for v in vals if isinstance(v, (int, float))]
    min_lp = float(os.getenv("STT_MIN_AVG_LOGPROB", "-0.85"))
    max_ns = float(os.getenv("STT_MAX_NO_SPEECH", "0.6"))
    max_cr = float(os.getenv("STT_MAX_COMPRESSION", "2.5"))
    lp_pairs = [(s.get("avg_logprob"), max(1, len(s.get("text") or "")))
                for s in segments if isinstance(s.get("avg_logprob"), (int, float))]
    nss = _num(s.get("no_speech_prob") for s in segments)
    crs = _num(s.get("compression_ratio") for s in segments)
    if lp_pairs:
        tot = sum(w for _, w in lp_pairs)
        avg_lp = sum(v * w for v, w in lp_pairs) / max(1, tot)
        if avg_lp < min_lp:
            print(f"[stt] dropped low-confidence utterance (avg_logprob={avg_lp:.2f} < {min_lp})", flush=True)
            return False
    if nss and max(nss) > max_ns:
        print(f"[stt] dropped noise utterance (no_speech_prob={max(nss):.2f} > {max_ns})", flush=True)
        return False
    if crs and max(crs) > max_cr:
        print(f"[stt] dropped repetitive utterance (compression_ratio={max(crs):.2f} > {max_cr})", flush=True)
        return False
    return True

def cloud_transcribe(audio_f32, backend, lang=None):
    """Send one utterance to a cloud transcription API (OpenAI or Groq — same API shape).
    We request verbose_json so we get confidence scores and can REJECT gibberish/noise instead of
    inventing a sentence. Groq's Whisper runs on their fast LPU. Supports MULTIPLE keys:
    set GROQ_API_KEY=key1,key2 — we round-robin and fail over to the next key on a 429.
    lang = per-session language override (hi/te/...); Whisper transcribes these natively."""
    import httpx
    cfg = CLOUD_STT[backend]
    keys = _keys_for(cfg["key"])
    if not keys:
        return ""
    model = os.getenv(cfg["model_env"], cfg["model_default"])
    wav = _pcm_to_wav(audio_f32)
    req_data = {"model": model, "response_format": "verbose_json",
                "language": lang or os.getenv("STT_LANG") or "en", "temperature": 0}
    prompt = os.getenv("STT_PROMPT", "").strip()      # domain vocabulary hint (e.g. interview terms)
    if prompt:
        req_data["prompt"] = prompt
    start = _key_rr.get(backend, 0)
    _key_rr[backend] = (start + 1) % len(keys)         # rotate for the next call
    for i in range(len(keys)):                          # try each key until one works
        key = keys[(start + i) % len(keys)]
        try:
            r = _http().post(cfg["url"], headers={"Authorization": f"Bearer {key}"},
                             files={"file": ("audio.wav", wav, "audio/wav")},
                             data=req_data)
            if r.status_code == 429:                     # rate limited -> try the next key
                continue
            r.raise_for_status()
            _record_usage(model, len(audio_f32) / 16000.0)
            try:
                j = r.json()
            except Exception:
                return r.text.strip()                    # non-JSON (shouldn't happen) -> accept text
            text = (j.get("text") or "").strip()
            segs = j.get("segments") or []
            if segs and not _confident(segs):
                return ""                                # gibberish / low-confidence -> no sentence
            return text
        except Exception:
            continue
    return ""   # every key failed / rate-limited

# ---- our own audio pre-processing (before STT) — improves accuracy on ANY backend ----
def preprocess_audio(a):
    """Clean the mic audio before transcription: remove DC offset + low-freq rumble,
    then peak-normalize so quiet speech is boosted. All cheap numpy, no extra deps."""
    if os.getenv("STT_PREPROCESS", "1") != "1" or a is None or len(a) == 0:
        return a
    a = a.astype(np.float32)
    a = a - float(np.mean(a))                      # 1. remove DC offset (centre the waveform)
    K = 200                                          # 2. crude high-pass (~<80Hz): subtract a
    if len(a) > K:                                   #    long moving average = the low rumble
        lp = np.convolve(a, np.ones(K, dtype=np.float32) / K, mode="same")
        a = a - lp
    peak = float(np.max(np.abs(a)))                  # 3. peak-normalize to ~-1 dBFS (big STT win:
    if peak > 1e-4:                                  #    consistent loudness = fewer errors)
        a = a * (0.89 / peak)
    return np.clip(a, -1.0, 1.0)

# ---- our own text post-processing (after STT) — strips Whisper's classic artifacts ----
_HALLUCINATIONS = {
    "thank you.", "thank you", "thanks for watching.", "thanks for watching",
    "thank you for watching.", "please subscribe.", "subscribe.", "you", "you.",
    ".", "..", "...", "bye.", "bye", "okay.", "so.", "the.", "i", "i.",
    # Whisper's classic noise-hallucinations in Hindi/Telugu (video-outro phrases)
    "धन्यवाद", "धन्यवाद।", "शुक्रिया", "सब्सक्राइब करें", "देखने के लिए धन्यवाद",
    "ధన్యవాదాలు", "ధన్యవాదాలు.", "చూసినందుకు ధన్యవాదాలు",
}
def postprocess_text(t):
    """Drop known hallucination phrases (Whisper invents these on noise/near-silence) and
    collapse runaway word repetition."""
    if os.getenv("STT_POSTPROCESS", "1") != "1" or not t:
        return t
    t = t.strip()
    if t.lower().strip() in _HALLUCINATIONS:
        return ""                                    # noise mis-transcribed as filler -> drop
    words, out = t.split(), []
    for w in words:                                  # "the the the the" -> "the"
        if len(out) >= 2 and out[-1] == w and out[-2] == w:
            continue
        out.append(w)
    return " ".join(out).strip()

def get_vad():
    global _vad
    if _vad is None:
        from vad import SileroVAD
        _vad = SileroVAD(threshold=float(os.getenv("VAD_THRESHOLD", "0.5")))
    return _vad

@app.on_event("startup")
async def _prewarm():
    """Load Whisper + VAD in a background thread at boot so the first WS connection
    doesn't block the event loop (which caused gateway handshake timeouts)."""
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, get_model)
    loop.run_in_executor(None, get_vad)

def _active_model():
    if STT_BACKEND in CLOUD_STT:
        c = CLOUD_STT[STT_BACKEND]
        return os.getenv(c["model_env"], c["model_default"])
    return os.getenv("WHISPER_MODEL", "small")

@app.get("/health")
def health():
    return {"ok": True, "service": "stt", "backend": STT_BACKEND, "model": _active_model()}

@app.get("/v1/usage_stt")
def usage_stt():
    """OpenAI STT usage for the Insights page: calls, minutes, and cost (USD + INR)."""
    return _usage_summary()

@app.post("/v1/usage_stt/reset")
def usage_reset(tenant=Depends(verify_api_key)):
    with _usage_lock:
        try:
            if os.path.exists(_USAGE_FILE):
                os.remove(_USAGE_FILE)
        except Exception:
            pass
    return {"reset": True}

@app.get("/v1/stt/backend")
def get_backend():
    """Which STT mode is active + which cloud providers have a key configured."""
    return {"backend": STT_BACKEND, "model": _active_model(),
            "openai_ready": bool(os.getenv("OPENAI_API_KEY")),
            "groq_ready": bool(os.getenv("GROQ_API_KEY")),
            "openai_model": os.getenv("OPENAI_STT_MODEL", "gpt-4o-transcribe"),
            "groq_model": os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")}

@app.post("/v1/stt/backend")
def set_backend(body: dict, tenant=Depends(verify_api_key)):
    """Switch STT mode at runtime (no restart): 'whisper' (self-hosted, free),
    'openai' (gpt-4o-transcribe), or 'groq' (Whisper large-v3-turbo, ~9x cheaper than OpenAI).
    The key stays server-side; only the mode changes."""
    global STT_BACKEND
    b = str(body.get("backend", "")).lower()
    if b not in ("whisper", "openai", "groq"):
        raise HTTPException(400, "backend must be 'whisper', 'openai', or 'groq'")
    if b in CLOUD_STT and not os.getenv(CLOUD_STT[b]["key"]):
        raise HTTPException(400, f"{CLOUD_STT[b]['key']} not set on the server")
    STT_BACKEND = b
    return {"backend": STT_BACKEND}

@app.post("/v1/stt")
async def batch_transcribe(file: UploadFile = File(...), tenant=Depends(verify_api_key)):
    """Batch: accepts wav/mp3/etc (ffmpeg-decodable)."""
    t0 = time.time()
    data = await file.read()
    if STT_BACKEND in CLOUD_STT:
        import httpx
        cfg = CLOUD_STT[STT_BACKEND]
        model = os.getenv(cfg["model_env"], cfg["model_default"])
        r = httpx.post(cfg["url"], headers={"Authorization": f"Bearer {os.getenv(cfg['key'],'')}"},
                       files={"file": ("audio.wav", data, "audio/wav")},
                       data={"model": model, "response_format": "text"}, timeout=60)
        r.raise_for_status()
        try:
            with wave.open(io.BytesIO(data)) as _w:
                secs = _w.getnframes() / _w.getframerate()
        except Exception:
            secs = 0.0
        _record_usage(model, secs)
        return {"text": r.text.strip(), "language": os.getenv("STT_LANG") or "auto",
                "duration_s": round(secs, 2), "latency_ms": int((time.time()-t0)*1000)}
    model = get_model()
    segments, info = model.transcribe(io.BytesIO(data), vad_filter=True)
    text = " ".join(s.text.strip() for s in segments)
    return {"text": text, "language": info.language,
            "duration_s": info.duration, "latency_ms": int((time.time()-t0)*1000)}

@app.websocket("/v1/stt/stream")
async def stream_transcribe(ws: WebSocket):
    """Streaming: binary PCM16 mono 16k frames in; JSON transcripts out.
    Buffers audio, runs VAD; on end-of-speech (silence gap) transcribes the utterance.
    Send text frame '{"event":"flush"}' to force-final, '{"event":"close"}' to end."""
    await ws.accept()
    # load off the event loop so accept() flushes immediately (no handshake timeout)
    loop = asyncio.get_event_loop()
    model = await loop.run_in_executor(None, get_model)
    vad = await loop.run_in_executor(None, get_vad)
    buf = np.zeros(0, dtype=np.float32)
    SR = 16000
    SILENCE_FLUSH_S = float(os.getenv("STT_SILENCE_FLUSH_S", "0.7"))
    PARTIAL_INTERVAL = float(os.getenv("STT_PARTIAL_INTERVAL_S", "1.0"))
    last_speech = time.time()
    last_partial = 0.0

    sess_lang = {"v": None}   # per-connection language override, set by {"event":"config"}

    def _do_transcribe(audio):
        audio = preprocess_audio(audio)   # OUR clean-up stage (DC/rumble removal + normalize)
        if STT_BACKEND in CLOUD_STT:
            return postprocess_text(cloud_transcribe(audio, STT_BACKEND, lang=sess_lang["v"]))
        m = get_model()   # dynamic so a runtime switch back to whisper loads the model on demand
        # anti-hallucination: vad_filter drops non-speech, condition_on_previous_text=False
        # stops runaway invented text, temperature=0 is deterministic, and the no-speech /
        # log-prob thresholds discard low-confidence guesses (Whisper's classic "Thank you."
        # random-phrase hallucinations on noise / near-silence).
        segments, info = m.transcribe(
            audio, language=sess_lang["v"] or os.getenv("STT_LANG") or None,
            initial_prompt=os.getenv("STT_PROMPT") or None,
            vad_filter=True, condition_on_previous_text=False, temperature=0.0,
            no_speech_threshold=0.6, log_prob_threshold=-1.0, compression_ratio_threshold=2.4)
        segs = [s for s in segments if getattr(s, "no_speech_prob", 0.0) < 0.6]
        return postprocess_text(" ".join(s.text.strip() for s in segs).strip())

    DUMP = os.getenv("STT_DEBUG_DUMP", "") == "1"
    dump_dir = os.getenv("VOICE_DIR", "./voices")
    PREROLL = int(SR * 0.3)          # keep 300ms before speech so the first word isn't clipped
    MIN_SPEECH_S = float(os.getenv("STT_MIN_SPEECH_S", "0.45"))  # ignore blips shorter than this
    # If the user clearly spoke (>= this) but we got NOTHING intelligible, it's mumble/gibberish/
    # cross-talk — the gateway should gently ask them to repeat. Below it, we stay silent (noise).
    UNCLEAR_MIN_SPEECH_S = float(os.getenv("STT_UNCLEAR_MIN_SPEECH_S", "0.7"))
    # Barge-in: announce "the user started talking" the moment we've heard this much REAL
    # speech in the current utterance. The gateway uses it to stop the agent mid-sentence.
    # High enough that residual echo / a cough doesn't cut the agent off, low enough to feel
    # instant (~a third of a second).
    SPEECH_START_S = float(os.getenv("STT_SPEECH_START_S", "0.35"))
    preroll = np.zeros(0, dtype=np.float32)
    in_utt = False
    speech_dur = 0.0                 # seconds of ACTUAL speech in the current utterance
    announced = False                # speech_start already sent for this utterance

    def _save_wav(audio, name):
        import wave
        try:
            os.makedirs(dump_dir, exist_ok=True)
            with wave.open(os.path.join(dump_dir, name), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
                w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
        except Exception:
            pass

    async def transcribe_and_send(final: bool, had_speech: bool = False):
        """Runs the (blocking) model in a thread so the receive loop keeps flowing.
        final=False emits a live 'partial' (text so far, buffer kept); final=True emits
        'final' and clears the buffer (end of the user's turn). If a final turn had real speech
        but produced no intelligible text, emit 'unclear' so the gateway can ask them to repeat."""
        nonlocal buf
        if len(buf) < SR // 4:  # <250ms — nothing meaningful yet
            if final:
                buf = np.zeros(0, dtype=np.float32)
            return
        audio = buf.copy()
        if final and DUMP:            # save exactly what Whisper hears, for quality inspection
            _save_wav(audio, "last_utterance.wav")
        t0 = time.time()
        text = await loop.run_in_executor(None, _do_transcribe, audio)
        if text:
            await ws.send_text(json.dumps({
                "type": "final" if final else "partial",
                "text": text, "latency_ms": int((time.time()-t0)*1000)}))
        elif final and had_speech:
            # they clearly spoke but nothing intelligible came back (mumble / gibberish / cross-talk).
            # Signal the gateway to gently re-prompt — WITHOUT inventing a sentence. Pure noise
            # (had_speech=False) is dropped silently instead.
            await ws.send_text(json.dumps({"type": "unclear"}))
        if final:
            buf = np.zeros(0, dtype=np.float32)

    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if "text" in msg and msg["text"]:
                ev = json.loads(msg["text"])
                if ev.get("event") == "flush":
                    await transcribe_and_send(final=True, had_speech=(speech_dur >= UNCLEAR_MIN_SPEECH_S))
                    in_utt = False; last_partial = 0.0; speech_dur = 0.0; announced = False
                elif ev.get("event") == "config":
                    # per-session settings from the gateway; language: en/hi/te ("" or "en" ->
                    # default). Whisper handles Hindi/Telugu natively — just needs to be told.
                    lang = str(ev.get("language") or "").strip().lower()
                    sess_lang["v"] = lang if lang and lang != "auto" else None
                elif ev.get("event") == "reset":
                    # discard whatever is buffered (echo/noise captured during the agent's turn)
                    buf = np.zeros(0, dtype=np.float32); in_utt = False; last_partial = 0.0
                    speech_dur = 0.0; announced = False
                elif ev.get("event") == "close":
                    await transcribe_and_send(final=True)
                    break
                continue
            frame = msg.get("bytes")
            if not frame:
                continue
            pcm = np.frombuffer(frame, dtype=np.int16).astype(np.float32) / 32768.0
            now = time.time()
            has = vad.has_speech(pcm)
            if has:
                if not in_utt:
                    # onset: seed with the pre-roll so the first word isn't clipped
                    buf = np.concatenate([preroll, pcm]); in_utt = True
                else:
                    buf = np.concatenate([buf, pcm])
                last_speech = now
                speech_dur += len(pcm) / SR
                if not announced and speech_dur >= SPEECH_START_S:
                    # confirmed real speech onset -> tell the gateway NOW (this is what lets the
                    # user interrupt the agent mid-sentence instead of waiting for the final).
                    announced = True
                    await ws.send_text(json.dumps({"type": "speech_start"}))
                # live partials re-transcribe the growing buffer. That's FREE on local Whisper,
                # but each one is a PAID call on a cloud backend — so only do partials on the
                # free local model. Cloud backends bill exactly once per utterance (the final).
                if (STT_BACKEND == "whisper"
                        and (now - last_partial) > PARTIAL_INTERVAL and len(buf) > int(SR * 0.4)):
                    await transcribe_and_send(final=False)
                    last_partial = time.time()
            elif in_utt:
                # mid-utterance pause: KEEP the audio contiguous (don't delete the gap / lose
                # words). Only finalize after sustained trailing silence = the user's turn ended.
                buf = np.concatenate([buf, pcm])
                if (now - last_speech) > SILENCE_FLUSH_S:
                    if speech_dur >= MIN_SPEECH_S:
                        await transcribe_and_send(final=True, had_speech=(speech_dur >= UNCLEAR_MIN_SPEECH_S))
                    else:
                        buf = np.zeros(0, dtype=np.float32)   # too little speech = noise blip, drop it
                    in_utt = False; last_partial = 0.0; speech_dur = 0.0; announced = False
            else:
                # idle: keep a rolling pre-roll of the most recent audio
                preroll = np.concatenate([preroll, pcm])[-PREROLL:]
    except Exception as e:
        try:
            await ws.send_text(json.dumps({"type": "error", "error": str(e)}))
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8001")))
