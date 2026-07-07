"""WebSocket Gateway — single realtime entrypoint for browser + telephony bridge.
WS /v1/agent/stream : full-duplex voice agent session.
   Client sends: binary PCM16 mono 16kHz mic frames + JSON control {"event":"start","system_prompt":...}
   Server sends: binary PCM16 TTS audio + JSON events {"type":"transcript"|"agent_text"|"done"}
Internally chains: stt-service (WS) -> conversation-service (SSE) -> tts-service (WS).
This is the only service the browser talks to."""
import asyncio, json, os, random, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import httpx, websockets
from fastapi import FastAPI, WebSocket

app = FastAPI(title="websocket-gateway", version="1.0.0")

STT_WS  = os.getenv("STT_WS",  "ws://stt-service:8001/v1/stt/stream")
TTS_WS  = os.getenv("TTS_WS",  "ws://tts-service:8002/v1/tts/stream")
CONV_URL = os.getenv("CONV_URL", "http://conversation-service:8003")
GW_API   = os.getenv("GATEWAY_API", "http://api-gateway:8080")   # kill-switch + session metrics
API_KEY = os.getenv("INTERNAL_API_KEY", os.getenv("DEV_API_KEY", "dev-test-key"))
HDRS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Instant backchannel: a tiny acknowledgement ("Mm-hmm.") plays the moment the user's turn ends,
# masking LLM+TTS think-time the way a human interviewer would. Synthesized once, cached as PCM.
FILLER_ENABLED = os.getenv("FILLER_ENABLED", "1") == "1"
FILLERS = ["Mm-hmm.", "Okay.", "Alright.", "Right."]
_filler_cache: dict[str, bytes] = {}

async def _filler_pcm(text: str) -> bytes:
    if text not in _filler_cache:
        try:
            async with websockets.connect(TTS_WS) as tts:
                await tts.send(json.dumps({"text": text}))
                chunks = []
                async for msg in tts:
                    if isinstance(msg, bytes):
                        chunks.append(msg)
                    elif json.loads(msg).get("type") == "done":
                        break
                _filler_cache[text] = b"".join(chunks)
        except Exception:
            _filler_cache[text] = b""
    return _filler_cache[text]

# Spoken re-prompts for when the user clearly spoke but nothing intelligible came back. Escalates
# across consecutive misses; a cooldown stops it nagging on noise; resets on the next good transcript.
REPROMPT_ENABLED = os.getenv("REPROMPT_ENABLED", "1") == "1"
REPROMPT_COOLDOWN_S = float(os.getenv("REPROMPT_COOLDOWN_S", "3.0"))
REPROMPTS = [
    ["Sorry, I didn't quite catch that — could you say it again?",
     "Hmm, I missed that. Could you repeat it?",
     "Sorry, could you say that once more?"],
    ["Still didn't catch that — could you speak a little louder?",
     "I'm having trouble hearing you. A bit louder, please?"],
    ["I'm still having trouble hearing you clearly. Could you check your microphone and try again?"],
]

@app.get("/health")
def health():
    return {"ok": True, "service": "websocket-gateway"}

