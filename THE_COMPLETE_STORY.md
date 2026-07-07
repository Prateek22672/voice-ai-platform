# The Complete Story — Voice AI Platform, From Zero to Live Phone Calls

*The full record of what we built, how every piece works, every problem we hit and how we solved
it. Written to be readable anytime — including as interview preparation: the concepts, the
decisions, and the war stories are all here.*

> Companion docs: [PLATFORM_GUIDE.md](PLATFORM_GUIDE.md) (ports/costs/ops reference) ·
> [INTEGRATION.md](INTEGRATION.md) (API guide for external products)

---

## 1. What we built (the elevator pitch)

A **self-hosted voice-AI platform** that replaces three paid vendors with one system we own:

- **ElevenLabs** (text-to-speech) → **Kokoro-82M**, 30 natural voices (US / UK / Hindi), running on our own CPU — ₹0/min. Plus an optional premium switch that routes through ElevenLabs' API for 100% parity when a client pays for it.
- **Whisper API** (speech-to-text) → **Groq `whisper-large-v3-turbo`** — same Whisper family as OpenAI's benchmark, ~₹0.06/min, wrapped in our own accuracy pipeline.
- **Twilio** (phone calls) → **Asterisk + a Telnyx SIP trunk** — real inbound/outbound PSTN calls at raw trunk prices.

The "brain" is **Groq Llama 3.3 70B** (~225ms responses). Everything runs as **14 Docker
containers** on a 2-vCPU Hostinger VPS, published at **https://voice.foliofyx.in** through a
Cloudflare Tunnel. Two products already integrate with it as a service: the **AI interview
platform** and (ready) a **realtor website** — each with its own API key.

**Result: ~8–15× cheaper per minute than the vendor stack, with the data staying on our servers.**

---

## 2. The architecture (one mental picture)

```
  Browser mic ──────────┐                                  ┌── STT  (Groq Whisper) :8001
                        │                                  │
  Phone call ── Telnyx ─┤--> websocket-gateway :8000 ──────┼── LLM  (Groq Llama)   :8003
  (PSTN)        trunk   │      "the conductor"             │
                Asterisk┘                                  └── TTS  (Kokoro)       :8002
                                                                     │
  Interview platform ──> api-gateway :8090 (API keys, metrics,       │
  Realtor website   ──>  kill-switch — the front door)         audio back to caller
```

**The single most important design idea:** the browser demo and a real phone call end in the
**same websocket-gateway session**. We built the voice loop once; every channel (web, phone,
future WhatsApp/whatever) is just a different way of piping audio into it.

### One conversational turn, end to end
1. Audio arrives as **PCM16 16kHz** frames at the gateway.
2. Gateway forwards to **stt-service**, where **Silero VAD** watches for speech vs silence.
3. After **0.8s of trailing silence** → the utterance is cut, cleaned (see §6), sent to **Groq Whisper** → transcript.
4. Transcript → **conversation-service** → Groq Llama streams the reply **sentence by sentence** (SSE).
5. Each sentence goes to **tts-service** (Kokoro) the moment it's complete; audio chunks stream back **while later sentences are still generating** — that's what makes it feel live.
6. The client plays the audio; on the phone path it's transcoded to the telephone codec (§4).
7. **Half-duplex**: the mic is ignored during the agent's whole turn so it can never transcribe its own voice. **Barge-in**: if the user speaks over the agent, generation is killed via a Redis interrupt flag.

Infrastructure under it: **Postgres** (API keys, settings), **Redis** (conversation memory,
interrupts), **MinIO** (recordings), **NATS** (event bus), **Caddy + cloudflared** (HTTPS tunnel).

---

## 3. Deployment story (local → GitHub → VPS → HTTPS)

1. Built and tested everything locally with `docker compose up --build`.
2. Clean git repo → private GitHub → `git clone` on the Hostinger VPS (KVM2: 2 vCPU / 8GB, Mumbai — already running n8n + Traefik).
3. `.env` holds every secret (Groq/OpenAI keys, admin password, SIP creds, tunnel token) and is **git-ignored** — the repo contains only `CHANGE_ME` placeholders which an entrypoint script fills at container start.
4. Port conflicts: 8080 was taken on the VPS → api-gateway published on **8090**. Port 3000 conflict locally → killed the old app.
5. **HTTPS problem:** the mic API (`getUserMedia`) requires HTTPS, but Traefik owned 443 for n8n. Solution: **Cloudflare Tunnel** — `cloudflared` makes an *outbound-only* connection to Cloudflare; they terminate TLS at `voice.foliofyx.in` and forward everything to our internal **Caddy**, which routes by path (`/v1/agent/stream` → gateway, `/v1/tts*` → TTS, `/admin/…` APIs → api-gateway, everything else → the Next.js dashboard). **Zero inbound ports opened.**
6. The frontend was made **same-origin aware**: served behind the tunnel it calls `wss://host/...`; served raw at `IP:3000` it calls `ws://host:8000`. Works both ways.

