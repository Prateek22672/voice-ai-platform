# Voice AI Platform
Self-hosted replacement for **ElevenLabs (TTS) + Twilio (telephony) + Whisper API (STT)**.
One reusable backend powering: Realtor CRM auto-dialer + Hireview AI interview service.

## Quickstart (5 min)
```bash
cp .env.example .env            # fill ANTHROPIC_API_KEY (or OPENAI_API_KEY) — minimum viable
docker compose up --build       # core Phase 1 stack
# open dashboard/public/voice-client.html in a browser (or http://localhost:3000)
# click Start Session, allow mic, speak -> hear AI reply
```
Default TTS is `espeak` (robotic, zero-download) so the stack works instantly.
For real voice quality on a GPU machine:
```bash
# .env: TTS_BACKEND=kokoro  TTS_EXTRA="kokoro soundfile"  WHISPER_MODEL=large-v3
docker compose up --build stt-service tts-service
```

## Ports
| Service | Port | Purpose |
|---|---|---|
| websocket-gateway | 8000 | realtime voice sessions (browser + phone) |
| stt-service | 8001 | transcription |
| tts-service | 8002 | synthesis |
| conversation-service | 8003 | LLM orchestration |
| telephony-service | 8004 | calls API (profile: telephony) |
| recording-service | 8005 | recordings/transcripts |
| analytics-service | 8006 | usage + /metrics |
| api-gateway | 8080 | public REST front door (API keys) |
| dashboard | 3000 | Next.js UI |

## Test each service in isolation
Every service dir has `README.md` + `test_standalone.py`:
```bash
cd services/tts-service && python test_standalone.py
```

## Run Phase 0 spikes (do this first on your GPU machine)
```bash
pip install faster-whisper silero-vad onnxruntime "numpy<2.0"
sudo apt install espeak-ng
./scripts/run_phase0_spike.sh     # then read FEASIBILITY_REPORT.md
```

## Phase 2 telephony (free softphone test, no carrier)
```bash
docker compose --profile telephony up --build
# register Zoiper/Linphone: softphone / test1234 @ <host-ip>:5060, dial 100
```
Real PSTN: fill Telnyx creds in `.env` — see `services/telephony-service/README.md`.

## Docs
- `ARCHITECTURE.md` — design + data flow
- `FEASIBILITY_REPORT.md` — Phase 0 results (what's verified vs pending GPU)
- `ROADMAP.md`, `COST_MODEL.md`, `COMPLIANCE_NOTES.md`
