# tts-service
Streaming text-to-speech, ElevenLabs-shaped API, pluggable model backends.

## Backends (set `TTS_BACKEND`)
| Backend | Quality | First-chunk latency | Cloning | Hardware |
|---|---|---|---|---|
| kokoro | Very good | ~100-300ms GPU / ~1s CPU | No | CPU OK, GPU fast |
| f5tts | Best OSS naturalness | ~200-500ms GPU | Yes (zero-shot) | GPU required |
| cosyvoice | Excellent multilingual | ~200-400ms GPU (native streaming) | Yes | GPU required |
| xtts | Good, 17 langs | ~500ms-1s | Yes | GPU recommended |
| espeak | Robotic | <50ms | No | Test/CI only |

## Run standalone
```bash
pip install -r requirements.txt && pip install kokoro soundfile   # or your backend
DEV_API_KEY=dev-test-key TTS_BACKEND=kokoro python app.py
```

## Test
```bash
python test_standalone.py
curl -X POST -H "Authorization: Bearer dev-test-key" -H "Content-Type: application/json" \
  -d '{"text":"Hello from the platform"}' http://localhost:8002/v1/tts -o out.wav
```
`X-First-Chunk-Ms` response header = time-to-first-audio. Target <250ms on GPU.