---

## 4. The telephony build (replacing Twilio) — how a phone call works

Concepts first (interview-grade):

- **PSTN** — the public telephone network.
- **SIP** — the signaling protocol (call setup/teardown), like HTTP for calls. **INVITE → 100 Trying → 180 Ringing → 200 OK**.
- **SDP** — a body inside SIP messages where each side declares *"send my audio to IP X, port Y, codec Z"*.
- **RTP** — the actual audio: UDP packets every 20ms.
- **SIP trunk** — a provider (Telnyx) that bridges internet SIP/RTP to the real phone network. **DID** = your rented phone number.
- **Codec alaw/PCMA** — 8kHz telephone audio, 160 bytes per 20ms packet. Kokoro speaks at 24kHz PCM — someone must convert.
- **Asterisk** — open-source phone engine (the switchboard). **ARI** = its REST/WebSocket control API; **Stasis** = handing a call to your app; **externalMedia** = "fork this call's audio to me as raw RTP".

### Our call path
```
Caller phone ↔ PSTN ↔ Telnyx ↔ SIP+RTP ↔ Asterisk (host network)
                                             ↕ externalMedia RTP (alaw, loopback)
                                     telephony-service bridge (Python)
                                             ↕ WebSocket PCM16
                                     websocket-gateway → same STT/LLM/TTS loop
```

The **telephony-service** does: originate calls via ARI (`POST /v1/calls`), answer inbound, bridge
the audio both ways, transcode (alaw@8k ↔ PCM16@16k/24k with stateful resampling), log the full
conversation (every `transcript`/`agent_text` event → saved JSON per call), enforce a **max-duration
auto-hangup** (default 5 min, cost control), and expose the call list + live transcripts to the
Calls page. The agent always **speaks first** on outbound (greet:true) and always **discloses it's
an AI** (compliance).

**Telnyx setup that made it work:** a *Credentials* SIP connection (username/password), an
Outbound Voice Profile with **India + US destinations enabled**, and a purchased US number as
caller ID. Asterisk's trunk creds are injected from `.env` at container boot.

---

## 5. The debugging war stories 🔥 (the most interview-valuable section)

Six real production bugs, each diagnosed with evidence, not guesses:

### Bug 1 — Asterisk wouldn't install
`Package 'asterisk' has no installation candidate` on `debian:bookworm-slim`. **Cause:** Debian
dropped Asterisk from bookworm. **Fix:** base image → `ubuntu:22.04` (ships Asterisk 18).
**Lesson:** distro packaging is part of your dependency surface.

### Bug 2 — Calls dialed but nothing happened
Asterisk log: `Failed to perform async DNS resolution of 'sip.telnyx.com'` — the
`res_resolver_unbound` module choked on the host's `/etc/hosts` entries and took ALL DNS down with
it. **Fix:** `noload => res_resolver_unbound.so` in modules.conf → falls back to the system
resolver. **Lesson:** read the *first* error in the log, not the last.

### Bug 3 — The ghost-call storm (50 calls/second)
The Calls page flooded with "inbound" entries; CPU pegged; audio dead. **Cause:** our own
`externalMedia` channel *also* enters the Stasis app when created — the handler treated it as a new
inbound call, which created another externalMedia, which… chain reaction. **Fix:** filter
`UnicastRTP/*` channel names out of the Stasis handler. **Lesson:** when you subscribe to events,
know which of them *you yourself* generate.

### Bug 4 — Silent calls, part 1: media never arrived
`tcpdump` on the RTP ports showed **0 packets** from Telnyx while a call was live. **Cause:**
Asterisk advertised the wrong address in its **SDP** — Telnyx was streaming audio into the void.
**Fix:** `external_media_address=<public IP>` + `local_net=` on the pjsip transport. Result:
tcpdump immediately showed the caller's packets arriving. **Lesson:** signaling can succeed while
media fails — SIP and RTP take different paths; always verify with packet captures.

