# stt-service
Streaming + batch speech-to-text. faster-whisper + Silero VAD (ONNX).

## Run standalone
```bash
pip install -r requirements.txt
DEV_API_KEY=dev-test-key WHISPER_MODEL=tiny python app.py   # tiny for CPU dev; small/large-v3 on GPU
```

## Test
```bash
python test_standalone.py            # needs service running on :8001
# batch:
curl -H "Authorization: Bearer dev-test-key" -F "file=@sample.wav" http://localhost:8001/v1/stt
```

## Env
- `WHISPER_MODEL` tiny|base|small|medium|large-v3 (GPU: use large-v3 or distil-large-v3)
- `WHISPER_DEVICE` auto|cuda|cpu, `WHISPER_COMPUTE` float16 (GPU) | int8 (CPU)
- `VAD_THRESHOLD` 0.5 default, `STT_SILENCE_FLUSH_S` 0.7 — silence gap that finalizes an utterance

## Notes
- First run downloads model from HuggingFace (needs network + optional `HF_TOKEN`).
- Streaming protocol: binary PCM16 mono 16kHz frames in → `{"type":"partial|final","text":...}` JSON out.
