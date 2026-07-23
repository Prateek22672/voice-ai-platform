"""LLM Router — one interface, any model. litellm handles OpenAI/Anthropic/local(vLLM/Ollama).
Swap via LLM_MODEL env: 'claude-sonnet-4-6', 'gpt-4.1', 'ollama/llama3', 'hosted_vllm/qwen'...
Every call's token usage is logged to VOICE_DIR/llm_usage.json (powers the Insights page)."""
import json, os, threading
from typing import AsyncIterator

# ---- usage tracking: real token counts per call, persisted like the STT counter ----
_lock = threading.Lock()
_USAGE_FILE = os.path.join(os.getenv("VOICE_DIR", "."), "llm_usage.json")

def _record(model: str, prompt_tokens: int, completion_tokens: int, measured: bool):
    """measured=True -> token counts came from the provider's API response (exact).
    measured=False -> counted locally with the tokenizer (very close, but flagged)."""
    with _lock:
        try:
            data = json.load(open(_USAGE_FILE)) if os.path.exists(_USAGE_FILE) else {}
        except Exception:
            data = {}
        m = data.setdefault(model, {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                    "estimated_calls": 0})
        m["calls"] += 1
        m["prompt_tokens"] += int(prompt_tokens or 0)
        m["completion_tokens"] += int(completion_tokens or 0)
        if not measured:
            m["estimated_calls"] = m.get("estimated_calls", 0) + 1
        try:
            json.dump(data, open(_USAGE_FILE, "w"))
        except Exception:
            pass

async def stream_completion(messages: list[dict], model: str | None = None) -> AsyncIterator[str]:
    """Yields text deltas. First token latency = what matters for voice."""
    import litellm
    model = model or os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    # 220 tokens ≈ 4-5 spoken sentences — enough for any conversational turn; the sentence cap
    # in conversation-service cuts earlier anyway. (Was 300, which allowed paragraph replies.)
    kwargs = dict(model=model, messages=messages, stream=True,
                  max_tokens=int(os.getenv("LLM_MAX_TOKENS", "220")))
    try:
        # ask the provider to report exact token usage on the final stream chunk
        resp = await litellm.acompletion(**kwargs, stream_options={"include_usage": True})
    except Exception:
        resp = await litellm.acompletion(**kwargs)   # provider rejects stream_options -> plain
    usage = None
    parts = []
    async for chunk in resp:
        u = getattr(chunk, "usage", None)
        if u and getattr(u, "completion_tokens", None) is not None:
            usage = u                                 # exact billing numbers from the API
        if not chunk.choices:                          # the usage-only final chunk has no choices
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            parts.append(delta)
            yield delta
    # record usage: exact if the API returned it, else tokenizer-counted (flagged as estimated)
    try:
        if usage:
            _record(model, getattr(usage, "prompt_tokens", 0) or 0,
                    getattr(usage, "completion_tokens", 0) or 0, measured=True)
        else:
            out = "".join(parts)
            try:
                p = litellm.token_counter(model=model, messages=messages)
                c = litellm.token_counter(model=model, text=out)
            except Exception:
                p = sum(len(str(m.get("content", ""))) for m in messages) // 4
                c = len(out) // 4
            _record(model, p, c, measured=False)
    except Exception:
        pass

async def complete(messages: list[dict], model: str | None = None) -> str:
    parts = []
    async for d in stream_completion(messages, model):
        parts.append(d)
    return "".join(parts)