### Bug 5 — Silent calls, part 2: packets arrived but Python never saw them
tcpdump showed RTP hitting `127.0.0.1:18004`, but our bridge logged `rx=0`. **Cause:** the
`asyncio.wait_for(loop.sock_recvfrom(...))` pattern loses datagrams on cancellation. **Fix:**
rewrote the receiver as a proper `loop.create_datagram_endpoint` (callback-driven `DatagramProtocol`
feeding a queue) — cannot miss packets. Also: Docker's UDP port-proxy had mangled the path earlier →
moved telephony-service to **host networking** so RTP flows directly. **Lesson:** for realtime UDP,
avoid proxies and avoid polling-style socket reads.

### Bug 6 — One-way audio: it heard us… we couldn't hear it
Asterisk's RTP debug showed `Got` packets from Telnyx, `Got` our agent audio — but **zero `Sent` to
Telnyx**. Asterisk's slin16→alaw transcoding path was silently discarding our return audio.
**Fix:** requested `externalMedia` in **alaw** (the phone's native codec) so Asterisk becomes a dumb
relay, and did the transcoding ourselves in Python (`audioop`: alaw↔PCM + stateful `ratecv`
resampling 8k↔16k/24k). **First audible agent sentence on a real phone.** 🎉

### Bug 7 — The agent spoke but was deaf
Caller words never transcribed. **Cause:** the browser sends the VAD ~256ms audio blocks; the phone
bridge was sending **20ms RTP slivers** — too small for Silero VAD to ever trigger. **Fix:** buffer
caller audio into 8192-byte (256ms) chunks before forwarding — identical to the browser. Full
two-way conversation achieved. **Lesson:** downstream components have implicit frame-size
contracts; match them explicitly.

---

## 6. The accuracy pipeline (why transcription is trustworthy)

Wrapped around Whisper, all our own code:

1. **Audio pre-processing** (before STT): DC-offset removal, high-pass (<80Hz rumble), peak
   normalization — consistent loudness = fewer errors.
2. **Domain biasing**: `STT_PROMPT` primes Whisper with the vocabulary it will hear (interview
   terms, product names).
3. **Confidence gating** (the gibberish fix): we request `verbose_json` and read Whisper's own
   `avg_logprob`, `no_speech_prob`, `compression_ratio` per segment. Low-confidence results are
   **dropped, never invented into a sentence** — the iron rule is *uncertain text never reaches
   the LLM*, so the agent can't confidently answer nonsense.
4. **Noise vs unclear speech**: VAD speech-duration tells them apart. Noise → silently ignored.
   Real speech we couldn't parse → a spoken, **escalating re-prompt** ("Sorry, could you say that
   again?" → "a little louder?" → "check your mic?"), with a cooldown and reset on success — no
   LLM involved, so zero hallucination risk.
5. **Text post-processing**: strips Whisper's classic hallucination phrases ("thanks for
   watching"), collapses word repetitions.
6. Half-duplex + a buffer reset event after each agent turn = the agent never transcribes its own
   echo.

---

## 7. Latency engineering (6–9s complaint → ~2–3s + instant feel)

| Change | Saved |
|---|---|
| Silence wait 1.5s → **0.8s** | ~0.7s every turn |
| Groq `large-v3` → **`large-v3-turbo`** | ~1–2s (billing on = no rate limits) |
| **Keep-alive HTTP** to Groq (was a new TLS handshake per call) | 100–300ms/turn |
| **One TTS connection per turn** (was per sentence) | ~100ms/sentence |
| Debug WAV dump off | disk I/O per utterance |
| **Short first sentence** rule in the system prompt (first sentence gates first audio) | 0.5–1.5s perceived |
| **Instant backchannel** — pre-synthesized "Mm-hmm/Okay" plays the moment you stop talking, while the real reply generates | perceived wait ≈ 0 (the human trick) |
| Browser: jitter cushion + natural inter-sentence pauses (0.22s) | smoothness, no rushed speech |

Honest floor: Kokoro on 2 vCPU synthesizes ~realtime → ~2s for a full reply. A GPU (or the
ElevenLabs backend) takes it sub-second.

---

## 8. The product layer (what makes it a *service*, not a demo)

- **API keys** (`vk_…`): minted in the password-locked **Admin** page, SHA-256-hashed in Postgres,
  revocable. The **api-gateway is the auth boundary**: it validates the tenant key, then talks to
  internal services with the internal key.
- **Admin monitoring**: precise request counts, avg/p95 latency, voice sessions (live count, turns,
  measured "user-stops-speaking → first-audio" response time), last-50 failure log, connected
  clients.
- **Emergency kill-switch**: one button → all API calls 503, new voice sessions refused; persisted
  in Postgres; `/v1/status` flips so client status-dots go red automatically.
- **Insights = the real bill**: every STT call (measured seconds) and every LLM turn (exact token
  counts from the API) is logged server-side; cost = measured usage × official list prices, split
  per provider (Groq/OpenAI), with a phone-call estimator (trunk rate + AI per-minute).
- **Voice Studio**: 30 voices, live preview with custom text, "use for agent" switch (no redeploy),
  per-call voice override.
- **Integrations shipped**: interview platform (live WS + status dot + REST TTS) and the realtor
  site (Calls API: place calls, poll live transcripts, CRM the answers). Each gets its own key;
  their traffic shows separately in Admin.

---

## 9. Money (the numbers that sold the project)

Per minute, all-in:

| | Old vendor stack | Ours |
|---|---|---|
| TTS | ElevenLabs ₹5–25 | Kokoro **₹0** |
| STT | Whisper API ₹0.5 | Groq turbo **₹0.06** |
| LLM | — | Groq **₹0.05–0.15** |
| Phone | Twilio ₹0.7 | Telnyx **₹0.3–0.6** (India) / $0.007 (US) |
| **Total** | **₹6–26/min** | **₹0.4–0.8/min** → **8–15× cheaper** |

Fixed: VPS already paid, number rental ~$1/mo, Groq billing = usage only.
The only future capex: **one GPU** (≈₹9k/mo cloud part-time or ₹60–90k once) which upgrades voice
quality, unlocks voice cloning, and makes replies sub-second — no code changes, the adapters are
ready.

---

## 10. Glossary (rapid interview recall)

**PCM16** raw 16-bit audio samples · **sample rate** samples/second (8k phone, 16k STT, 24k Kokoro)
· **resampling** converting between rates (stateful, or you get clicks) · **alaw/PCMA** 8k
telephone codec · **VAD** voice-activity detection (Silero) · **utterance** one continuous piece of
speech · **half-duplex** one side talks at a time (mic muted during agent turn) · **barge-in** user
interrupts the agent mid-speech · **SSE** server-sent events (LLM sentence streaming) · **WebSocket**
persistent two-way connection (all realtime audio) · **SIP/SDP/RTP** call signaling / media
negotiation / the audio packets · **DID** rented phone number · **SIP trunk** internet↔PSTN bridge ·
**ARI/Stasis/externalMedia** Asterisk's app-control trio · **payload type** RTP header byte saying
which codec (8=alaw) · **reverse proxy** one entry point routing by path (Caddy) · **Cloudflare
Tunnel** outbound-only HTTPS publishing · **idempotent auth boundary** gateway swaps tenant key for
internal key · **prompt biasing** feeding expected vocabulary to Whisper · **log-prob gating**
rejecting low-confidence transcriptions.

---

## 11. Likely interview questions — and the answers we lived

**"How do you handle the agent hearing itself?"** Half-duplex: the gateway sets an `agent_turn`
event for the whole reply; mic frames are dropped; after the turn, an STT buffer reset discards
any echo that leaked in. Plus browser echoCancellation.

**"How did you debug one-way audio on calls?"** Layer by layer with evidence: bridge-level packet
counters → tcpdump at the NIC → Asterisk's `rtp set debug on`. Found `Got` from both sides but no
`Sent` toward the trunk → transcoding path was eating the audio → removed transcoding by matching
codecs end-to-end. (Full saga in §5.)

**"Why sentence-streaming instead of waiting for the full LLM reply?"** Time-to-first-audio is the
UX metric. Sentence 1 synthesizes while sentences 2-n generate; plus a pre-cached verbal
acknowledgement masks the remaining gap — the same trick human agents use ("mm-hmm").

**"How do you prevent hallucinated transcripts?"** Never trust a bare string: request per-segment
confidence, gate on avg_logprob/no_speech/compression, distinguish noise (ignore) from unclear
speech (spoken re-prompt), and keep uncertain text away from the LLM entirely.

**"How would you scale it?"** Vertical first (GPU: real-time large-v3 + TTS + cloning), then
horizontal: the services are stateless (state in Redis/Postgres), so replicate stt/tts/gateway
behind the proxy; Asterisk scales by call-count per instance; Groq handles LLM scale.

**"What would you do differently?"** Start telephony with matching codecs (alaw passthrough) from
day one; put packet-level observability (the bridge counters) in *before* the first call, not
after five silent ones.

---

*Built end-to-end in one week: 14 containers, 4 external providers replaced or integrated, 2
downstream products served, 7 production bugs diagnosed with packet-level evidence. Everything on
this page is reproducible from the repo + PLATFORM_GUIDE.md + INTEGRATION.md.*
