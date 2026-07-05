# websocket-gateway
Realtime front door. Chains STT -> Conversation -> TTS for full-duplex voice sessions.

Protocol (`WS /v1/agent/stream`):
1. client -> `{"event":"start","system_prompt":"You are an interviewer..."}`
2. server -> `{"type":"ready","session_id":...}`
3. client -> binary PCM16 mono 16kHz mic frames (continuous)
4. server -> `{"type":"transcript"}`, `{"type":"agent_text"}`, binary TTS PCM chunks, `{"type":"audio_done","sample_rate":N}`
5. Barge-in automatic: user speech during TTS playback interrupts generation.

## Run standalone
```bash
pip install -r requirements.txt
STT_WS=ws://localhost:8001/v1/stt/stream TTS_WS=ws://localhost:8002/v1/tts/stream \
  CONV_URL=http://localhost:8003 python app.py
python test_standalone.py
```
