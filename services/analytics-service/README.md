# analytics-service
Usage metering (billing basis: stt_seconds, tts_chars, call_minutes) + latency metrics + /metrics for Prometheus.
```bash
DEV_API_KEY=dev-test-key POSTGRES_URL=postgresql://voice:voice@localhost:5432/voiceai python app.py
python test_standalone.py
```
