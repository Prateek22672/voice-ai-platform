# Architecture

## Data flow (one voice turn)
```
mic PCM16/16k ──WS──> websocket-gateway ──WS──> stt-service (Silero VAD -> faster-whisper)
                                                      │ final transcript
                                                      ▼
                                        conversation-service (Redis memory)
                                                      │ litellm stream
                                                      ▼
                                             LLM (Claude/GPT/local)
                                                      │ sentence-by-sentence SSE
                                                      ▼
                                            tts-service (adapter -> PCM chunks)
                                                      │ ~200ms binary chunks
mic playback <──WS── websocket-gateway <──────────────┘
```
Phone calls: Asterisk externalMedia (slin16 RTP) <-> telephony-service RTPBridge <-> same gateway WS.
Same pipeline, different transport.

## Latency budget (targets)
| Stage | Target | Where measured |
|---|---|---|
| VAD | 10-20ms | stt-service |
| STT (utterance) | 100-250ms | X-latency in transcript msg |
| LLM first token | 100-300ms | conversation SSE `first_token_ms` |
| TTS first chunk | 100-250ms | tts `X-First-Chunk-Ms` header / WS done msg |
| **Total time-to-first-audio** | **300-700ms** | analytics-service p50/p95 |

## Key design decisions
1. **Sentence-streaming everywhere.** LLM output flushes per-sentence to TTS; TTS chunks ~200ms.
   User hears sentence 1 while sentence 3 still generating. This, not model choice, is what
   makes latency feel sub-second.
2. **VAD before Whisper.** Silero (ONNX, ~1MB, 24ms/2.8s audio measured) gates what reaches the
   GPU. ~70% GPU load reduction on real conversations (mostly silence/listening).
3. **TTS adapter pattern.** `TTS_BACKEND` env swaps kokoro/f5tts/cosyvoice/xtts/espeak. TTS
   models leapfrog every few months — zero platform changes to adopt the next one.
4. **litellm router.** `LLM_MODEL=claude-sonnet-4-6` today, `ollama/llama3` tomorrow. One line.
5. **ARI not AGI.** Asterisk driven over HTTP/WS from Python; externalMedia gives raw RTP taps
   without dialplan hacks.
6. **Barge-in.** Gateway detects user speech during TTS playback -> POST /interrupt -> Redis flag
   -> LLM stream aborts. Interruption latency = one sentence max.
7. **slin16 end-to-end on phone leg.** externalMedia negotiates 16kHz PCM = exactly what Whisper
   wants. No transcode on the inbound path.
8. **NATS JetStream** bus provisioned for async events (recording-done, call-ended -> CRM
   webhooks). Simpler ops than Kafka; documented migration path if volume demands.

## Multi-tenancy (Phase 3)
- api-gateway: Bearer key -> sha256 lookup -> tenant_id injected as `x-tenant-id` header downstream.
- Usage events land in Postgres per tenant -> `/v1/usage` = billing basis.
- Keys created via `POST /admin/keys` (gate behind dashboard JWT in prod), hashed at rest, shown once.

## Scaling path
See `infra/k8s/PLAN.md`. Short version: GPU node pools per workload, HPA on active-session
metric, Asterisk at edge outside k8s.
