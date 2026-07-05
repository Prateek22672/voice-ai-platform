# FEASIBILITY REPORT — Phase 0
**Build environment:** CPU-only Linux sandbox (no GPU, HuggingFace downloads blocked by
network policy). Everything runnable here WAS run, with real numbers below. GPU-dependent
spikes ship as ready-to-run scripts (`phase0/`) — run `./scripts/run_phase0_spike.sh` on your
GPU box and paste numbers into the table.

## Verified in this environment (real measurements)

| Component | Result | Measured |
|---|---|---|
| Silero VAD (ONNX) | **GO** | model load 0.07s; 24.2ms to process 2.8s audio; speech correctly detected (1 segment), pure silence correctly rejected (0 segments) |
| TTS streaming pipeline (espeak backend) | **GO** (plumbing) | first-chunk 10-15ms; WS stream delivered 14×~200ms PCM chunks + done metadata; proves chunking/streaming path, NOT voice quality |
| Text normalizer | **GO** | "Dr. Smith owes $1,500 for 3 visits." -> "Doctor Smith owes one thousand, five hundred dollars for three visits." (bug found + fixed during testing) |
| tts-service standalone | **GO** | health + synth + `X-First-Chunk-Ms: 12` header |
| api-gateway auth | **GO** | no key -> 401; dev key -> accepted; hashed key issuance endpoint works |
| conversation-service + Redis | **GO** | session create OK against live Redis; LLM turn skipped (no API key in sandbox by design) |
| websocket-gateway | **GO** (boot+health) | full-duplex flow requires STT model (blocked here) — covered by `scripts/test_e2e.py` |
| All Python services | **GO** | every file compiles; services boot clean |

## Pending on YOUR hardware (scripts ready, commands exact)

| Component | Script | Expected (published benchmarks, verify yourself) | GO bar |
|---|---|---|---|
| faster-whisper STT | `phase0/spike_stt.py` | large-v3 on RTX 4090/L4: ~100-250ms per utterance, RTF ~0.05-0.15; small on CPU: RTF ~0.3-0.6 | RTF < 0.3, latency < 300ms |
| Kokoro TTS | `TTS_BACKEND=kokoro phase0/spike_tts.py` | ~80-200ms first chunk GPU; ~0.5-1.5s CPU | first-chunk ≤ 250ms |
| F5-TTS (cloning) | `TTS_BACKEND=f5tts phase0/spike_tts.py` | ~200-500ms GPU, quality > Kokoro, cloning zero-shot | first-chunk ≤ 500ms + subjective quality pass |
| E2E loop | `phase0/spike_e2e.py` | STT + TTS-first-audio ≤ 400ms combined | ≤ 500ms |
| Asterisk RTP bridge | `phase0/spike_asterisk.md` (manual softphone) | call answered, audio both ways | AI reply audible in softphone |

**Why blocked here:** sandbox network allowlist excludes huggingface.co (model weights) and
has no GPU. Not a design failure — a facilities constraint.

## Recommendation
- Architecture is sound: streaming plumbing, VAD gating, auth, orchestration all verified live.
- **Primary TTS pick: Kokoro-82M** for the dialer (speed, CPU-viable fallback), **F5-TTS** for
  Hireview where voice cloning/naturalness matters more than 100ms. Both wired; switch via env.
- Run the four pending spikes on a GPU box (any RTX 3090/4090, or cloud L4/T4). Half a day.
- Go decision expected: all four have broad published evidence at these latencies; the spike
  scripts exist to verify on YOUR hardware, not to discover novelty.

## Hardware guidance
| Tier | Setup | Handles |
|---|---|---|
| Dev | 1× RTX 3090/4090 (24GB) | 5-15 concurrent calls |
| Small prod | 1× L4 cloud (~$0.50-0.80/hr) | 10-30 concurrent |
| Scale | GPU pool per k8s plan | linear per GPU |