@app.websocket("/v1/agent/stream")
async def agent_stream(ws: WebSocket):
    await ws.accept()
    session_id = None
    speaking = asyncio.Event()     # true while TTS audio is being sent
    agent_turn = asyncio.Event()   # true for the WHOLE agent response — mic is paused (half-duplex)
    unclear_count = 0              # consecutive "spoke but unintelligible" turns (escalates re-prompt)
    last_reprompt = 0.0            # cooldown clock so we never nag on repeated background noise
    sess_turns = 0                 # metrics: completed agent turns this session
    sess_first_audio = []          # metrics: per-turn ms from transcript -> first agent audio

    async with httpx.AsyncClient(timeout=60) as http:
        # ---- emergency kill-switch: refuse new sessions while the service is disabled ----
        try:
            r = await http.get(f"{GW_API}/v1/service_state", timeout=2)
            if r.status_code == 200 and not r.json().get("enabled", True):
                await ws.send_text(json.dumps({"type": "error",
                                               "error": "Service temporarily disabled by admin"}))
                await ws.close(); return
        except Exception:
            pass   # gateway unreachable -> fail open (don't block voice on a metrics hop)
        # report session start for the admin traffic panel (fire-and-forget)
        try:
            await http.post(f"{GW_API}/internal/voice", headers=HDRS,
                            json={"event": "start"}, timeout=2)
        except Exception:
            pass
        async def handle_transcript(text: str, echo: bool = True):
            """final transcript -> conversation SSE -> per-sentence TTS -> audio to client.
            The mic is muted for the whole turn so the agent never transcribes its own voice.
            echo=False is used for the agent's opening greeting so no fake 'user' line is shown."""
            nonlocal session_id, sess_turns
            agent_turn.set()
            await ws.send_text(json.dumps({"type": "state", "state": "agent"}))  # UI: agent turn
            t_turn = time.time(); first_audio_ms = None
            tts = None                                    # ONE TTS connection reused for the turn
            try:
                if echo:
                    await ws.send_text(json.dumps({"type": "transcript", "text": text}))
                    if FILLER_ENABLED:
                        # instant acknowledgement while the real reply is being generated
                        pcm = await _filler_pcm(random.choice(FILLERS))
                        if pcm:
                            await ws.send_bytes(pcm)
                async with http.stream("POST", f"{CONV_URL}/v1/sessions/{session_id}/turn",
                                       headers=HDRS, json={"text": text}) as resp:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        ev = json.loads(line[6:])
                        if ev.get("type") == "sentence":
                            sentence = ev["sentence"]
                            await ws.send_text(json.dumps({"type": "agent_text", "text": sentence}))
                            speaking.set()
                            if tts is None:               # open once, not per-sentence (saves ~100ms/sentence)
                                tts = await websockets.connect(TTS_WS)
                            await tts.send(json.dumps({"text": sentence}))
                            async for msg in tts:
                                if isinstance(msg, bytes):
                                    if first_audio_ms is None:
                                        first_audio_ms = int((time.time()-t_turn)*1000)
                                        print(f"[gw] first agent audio {first_audio_ms}ms after transcript", flush=True)
                                    await ws.send_bytes(msg)
                                else:
                                    d = json.loads(msg)
                                    if d.get("type") == "done":
                                        await ws.send_text(json.dumps(
                                            {"type": "audio_done",
                                             "sample_rate": d.get("sample_rate", 24000)}))
                                        break
                            speaking.clear()
                        elif ev.get("type") == "done":
                            await ws.send_text(json.dumps({"type": "turn_done"}))
            finally:
                if tts is not None:
                    try: await tts.close()
                    except Exception: pass
                sess_turns += 1                               # metrics: one completed agent turn
                if first_audio_ms is not None:
                    sess_first_audio.append(first_audio_ms)   # metrics: response latency
                # discard anything the STT buffered during the agent's turn (echo/noise), then
                # reopen the mic and tell the UI it's the user's turn.
                try:
                    await stt.send(json.dumps({"event": "reset"}))
                except Exception:
                    pass
                agent_turn.clear()
                await ws.send_text(json.dumps({"type": "state", "state": "listening"}))

        async def speak_line(line: str):
            """Speak a fixed line straight through TTS (no LLM) — used for re-prompts. Mirrors the
            agent-turn / half-duplex / stt-reset handling of a normal turn so it can't self-transcribe."""
            agent_turn.set()
            await ws.send_text(json.dumps({"type": "state", "state": "agent"}))
            await ws.send_text(json.dumps({"type": "agent_text", "text": line}))
            tts = None
            try:
                tts = await websockets.connect(TTS_WS)
                await tts.send(json.dumps({"text": line}))
                async for msg in tts:
                    if isinstance(msg, bytes):
                        await ws.send_bytes(msg)
                    else:
                        d = json.loads(msg)
                        if d.get("type") == "done":
                            await ws.send_text(json.dumps(
                                {"type": "audio_done", "sample_rate": d.get("sample_rate", 24000)}))
                            break
            finally:
                if tts is not None:
                    try: await tts.close()
                    except Exception: pass
                try:
                    await stt.send(json.dumps({"event": "reset"}))
                except Exception:
                    pass
                agent_turn.clear()
                await ws.send_text(json.dumps({"type": "state", "state": "listening"}))

        async def handle_unclear():
            """User spoke but we couldn't understand — ask them to repeat (escalating), with a
            cooldown so background noise never turns into nagging. Never calls the LLM."""
            nonlocal unclear_count, last_reprompt
            if not REPROMPT_ENABLED or agent_turn.is_set():
                return
            now = time.time()
            if now - last_reprompt < REPROMPT_COOLDOWN_S:
                return
            last_reprompt = now
            tier = min(unclear_count, len(REPROMPTS) - 1)   # escalate with each consecutive miss
            unclear_count += 1
            await speak_line(random.choice(REPROMPTS[tier]))

        try:
            stt = await websockets.connect(STT_WS)
        except Exception as e:
            await ws.send_text(json.dumps({"type": "error", "error": f"stt connect: {e}"}))
            await ws.close(); return

        async def stt_reader():
            """live partials -> browser (display only); finals -> conversation pipeline"""
            nonlocal unclear_count
            async for msg in stt:
                d = json.loads(msg)
                if d.get("type") == "partial" and d.get("text"):
                    # show words as the user speaks (ChatGPT/Claude-style live transcription)
                    await ws.send_text(json.dumps({"type": "partial_transcript", "text": d["text"]}))
                elif d.get("type") == "final" and d.get("text"):
                    unclear_count = 0               # understood the user -> reset the re-prompt escalation
                    if speaking.is_set() and session_id:
                        # user spoke over agent -> barge-in: kill current generation
                        await http.post(f"{CONV_URL}/v1/sessions/{session_id}/interrupt",
                                        headers=HDRS)
                    await handle_transcript(d["text"])
                elif d.get("type") == "unclear":
                    # spoke, but nothing intelligible -> gently ask to repeat (no LLM, no invented text)
                    await handle_unclear()

        reader = asyncio.create_task(stt_reader())
        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                if msg.get("text"):
                    ev = json.loads(msg["text"])
                    if ev.get("event") == "start":
                        r = await http.post(f"{CONV_URL}/v1/sessions", headers=HDRS,
                                            json={"system_prompt": ev.get("system_prompt", "")})
                        session_id = r.json()["session_id"]
                        await ws.send_text(json.dumps({"type": "ready", "session_id": session_id}))
                        # Optional: agent OPENS the conversation (greet + first question) instead of
                        # waiting for the candidate to speak first. Interview platforms want this.
                        if ev.get("greet"):
                            kickoff = ev.get("greeting_prompt") or \
                                "Greet the candidate warmly in one sentence, then ask your first question."
                            asyncio.create_task(handle_transcript(kickoff, echo=False))
                    elif ev.get("event") == "close":
                        break
                elif msg.get("bytes"):
                    if not agent_turn.is_set():     # half-duplex: ignore mic while agent speaks
                        await stt.send(msg["bytes"])   # mic audio -> STT
        finally:
            reader.cancel()
            # report session end + its metrics for the admin traffic panel
            try:
                await http.post(f"{GW_API}/internal/voice", headers=HDRS,
                                json={"event": "end", "turns": sess_turns,
                                      "first_audio_ms": sess_first_audio}, timeout=2)
            except Exception:
                pass
            try: await stt.close()
            except Exception: pass
            try: await ws.close()
            except Exception: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
