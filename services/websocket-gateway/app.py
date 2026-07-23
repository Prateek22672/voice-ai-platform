"""WebSocket Gateway — single realtime entrypoint for browser + telephony bridge.
WS /v1/agent/stream : full-duplex voice agent session.
   Client sends: binary PCM16 mono 16kHz mic frames + JSON control {"event":"start","system_prompt":...}
   Server sends: binary PCM16 TTS audio + JSON events {"type":"transcript"|"agent_text"|"interrupt"|"done"}
Internally chains: stt-service (WS) -> conversation-service (SSE) -> tts-service (WS).
This is the only service the browser talks to.

FULL-DUPLEX + BARGE-IN: the mic is NEVER muted. Browser echo-cancellation keeps the agent's own
voice out of the mic stream, so the STT hears the user even while the agent is talking. The moment
STT confirms real speech onset ({"type":"speech_start"}), the gateway kills the in-flight LLM
generation and TTS stream and tells the client to flush its audio queue ({"type":"interrupt"}) —
the agent goes quiet mid-word, exactly like a human who's been talked over."""
import asyncio, json, os, random, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import httpx, websockets
from fastapi import FastAPI, WebSocket

app = FastAPI(title="websocket-gateway", version="1.1.0")

STT_WS  = os.getenv("STT_WS",  "ws://stt-service:8001/v1/stt/stream")
TTS_WS  = os.getenv("TTS_WS",  "ws://tts-service:8002/v1/tts/stream")
CONV_URL = os.getenv("CONV_URL", "http://conversation-service:8003")
GW_API   = os.getenv("GATEWAY_API", "http://api-gateway:8080")   # kill-switch + session metrics
API_KEY = os.getenv("INTERNAL_API_KEY", os.getenv("DEV_API_KEY", "dev-test-key"))
HDRS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

# Barge-in: user speech while the agent talks stops the agent instantly. On by default; set 0
# to fall back to the old "agent always finishes" behaviour (e.g. bad-AEC environments).
BARGE_IN = os.getenv("BARGE_IN", "1") == "1"

# Instant backchannel: a tiny human acknowledgement ("Mm-hmm", "Hmm, okay") plays the moment the
# user's turn ends, masking LLM+TTS think-time the way a real listener would. Synthesized once per
# (text, voice), cached as PCM. Variety matters — one repeated "Mm-hmm." sounds robotic fast.
FILLER_ENABLED = os.getenv("FILLER_ENABLED", "1") == "1"
FILLERS = [
    "Mm-hmm.", "Okay.", "Alright.", "Right.", "Hmm.",
    "Mmm, okay.", "Ohh, I see.", "Got it.", "Ah, okay.", "Mm-hmm, right.",
]
# After a question from the user, an acknowledgement sounds wrong ("Mm-hmm." to "what's the price?")
# — a short thinking sound fits better.
THINKING_FILLERS = ["Hmm.", "Mmm.", "Okay, so.", "Right, so.", "Let's see."]
_filler_cache: dict[tuple, bytes] = {}

def _pick_filler(user_text: str) -> str:
    t = (user_text or "").strip()
    if t.endswith("?") or t.lower().split(" ")[0] in (
            "what", "why", "how", "when", "where", "who", "can", "could", "do", "does", "is", "are"):
        return random.choice(THINKING_FILLERS)
    return random.choice(FILLERS)

async def _filler_pcm(text: str, voice: str = "") -> bytes:
    key = (text, voice)
    if key not in _filler_cache:
        try:
            async with websockets.connect(TTS_WS) as tts:
                await tts.send(json.dumps({"text": text, "voice": voice or None}))
                chunks = []
                async for msg in tts:
                    if isinstance(msg, bytes):
                        chunks.append(msg)
                    elif json.loads(msg).get("type") == "done":
                        break
                _filler_cache[key] = b"".join(chunks)
        except Exception:
            _filler_cache[key] = b""
    return _filler_cache[key]

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
    return {"ok": True, "service": "websocket-gateway", "barge_in": BARGE_IN}

