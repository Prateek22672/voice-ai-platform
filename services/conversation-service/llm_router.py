"""LLM Router — one interface, any model. litellm handles OpenAI/Anthropic/local(vLLM/Ollama).
Swap via LLM_MODEL env: 'claude-sonnet-4-6', 'gpt-4.1', 'ollama/llama3', 'hosted_vllm/qwen'..."""
import os
from typing import AsyncIterator

async def stream_completion(messages: list[dict], model: str | None = None) -> AsyncIterator[str]:
    """Yields text deltas. First token latency = what matters for voice."""
    import litellm
    model = model or os.getenv("LLM_MODEL", "claude-sonnet-4-6")
    resp = await litellm.acompletion(model=model, messages=messages, stream=True,
                                     max_tokens=int(os.getenv("LLM_MAX_TOKENS", "300")))
    async for chunk in resp:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

async def complete(messages: list[dict], model: str | None = None) -> str:
    parts = []
    async for d in stream_completion(messages, model):
        parts.append(d)
    return "".join(parts)
