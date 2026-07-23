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

# Spoken-style contract, appended to EVERY system prompt (default AND custom). Custom prompts
# used to bypass the brevity rules entirely — that's where the giant-paragraph replies came from.
# This is the "sound like a person, not a bot" layer: a support EXECUTIVE on a call, active
# listening, no AI-flavored phrasing anywhere.
AGENT_NAME = os.getenv("AGENT_NAME", "")   # e.g. "Priya" — used in the persona line below
NATURAL_STYLE = (
    " CRITICAL voice-call style rules: You are a real customer support executive talking OUT LOUD "
    "on a live phone call, not writing. NEVER describe yourself as an AI, assistant, bot, virtual "
    "agent, or language model, and never use bot phrases like 'How may I assist you today', 'As "
    "an AI', or 'I apologize for the inconvenience'. Introduce yourself only by name and role"
    + (f" (you are {AGENT_NAME}, an executive on the support team)" if AGENT_NAME else
       " (an executive on the support team)") +
    " — for example 'I'm from the support team, I'll sort this out for you.' If someone directly "
    "asks whether you're an AI or a human, don't argue and don't lie — give one short casual "
    "honest line and get right back to helping them. "
    "Show ACTIVE LISTENING like a real person: often (not every single turn) start with a small "
    "reaction to what they just said — 'Hmm,', 'Okay,', 'Ohh right,', 'Ah, got it.', 'Oh no,', "
    "'Nice!' — matched to their mood; sympathize in one short phrase when they have a problem. "
    "Use contractions and everyday words, vary how you start sentences, and occasionally a "
    "natural filler like 'you know' or 'actually'. Keep every reply to two or three short spoken "
    "sentences, then stop and let them talk — never a paragraph, never a list. Ask at most one "
    "question per turn. Absolutely no markdown, bullet points, headings, or emojis — only plain "
    "speakable words. Only go longer if they explicitly ask for detail, and even then pause "
    "after a few sentences."
)

# Language rule appended per session ("language" in the create-session body: en | hi | te).
LANG_STYLE = {
    "hi": (" IMPORTANT: Speak ONLY in natural, everyday conversational Hindi, written in "
           "Devanagari script — the way a friendly Indian support executive talks on the phone. "
           "Common English words Indians mix in naturally (okay, order, service, refund) are "
           "fine. Write numbers as words."),
    "te": (" IMPORTANT: Speak ONLY in natural, everyday conversational Telugu, written in Telugu "
           "script — the way a friendly Telugu support executive talks on the phone. Common "
           "English words people mix in naturally (okay, order, service) are fine. Write "
           "numbers as words."),
}

@app.post("/v1/sessions")
async def create_session(body: dict, tenant=Depends(verify_api_key)):
    sid = str(uuid.uuid4())
    system = body.get("system_prompt") or (
        "You are a friendly, capable customer support executive on a phone call. Help the caller "
        "with whatever they need, briefly and warmly.")
    if os.getenv("LLM_NATURAL_STYLE", "1") == "1":
        system += NATURAL_STYLE
    lang = (body.get("language") or "en").lower()
    system += LANG_STYLE.get(lang, "")
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

    # Hard backstop against paragraph-length replies: stop streaming after this many spoken
    # sentences even if the model keeps going. The style prompt asks for 2-3; this enforces it.
    max_sentences = int(os.getenv("LLM_MAX_SENTENCES", "4"))

    async def gen():
        t0 = time.time()
        buf, first_ms = "", None
        spoken = []            # sentences actually sent to TTS — this is what goes into memory
        interrupted = False
        try:
            async for delta in stream_completion(messages):
                if first_ms is None:
                    first_ms = int((time.time()-t0)*1000)
                if await m.r.get(f"conv:{sid}:interrupt"):
                    interrupted = True
                    yield f'data: {json.dumps({"type":"interrupted"})}\n\n'
                    break
                buf += delta
                # flush complete sentences immediately for TTS (never past the cap)
                # (। = Hindi danda — without it Hindi replies would never flush mid-stream)
                while len(spoken) < max_sentences:
                    match = re.search(r"^(.*?[.!?।])(\s+|$)", buf)
                    if not match:
                        break
                    sentence = match.group(1).strip()
                    buf = buf[match.end():]
                    if sentence:
                        spoken.append(sentence)
                        yield f'data: {json.dumps({"type":"sentence","sentence":sentence,"first_token_ms":first_ms})}\n\n'
                if len(spoken) >= max_sentences:
                    break   # backstop: reply is long enough — cut cleanly at a sentence boundary
            if not interrupted and len(spoken) < max_sentences and buf.strip():
                spoken.append(buf.strip())
                yield f'data: {json.dumps({"type":"sentence","sentence":buf.strip(),"first_token_ms":first_ms})}\n\n'
            yield f'data: {json.dumps({"type":"done"})}\n\n'
        finally:
            # Memory holds only what was actually SPOKEN. On barge-in, mark the cut so the
            # model knows it was interrupted and can pick up naturally instead of repeating.
            # (A barge-in usually closes this SSE stream before the loop sees the Redis flag,
            # so re-check it here — otherwise the marker would almost never be recorded.)
            if not interrupted:
                try:
                    interrupted = bool(await m.r.get(f"conv:{sid}:interrupt"))
                except Exception:
                    pass
            text = " ".join(spoken).strip()
            if interrupted:
                text = (text + " —").strip() if text else ""
                if text:
                    text += " [the user interrupted me here, so I stopped talking]"
            if text:
                await m.add_turn(sid, "assistant", text)

    return StreamingResponse(gen(), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8003")))
