# Roadmap

## Phase 0 — R&D spike: PARTIALLY COMPLETE
- [x] VAD verified (real numbers, sandbox)
- [x] Streaming/plumbing verified (real, sandbox)
- [ ] STT latency on GPU — `phase0/spike_stt.py` (blocked in sandbox: HF download + no GPU)
- [ ] Real TTS quality/latency on GPU — `phase0/spike_tts.py`
- [ ] Asterisk softphone loop — `phase0/spike_asterisk.md`
**Next action: run `./scripts/run_phase0_spike.sh` on GPU machine, fill FEASIBILITY_REPORT.**

## Phase 1 — Browser MVP: CODE COMPLETE, needs GPU + LLM key to exercise fully
- [x] All 8 services implemented + standalone tests
- [x] docker-compose one-command stack
- [x] Browser voice client (zero-build HTML)
- [x] Barge-in/interruption
- [ ] End-to-end audio session verified on real hardware (`scripts/test_e2e.py`)

## Phase 2 — Telephony: CODE COMPLETE, needs network-capable host
- [x] Asterisk container + ARI controller + RTP<->WS bridge
- [x] Outbound calls API, inbound Stasis routing
- [x] Free softphone test path (no carrier cost)
- [ ] Telnyx trunk live test (needs account + DID)
- [ ] DTMF handling, voicemail detection (basic heuristics) — NEXT
- [ ] Per-call recording taps -> recording-service — NEXT

## Phase 3 — Multi-tenant SaaS: FOUNDATION BUILT
- [x] API key issuance/auth/revocation (hashed), rate limiting
- [x] Usage metering events + /v1/usage rollup
- [x] Dashboard skeleton (keys, usage) + test client
- [ ] Dashboard JWT login, admin endpoint protection
- [ ] Billing/invoicing integration (usage_events table = the meter)
- [ ] Live call view (subscribe NATS events)

## Product layers (thin clients on this API)
- Realtor dialer: POST /v1/calls per lead + CRM webhook on call-ended (NATS consumer) — ~1 week on top
- Hireview: browser client + interview prompt templates + transcript/recording fetch — ~1 week on top
