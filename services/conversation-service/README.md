# conversation-service
Orchestrator: memory (Redis) + LLM router (litellm) + sentence streaming + barge-in.

## Run standalone
```bash
pip install -r requirements.txt
# needs Redis: docker run -d -p 6379:6379 redis:7
DEV_API_KEY=dev-test-key REDIS_URL=redis://localhost:6379/0 \
  ANTHROPIC_API_KEY=sk-... LLM_MODEL=claude-sonnet-4-6 python app.py
```

## Test
```bash
python test_standalone.py    # needs real LLM key OR set LLM_MODEL to a local model
```

## Design
- SSE sentence stream: TTS starts on sentence 1 while LLM still generating sentence 3.
- Barge-in: `/interrupt` sets Redis flag; stream aborts mid-generation.
- Swap models with `LLM_MODEL` — any litellm string (Anthropic/OpenAI/Ollama/vLLM).
