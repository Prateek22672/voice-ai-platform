"""Full-stack E2E: connect to gateway WS, stream a spoken question (espeak-generated),
verify transcript + agent text + audio bytes come back. Needs full compose stack + LLM key."""
import asyncio, json, os, subprocess, wave
import websockets

GW = os.getenv("GW_WS", "ws://localhost:8000/v1/agent/stream")

async def main():
    subprocess.run(["espeak-ng", "-w", "_q.wav", "hello can you hear me"], check=True)
    with wave.open("_q.wav") as w:
        sr, pcm = w.getframerate(), w.readframes(w.getnframes())
    # naive resample to 16k if needed
    if sr != 16000:
        import audioop
        pcm, _ = audioop.ratecv(pcm, 2, 1, sr, 16000, None)
    got = {"transcript": False, "agent_text": False, "audio": False}
    async with websockets.connect(GW) as ws:
        await ws.send(json.dumps({"event": "start",
            "system_prompt": "Reply with one short sentence."}))
        # stream in 20ms frames + trailing silence to trigger VAD flush
        for i in range(0, len(pcm), 640):
            await ws.send(pcm[i:i+640]); await asyncio.sleep(0.02)
        await ws.send(b"\x00" * 640 * 50)
        try:
            while not all(got.values()):
                msg = await asyncio.wait_for(ws.recv(), timeout=30)
                if isinstance(msg, bytes):
                    got["audio"] = True
                else:
                    d = json.loads(msg)
                    if d.get("type") == "transcript": got["transcript"] = True; print("transcript:", d["text"])
                    if d.get("type") == "agent_text": got["agent_text"] = True; print("agent:", d["text"])
        except asyncio.TimeoutError:
            pass
    print("RESULT:", got)
    assert all(got.values()), "E2E incomplete"
    print("E2E PASS")

if __name__ == "__main__":
    asyncio.run(main())
