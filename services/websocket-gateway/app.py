"""WebSocket Gateway — single realtime entrypoint for browser + telephony bridge.
WS /v1/agent/stream : full-duplex voice agent session.
   Client sends: binary PCM16 mono 16kHz mic frames + JSON control {"event":"start","system_prompt":...}
   Server sends: binary PCM16 TTS audio + JSON events {"type":"transcript"|"agent_text"|"done"}
Internally chains: stt-service (WS) -> conversation-service (SSE) -> tts-service (WS).
This is the only service the browser talks to."""
import asyncio, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
import httpx, websockets
from fastapi import FastAPI, WebSocket

app = FastAPI(title="websocket-gateway", version="1.0.0")

STT_WS  = os.getenv("STT_WS",  "ws://stt-service:8001/v1/stt/stream")
TTS_WS  = os.getenv("TTS_WS",  "ws://tts-service:8002/v1/tts/stream")
CONV_URL = os.getenv("CONV_URL", "http://conversation-service:8003")
API_KEY = os.getenv("INTERNAL_API_KEY", os.getenv("DEV_API_KEY", "dev-test-key"))
HDRS = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

@app.get("/health")
def health():
    return {"ok": True, "service": "websocket-gateway"}

@app.websocket("/v1/agent/stream")
async def agent_stream(ws: WebSocket):
    await ws.accept()
    session_id = None
    speaking = asyncio.Event()     # true while TTS audio is being sent
    agent_turn = asyncio.Event()   # true for the WHOLE agent response — mic is paused (half-duplex)

    async with httpx.AsyncClient(timeout=60) as http:
        async def handle_transcript(text: str):
            """final transcript -> conversation SSE -> per-sentence TTS -> audio to client.
            The mic is muted for the whole turn so the agent never transcribes its own voice."""
            nonlocal session_id
            agent_turn.set()
            await ws.send_text(json.dumps({"type": "state", "state": "agent"}))  # UI: agent turn
            try:
                await ws.send_text(json.dumps({"type": "transcript", "text": text}))
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
                            try:
                                async with websockets.connect(TTS_WS) as tts:
                                    await tts.send(json.dumps({"text": sentence}))
                                    async for msg in tts:
                                        if isinstance(msg, bytes):
                                            await ws.send_bytes(msg)
                                        else:
                                            d = json.loads(msg)
                                            if d.get("type") == "done":
                                                await ws.send_text(json.dumps(
                                                    {"type": "audio_done",
                                                     "sample_rate": d.get("sample_rate", 24000)}))
                                                break
                            finally:
                                speaking.clear()
                        elif ev.get("type") == "done":
                            await ws.send_text(json.dumps({"type": "turn_done"}))
            finally:
                # discard anything the STT buffered during the agent's turn (echo/noise), then
                # reopen the mic and tell the UI it's the user's turn.
                try:
                    await stt.send(json.dumps({"event": "reset"}))
                except Exception:
                    pass
                agent_turn.clear()
                await ws.send_text(json.dumps({"type": "state", "state": "listening"}))

        try:
            stt = await websockets.connect(STT_WS)
        except Exception as e:
            await ws.send_text(json.dumps({"type": "error", "error": f"stt connect: {e}"}))
            await ws.close(); return

        async def stt_reader():
            """live partials -> browser (display only); finals -> conversation pipeline"""
            async for msg in stt:
                d = json.loads(msg)
                if d.get("type") == "partial" and d.get("text"):
                    # show words as the user speaks (ChatGPT/Claude-style live transcription)
                    await ws.send_text(json.dumps({"type": "partial_transcript", "text": d["text"]}))
                elif d.get("type") == "final" and d.get("text"):
                    if speaking.is_set() and session_id:
                        # user spoke over agent -> barge-in: kill current generation
                        await http.post(f"{CONV_URL}/v1/sessions/{session_id}/interrupt",
                                        headers=HDRS)
                    await handle_transcript(d["text"])

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
                    elif ev.get("event") == "close":
                        break
                elif msg.get("bytes"):
                    if not agent_turn.is_set():     # half-duplex: ignore mic while agent speaks
                        await stt.send(msg["bytes"])   # mic audio -> STT
        finally:
            reader.cancel()
            try: await stt.close()
            except Exception: pass
            try: await ws.close()
            except Exception: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
