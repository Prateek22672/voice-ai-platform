"""Conversation Service — the brain. Transcript in -> LLM (streamed) -> sentences out to TTS.
POST /v1/sessions               : create session with system prompt (agent persona)
POST /v1/sessions/{id}/turn     : user transcript in -> streamed sentence chunks out (SSE)
Barge-in: POST /v1/sessions/{id}/interrupt sets a Redis flag; generation loop checks + aborts.
Sentences flush to TTS as soon as each completes — never wait for full LLM response."""
import asyncio, json, os, re, sys, time, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from fastapi import FastAPI, Depends, HTTPException
from fastapi.responses import StreamingResponse
from shared.auth import verify_api_key
from llm_router import stream_completion
from memory import ConversationMemory

app = FastAPI(title="conversation-service", version="1.0.0")
_mem = None

def mem() -> ConversationMemory:
    global _mem
    if _mem is None:
        _mem = ConversationMemory()
    return _mem

@app.get("/health")
def health():
    return {"ok": True, "service": "conversation", "model": os.getenv("LLM_MODEL", "claude-sonnet-4-6")}

@app.post("/v1/sessions")
async def create_session(body: dict, tenant=Depends(verify_api_key)):
    sid = str(uuid.uuid4())
    system = body.get("system_prompt",
        "You are a helpful voice assistant. Keep replies short and conversational — "
        "1-3 sentences. You are speaking aloud, so no markdown, no lists.")
    await mem().init_session(sid, system)
    return {"session_id": sid}

@app.post("/v1/sessions/{sid}/interrupt")
async def interrupt(sid: str, tenant=Depends(verify_api_key)):
    await mem().r.set(f"conv:{sid}:interrupt", "1", ex=10)
    return {"ok": True}

@app.post("/v1/sessions/{sid}/turn")
async def turn(sid: str, body: dict, tenant=Depends(verify_api_key)):
    """SSE stream of sentence chunks: data: {"sentence": "...", "first_token_ms": N}"""
    user_text = body.get("text", "").strip()
    if not user_text:
        raise HTTPException(400, "text required")
    m = mem()
    await m.r.delete(f"conv:{sid}:interrupt")
    await m.add_turn(sid, "user", user_text)
    messages = await m.get_messages(sid)
    if len(messages) == 0:
        raise HTTPException(404, "session not found or expired")

    async def gen():
        t0 = time.time()
        buf, full, first_ms = "", [], None
        try:
            async for delta in stream_completion(messages):
                if first_ms is None:
                    first_ms = int((time.time()-t0)*1000)
                if await m.r.get(f"conv:{sid}:interrupt"):
                    yield f'data: {json.dumps({"type":"interrupted"})}\n\n'
                    break
                buf += delta
                full.append(delta)
                # flush complete sentences immediately for TTS
                while True:
                    match = re.search(r"^(.*?[.!?])(\s+|$)", buf)
                    if not match:
                        break
                    sentence = match.group(1).strip()
                    buf = buf[match.end():]
                    if sentence:
                        yield f'data: {json.dumps({"type":"sentence","sentence":sentence,"first_token_ms":first_ms})}\n\n'
            if buf.strip():
                yield f'data: {json.dumps({"type":"sentence","sentence":buf.strip(),"first_token_ms":first_ms})}\n\n'
            yield f'data: {json.dumps({"type":"done"})}\n\n'
        finally:
            text = "".join(full).strip()
            if text:
                await m.add_turn(sid, "assistant", text)

    return StreamingResponse(gen(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8003")))
