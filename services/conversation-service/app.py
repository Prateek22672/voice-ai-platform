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

# CORS so the dashboard can read /v1/usage_llm directly (same pattern as stt-service).
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"], allow_credentials=False)

_mem = None

# ---- LLM billing rates: USD per 1M tokens (input, output) — provider list prices ----
LLM_RATES_PER_MTOK = {
    "llama-3.3-70b-versatile": (0.59, 0.79),   # Groq
    "llama-3.1-8b-instant":    (0.05, 0.08),   # Groq
    "gpt-4o-mini":             (0.15, 0.60),   # OpenAI
    "gpt-4o":                  (2.50, 10.00),  # OpenAI
}

def _llm_rate(model: str):
    for key, rate in LLM_RATES_PER_MTOK.items():
        if model.endswith(key) or key in model:
            return rate
    return (0.59, 0.79)   # unknown -> assume Groq 70B so we never under-report

@app.get("/v1/usage_llm")
def usage_llm():
    """Real LLM usage for the Insights page: every call + its token counts are logged by
    llm_router; cost = measured tokens x official list price."""
    import json as _json
    path = os.path.join(os.getenv("VOICE_DIR", "."), "llm_usage.json")
    try:
        data = _json.load(open(path)) if os.path.exists(path) else {}
    except Exception:
        data = {}
    total_cost, total_calls, total_p, total_c, est_calls, by = 0.0, 0, 0, 0, 0, []
    for model, v in data.items():
        rin, rout = _llm_rate(model)
        cost = v.get("prompt_tokens", 0) / 1e6 * rin + v.get("completion_tokens", 0) / 1e6 * rout
        total_cost += cost
        total_calls += v.get("calls", 0)
        total_p += v.get("prompt_tokens", 0)
        total_c += v.get("completion_tokens", 0)
        est_calls += v.get("estimated_calls", 0)
        by.append({"model": model, "calls": v.get("calls", 0),
                   "prompt_tokens": v.get("prompt_tokens", 0),
                   "completion_tokens": v.get("completion_tokens", 0),
                   "estimated_calls": v.get("estimated_calls", 0),
                   "cost_usd": round(cost, 5)})
    return {"total_calls": total_calls, "prompt_tokens": total_p, "completion_tokens": total_c,
            "estimated_calls": est_calls, "est_cost_usd": round(total_cost, 5),
            "usd_inr": 85, "est_cost_inr": round(total_cost * 85, 3),
            "model": os.getenv("LLM_MODEL", ""), "by_model": by}

@app.post("/v1/usage_llm/reset")
def usage_llm_reset(tenant=Depends(verify_api_key)):
    path = os.path.join(os.getenv("VOICE_DIR", "."), "llm_usage.json")
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    return {"reset": True}

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
    # Latency trick: the FIRST sentence gates time-to-first-audio (it must be fully synthesized
    # before the caller hears anything). A short opener = the agent starts speaking sooner.
    if os.getenv("LLM_STYLE_HINT", "1") == "1":
        system += (" Important speaking style: open every reply with a very short first "
                   "sentence (under 8 words), then continue naturally.")
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