@app.websocket("/v1/agent/stream")
async def agent_stream(ws: WebSocket):
    await ws.accept()
    session_id = None
    agent_turn = asyncio.Event()   # true for the WHOLE agent response (drives UI state)
    turn_task: asyncio.Task | None = None   # the in-flight agent turn — cancellable = barge-in
    interrupted_turns = 0          # metrics: how often the user barged in this session
    unclear_count = 0              # consecutive "spoke but unintelligible" turns (escalates re-prompt)
    last_reprompt = 0.0            # cooldown clock so we never nag on repeated background noise
    sess_turns = 0                 # metrics: completed agent turns this session
    sess_first_audio = []          # metrics: per-turn ms from transcript -> first agent audio
    session_voice = ""             # per-session TTS voice (from the start event); "" = platform default

    async def send_json(obj: dict):
        try:
            await ws.send_text(json.dumps(obj))
        except Exception:
            pass   # client went away mid-send; the receive loop will notice and clean up

    async with httpx.AsyncClient(timeout=60) as http:
        # ---- emergency kill-switch: refuse new sessions while the service is disabled ----
        try:
            r = await http.get(f"{GW_API}/v1/service_state", timeout=2)
            if r.status_code == 200 and not r.json().get("enabled", True):
                await send_json({"type": "error", "error": "Service temporarily disabled by admin"})
                await ws.close(); return
        except Exception:
            pass   # gateway unreachable -> fail open (don't block voice on a metrics hop)
        # report session start for the admin traffic panel (fire-and-forget)
        try:
            await http.post(f"{GW_API}/internal/voice", headers=HDRS,
                            json={"event": "start"}, timeout=2)
        except Exception:
            pass

        async def run_turn(text: str, echo: bool = True):
            """One agent turn: transcript -> conversation SSE -> per-sentence TTS -> audio out.
            Runs as a task so a barge-in can CANCEL it mid-stream; the finally block makes
            cancellation safe (TTS socket closed, state returned to listening) at any point.
            echo=False is used for the agent's opening greeting so no fake 'user' line is shown."""
            nonlocal session_id, sess_turns
            agent_turn.set()
            await send_json({"type": "state", "state": "agent"})   # UI: agent turn
            t_turn = time.time(); first_audio_ms = None
            tts = None                                    # ONE TTS connection reused for the turn
            try:
                if echo:
                    await send_json({"type": "transcript", "text": text})
                    if FILLER_ENABLED:
                        # instant acknowledgement while the real reply is being generated
                        pcm = await _filler_pcm(_pick_filler(text), session_voice)
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
                            await send_json({"type": "agent_text", "text": sentence})
                            if tts is None:               # open once, not per-sentence (saves ~100ms/sentence)
                                tts = await websockets.connect(TTS_WS)
                            await tts.send(json.dumps({"text": sentence,
                                                       "voice": session_voice or None}))
                            async for msg in tts:
                                if isinstance(msg, bytes):
                                    if first_audio_ms is None:
                                        first_audio_ms = int((time.time()-t_turn)*1000)
                                        print(f"[gw] first agent audio {first_audio_ms}ms after transcript", flush=True)
                                    await ws.send_bytes(msg)
                                else:
                                    d = json.loads(msg)
                                    if d.get("type") == "done":
                                        await send_json({"type": "audio_done",
                                                         "sample_rate": d.get("sample_rate", 24000)})
                                        break
                        elif ev.get("type") == "done":
                            await send_json({"type": "turn_done"})
            finally:
                if tts is not None:
                    try: await tts.close()
                    except Exception: pass
                sess_turns += 1                               # metrics: one completed agent turn
                if first_audio_ms is not None:
                    sess_first_audio.append(first_audio_ms)   # metrics: response latency
                agent_turn.clear()
                await send_json({"type": "state", "state": "listening"})

        async def run_line(line: str):
            """Speak a fixed line straight through TTS (no LLM) — used for re-prompts. Same
            cancellable-task shape as run_turn so it too can be barged-in."""
            agent_turn.set()
            await send_json({"type": "state", "state": "agent"})
            await send_json({"type": "agent_text", "text": line})
            tts = None
            try:
                tts = await websockets.connect(TTS_WS)
                await tts.send(json.dumps({"text": line, "voice": session_voice or None}))
                async for msg in tts:
                    if isinstance(msg, bytes):
                        await ws.send_bytes(msg)
                    else:
                        d = json.loads(msg)
                        if d.get("type") == "done":
                            await send_json({"type": "audio_done",
                                             "sample_rate": d.get("sample_rate", 24000)})
                            break
            finally:
                if tts is not None:
                    try: await tts.close()
                    except Exception: pass
                agent_turn.clear()
                await send_json({"type": "state", "state": "listening"})

        async def cancel_turn():
            """Barge-in: stop the agent NOW. Order matters for perceived latency —
            1. tell the client to flush its queued audio (silence is instant)
            2. flag the conversation service so the LLM stream aborts
            3. cancel the turn task (closes the TTS stream)"""
            nonlocal turn_task, interrupted_turns
            if turn_task is None or turn_task.done():
                turn_task = None
                return
            interrupted_turns += 1
            await send_json({"type": "interrupt"})
            if session_id:
                try:
                    await http.post(f"{CONV_URL}/v1/sessions/{session_id}/interrupt",
                                    headers=HDRS, timeout=2)
                except Exception:
                    pass
            turn_task.cancel()
            try:
                await turn_task
            except (asyncio.CancelledError, Exception):
                pass
            turn_task = None
            print("[gw] barge-in: agent turn cancelled", flush=True)

        async def handle_unclear():
            """User spoke but we couldn't understand — ask them to repeat (escalating), with a
            cooldown so background noise never turns into nagging. Never calls the LLM."""
            nonlocal unclear_count, last_reprompt, turn_task
            if not REPROMPT_ENABLED or agent_turn.is_set():
                return
            now = time.time()
            if now - last_reprompt < REPROMPT_COOLDOWN_S:
                return
            last_reprompt = now
            tier = min(unclear_count, len(REPROMPTS) - 1)   # escalate with each consecutive miss
            unclear_count += 1
            turn_task = asyncio.create_task(run_line(random.choice(REPROMPTS[tier])))

        try:
            stt = await websockets.connect(STT_WS)
        except Exception as e:
            await send_json({"type": "error", "error": f"stt connect: {e}"})
            await ws.close(); return

        async def stt_reader():
            """speech_start while agent talks -> barge-in; partials -> browser (display);
            finals -> a fresh agent turn (cancelling any turn still in flight)."""
            nonlocal unclear_count, turn_task
            async for msg in stt:
                d = json.loads(msg)
                if d.get("type") == "speech_start":
                    if BARGE_IN and agent_turn.is_set():
                        # user started talking over the agent -> shut the agent up instantly
                        await cancel_turn()
                elif d.get("type") == "partial" and d.get("text"):
                    # show words as the user speaks (ChatGPT/Claude-style live transcription)
                    await send_json({"type": "partial_transcript", "text": d["text"]})
                elif d.get("type") == "final" and d.get("text"):
                    unclear_count = 0               # understood the user -> reset the re-prompt escalation
                    # safety net: if a turn is somehow still running (e.g. barge-in disabled or
                    # speech_start missed), stop it before answering the new utterance
                    await cancel_turn()
                    turn_task = asyncio.create_task(run_turn(d["text"]))
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
                        session_voice = (ev.get("voice") or "").strip()   # per-session natural voice
                        r = await http.post(f"{CONV_URL}/v1/sessions", headers=HDRS,
                                            json={"system_prompt": ev.get("system_prompt", "")})
                        session_id = r.json()["session_id"]
                        await send_json({"type": "ready", "session_id": session_id})
                        # Optional: agent OPENS the conversation (greet + first question) instead of
                        # waiting for the candidate to speak first. Interview platforms want this.
                        if ev.get("greet"):
                            kickoff = ev.get("greeting_prompt") or \
                                "Greet the candidate warmly in one sentence, then ask your first question."
                            turn_task = asyncio.create_task(run_turn(kickoff, echo=False))
                    elif ev.get("event") == "close":
                        break
                elif msg.get("bytes"):
                    # FULL-DUPLEX: mic frames flow to STT even while the agent is speaking.
                    # Browser AEC keeps the agent's voice out; STT's confidence filters drop
                    # any residue — this is what makes interruption possible.
                    await stt.send(msg["bytes"])
        finally:
            reader.cancel()
            if turn_task is not None and not turn_task.done():
                turn_task.cancel()
            # report session end + its metrics for the admin traffic panel
            try:
                await http.post(f"{GW_API}/internal/voice", headers=HDRS,
                                json={"event": "end", "turns": sess_turns,
                                      "interrupted_turns": interrupted_turns,
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
