# Voice AI Platform — Complete Guide

*Everything: what it is, how it's built, every port, how it's deployed on Hostinger + Cloudflare, how phone calls work, which telephony providers to use for India & the US, precise cost estimates, and whether you'll ever need a GPU.*

---

## 1. What this platform is

A **self-hosted replacement for three paid vendors**, merged into one service you own:

| The vendor you were paying | What it did | Our replacement |
|---|---|---|
| **ElevenLabs** | Text → Speech (the voice) | **Kokoro-82M** (self-hosted, 22 natural voices) |
| **OpenAI Whisper API** | Speech → Text (transcription) | **Groq `whisper-large-v3`** (cloud, cheap) — or self-hosted Whisper |
| **Twilio** | Phone calls (PSTN) | **Asterisk + a SIP trunk** (Phase 2) |

The "brain" (the LLM that decides what to say) is **Groq Llama 3.3 70B** — cloud, ~225 ms/response.

Everything runs as **Docker containers** on one server. Live at **https://voice.foliofyx.in**.

---

## 2. The big picture (architecture)

```
                        ┌──────────────────────────────────────────────┐
   You (browser mic) ──▶│                                              │
                        │   websocket-gateway  (the conductor)         │
   Phone call ─────────▶│   ws://…:8000/v1/agent/stream                │
   (Asterisk)           │                                              │
                        └───┬───────────────┬───────────────┬──────────┘
                            │               │               │
                       1. speech        2. text         3. reply text
                            ▼               ▼               ▼
                     ┌──────────┐    ┌────────────┐   ┌──────────┐
                     │   STT    │    │    LLM     │   │   TTS    │
                     │  :8001   │    │   :8003    │   │  :8002   │
                     │  Groq    │───▶│ Groq Llama │──▶│  Kokoro  │
                     │ Whisper  │    │  3.3 70B   │   │  voice   │
                     └──────────┘    └────────────┘   └──────────┘
                            │                               │
                     transcript                       audio spoken
                            └──────────── back to you ──────┘
```

**One "turn" of conversation:** you speak → gateway streams your audio to **STT** → transcript goes to the **LLM** → the reply text is streamed sentence-by-sentence to **TTS** → spoken audio streams back to you. The browser and the phone use the **exact same gateway** — that's why building it once covers both.

**Half-duplex turn-taking:** while the agent is speaking, your mic is muted (so it never transcribes its own voice). When it pauses, you get the turn back. This is what makes it feel natural and stops the "hearing itself" bug.

---

## 3. Every service & port (reference table)

All of these run as containers from one `docker-compose.yml`.

### Core pipeline (always on)
| Service | Internal port | Host port | What it does |
|---|---|---|---|
| **websocket-gateway** | 8000 | 8000 | Realtime voice session; chains STT → LLM → TTS |
| **stt-service** | 8001 | 8001 | Speech-to-text (Groq / OpenAI / self-hosted Whisper) |
| **tts-service** | 8002 | 8002 | Text-to-speech (Kokoro) + Voice Studio catalog |
| **conversation-service** | 8003 | 8003 | The LLM brain (Groq Llama 3.3 70B via LiteLLM) |
| **telephony-service** | 8004 | 8004 | Phone-call controller (Phase 2, off by default) |
| **recording-service** | 8005 | 8005 | Saves recordings + transcripts to MinIO/Postgres |
| **analytics-service** | 8006 | 8006 | Usage, latency, cost metrics |
| **api-gateway** | 8080 | **8090** | Public REST front door + API keys + admin (host 8090 because 8080 was taken on the VPS) |
| **dashboard** | 3000 | 3000 | The website (Next.js) |

### Infrastructure (data stores)
| Service | Port | What it does |
|---|---|---|
| **postgres** | 5432 | API keys, call metadata, usage |
| **redis** | 6379 | Conversation memory / session state |
| **nats** | 4222, 8222 | Internal event bus |
| **minio** | 9000 (API), 9001 (console) | Recording storage (S3-compatible) |

### Public HTTPS layer (added for live hosting)
| Service | Port | What it does |
|---|---|---|
| **caddy** | 8099 (internal only) | Reverse proxy — routes one domain to the right service |
| **cloudflared** | — (outbound only) | Cloudflare Tunnel — gives HTTPS without opening any ports |

### Optional profiles
| Service | Port | Profile | What it does |
|---|---|---|---|
| **asterisk** | 5060/udp + RTP | `telephony` | SIP/PSTN phone engine |
| **prometheus** | 9090 | `monitoring` | Metrics scraper |
| **grafana** | 3001 | `monitoring` | Metrics dashboards |

---

## 4. The website (pages & what each does)

| Page | URL | Purpose |
|---|---|---|
| **Overview** | `/` | Hero + live health of every service + the pipeline diagram |
| **Architecture** | `/architecture` | The voice pipeline + telephony half + cost breakdown |
| **Voices** (Voice Studio) | `/voices` | Preview all 22 natural voices, pick the live agent voice |
| **Insights** | `/insights` | Switch STT engine (Whisper/OpenAI/Groq), live usage & cost |
| **Admin** | `/admin` | Password-locked: create/revoke API keys, see live connections |
| **Talk to Agent** | `/voice-client.html` | The actual live voice demo |
| **Train a Voice** | `/voice-enroll.html` | Upload a reference clip to enroll a cloned voice (needs GPU backend to *speak* it) |

---

## 5. Swapping models (one env var each)

Everything is swappable in `.env` — no code changes:

| What | Env var | Options |
|---|---|---|
| STT engine | `STT_BACKEND` | `groq` (default, cheap) · `openai` · `whisper` (self-hosted) |
| STT model | `GROQ_STT_MODEL` | `whisper-large-v3` |
| TTS voice | (set live in Voice Studio, or) `KOKORO_VOICE` | `af_heart`, `bf_emma`, … |
| Voice speed | `KOKORO_SPEED` | `0.9` (calmer) |
| LLM | `LLM_MODEL` | `groq/llama-3.3-70b-versatile` |

STT can also be switched **live** from the Insights page; the TTS voice can be switched **live** from the Voice Studio — both without a redeploy.

---

## 6. Voice Studio (the natural-voices feature)

`/voices` lists **22 built-in Kokoro voices** (American + British, female + male), each with a quality grade:

- **Preview** — type any line, hear any voice instantly (open, no key needed).
- **Use for agent** — sets the **live** voice the agent speaks with; takes effect immediately and survives restarts (password-gated with the admin password).
- British voices use the correct British pronunciation pipeline (not American with a British accent).

Backend endpoints (on tts-service, reachable at `/v1/tts/*` through the tunnel):
- `GET /v1/tts/catalog` — the voice list + current live voice
- `POST /v1/tts/preview` — `{text, voice}` → WAV
- `POST /v1/tts/default_voice` — `{voice}` + `X-Admin-Password` header → sets the live voice

---

## 7. API integration (how your Interview Platform calls this)

Your separate AI-interview app talks to this service like it's a vendor:

1. In **Admin**, create an **API key** (`vk_…`). It's stored SHA-256-hashed in Postgres.
2. Your app calls the **api-gateway** (`https://voice.foliofyx.in/v1/…`) with `Authorization: Bearer vk_…`.
3. The gateway is the **auth boundary**: it validates your `vk_` key, then swaps in the internal `DEV_API_KEY` before forwarding to the internal services (which only trust the internal key). This is why the interview key works end-to-end.
4. The Admin page's "Connected clients" panel shows live sessions so you can confirm the integration is talking.

---

## 8. Deployment — the full journey (exactly what we did)

```
Local laptop (Docker)  ──git push──▶  GitHub (private)  ──git pull──▶  Hostinger VPS
                                                                            │
                                                          docker compose up --build (12 containers)
                                                                            │
                                                    cloudflared ──outbound──▶ Cloudflare edge
                                                                            │
                                                        https://voice.foliofyx.in (mic works)
```

**Step by step:**

1. **Local:** built and tested all containers with `docker compose up --build`.
2. **GitHub:** a clean repo (`git init` inside `voice-ai-platform`), pushed. `.env` is **git-ignored** (holds secrets).
3. **Hostinger VPS** (KVM 2: 2 vCPU, 8 GB RAM, 100 GB, Mumbai — already runs n8n + Traefik):
   - `git clone` the repo, create `.env` with the keys.
   - `docker compose up -d --build` → all 12 containers up.
   - Note: **we do NOT use Hostinger's "Docker Manager / + Project" UI** — our stack runs via `docker compose` directly over SSH. That UI is only for Hostinger's own one-click apps (like n8n).
4. **The port clash:** Hostinger already used `8080`, so the api-gateway is mapped to host **8090** (`8090:8080`).
5. **HTTPS with a working mic:** Traefik on the VPS owns ports 80/443 (for n8n), so we couldn't bind them. Solution → a **Cloudflare Tunnel**:
   - `cloudflared` makes an **outbound-only** connection to Cloudflare (no inbound ports, no firewall changes).
   - Cloudflare terminates HTTPS at `voice.foliofyx.in` and forwards traffic down the tunnel to **caddy:8099**.
   - **caddy** looks at the path and sends it to the right container (see routing table below).

**Why a tunnel instead of just pointing DNS at the IP?** The mic (`getUserMedia`) only works over **HTTPS**. Traefik already held 443, and we didn't want to touch the n8n setup. The tunnel gives us clean HTTPS on a subdomain without fighting over ports.

---

## 9. How traffic is routed on the VPS (Caddy table)

`cloudflared` sends **everything** to `caddy:8099`. Caddy then splits by path (`infra/caddy/Caddyfile`):

| Path | Goes to | Why |
|---|---|---|
| `/v1/agent/stream*` | websocket-gateway:8000 | the live voice WebSocket |
| `/v1/usage_stt*`, `/v1/stt/backend*` | stt-service:8001 | STT usage + engine switch |
| `/v1/tts*` | tts-service:8002 | Voice Studio catalog/preview/set-voice |
| `/admin/verify`, `/admin/keys`, `/admin/activity` | api-gateway:8080 | admin **API** calls |
| `/v1/*` (everything else) | api-gateway:8080 | your interview-platform API |
| everything else (`/`, `/admin` page, `/voices`, assets) | dashboard:3000 | the website |

> The Cloudflare Tunnel route is configured as **Published application → `http://caddy:8099`** in the Zero Trust dashboard (Networks → Tunnels → voice → Routes). It auto-creates the DNS; we had to delete the old `voice` A record so the tunnel could add its CNAME.

---

## 10. Part B — Telephony (real phone calls) 📞

### Does our STT/TTS work for phone calls? **Yes — already.**

Look at the flow: a phone call and a browser session **end up in the same place**. Asterisk answers the call, grabs the raw audio, and pipes it into the **same `websocket-gateway` agent session** the browser uses. So the phone call automatically gets STT → LLM → TTS. Nothing about the voice pipeline changes.

```
Caller's phone
     │  (PSTN — the normal phone network)
     ▼
SIP TRUNK PROVIDER   ← this is the ONE piece you still need to buy
     │  (SIP over the internet)
     ▼
Asterisk (our container)         ← replaces Twilio's call engine
     │  externalMedia RTP (raw audio)
     ▼
telephony-service (ari_app.py)   ← bridges call audio ⇄ gateway
     │  WebSocket PCM
     ▼
websocket-gateway ──▶ STT ──▶ LLM ──▶ TTS ──▶ back down the same path to the caller
```

**In plain words:** Asterisk is the phone switchboard. The `telephony-service` strips the audio out of the call and feeds it to our agent, then pushes the agent's spoken reply back into the call. The code already:
- Answers inbound calls and can originate outbound calls (`POST /v1/calls {to, agent_prompt}`).
- Converts the agent's 24 kHz TTS audio down to 16 kHz for the phone leg.
- Reconnects to Asterisk automatically.

### So what's missing? **A SIP trunk + a phone number.**

Asterisk can't reach the public phone network by itself — it needs a **SIP trunk provider** who gives you:
1. A **phone number (DID)** people can call, and
2. **Termination** (the ability to place/receive calls on the PSTN).

The config (`pjsip.conf`) is already templated for a trunk named `telnyx-trunk` — you just fill in `SIP_TRUNK_USER` / `SIP_TRUNK_PASS` / `SIP_DID_NUMBER` in `.env` and enable the profile:

```bash
docker compose --profile telephony up -d
```

### This IS the "ElevenLabs + Twilio merged" service

Once the trunk is connected: **one service** does the voice (Kokoro), the transcription (Groq Whisper), the brain (Groq Llama), **and** the phone call (Asterisk + trunk). You no longer need ElevenLabs *or* Twilio — you only pay a SIP trunk for the raw phone minutes (which is far cheaper than Twilio's bundled voice API).

---

## 11. Third-party SIP-trunk / phone-number providers

You need a provider that gives a **DID number + SIP trunking** (raw SIP that Asterisk can register to). Split by country because **India is regulated separately** from the US.

> ⚠️ **Prices below are approximate (early 2026) and change often — always confirm on the provider's live pricing page before committing.** All are per-minute unless noted. ₹ figures assume ~₹83/$.

### 🇺🇸 United States (easy — any of these work with Asterisk)

| Provider | Number rental /mo | Inbound /min | Outbound /min | Per 100 min (inbound) | Link |
|---|---|---|---|---|---|
| **Telnyx** ⭐ (config already targets this) | ~$1.00 | ~$0.0035 | ~$0.005 | ~$0.35 | telnyx.com |
| **SignalWire** (Twilio-compatible, cheap) | ~$0.87 | ~$0.0035 | ~$0.0095 | ~$0.35 | signalwire.com |
| **Plivo** | ~$0.50 | ~$0.0055 | ~$0.009 | ~$0.55 | plivo.com |
| **Twilio** (what you're replacing — reference) | ~$1.15 | ~$0.0085 | ~$0.014 | ~$0.85 | twilio.com |
| **Bandwidth / Vonage** | enterprise | varies | varies | — | bandwidth.com |

**Recommendation for US:** **Telnyx** (best price + the config is already set up for it) or **SignalWire**.

### 🇮🇳 India (regulated — must use a licensed Indian provider)

India (TRAI) does **not** allow a foreign SIP trunk to hand you a domestic Indian number and terminate calls the way the US does. For Indian domestic numbers you go through a **licensed Indian operator**. For our Asterisk setup, pick ones that offer real **SIP trunking**:

| Provider | Type | Number rental | Per-min (approx) | SIP trunk for Asterisk? | Link |
|---|---|---|---|---|---|
| **Acefone / Servetel** ⭐ | Indian SIP trunk + DID | ~₹500–1,500/mo | ~₹0.30–0.60 | **Yes** (built for this) | acefone.com · servetel.in |
| **Exotel** | Indian CPaaS (managed IVR) | ~₹500–2,000/mo + setup | ~₹0.40–0.70 | Partial (SIP connect on higher plans) | exotel.com |
| **Knowlarity** | Indian cloud telephony | plan-based | ~₹0.40–0.80 | On request | knowlarity.com |
| **Ozonetel** | Indian CX telephony | plan-based | ~₹0.40–0.80 | On request | ozonetel.com |
| **MyOperator** | Indian SMB telephony | plan-based | ~₹0.40–0.80 | Limited | myoperator.com |
| **Tata Comm / Airtel IQ** | Telco-grade SIP | enterprise | negotiated | Yes (enterprise) | tatacommunications.com · airtel.in/airtel-iq |
| **Plivo / Twilio (India)** | Global, Indian DIDs | higher + KYC | higher | Yes, but heavy compliance | plivo.com · twilio.com |

**India compliance you can't skip:** KYC (business docs), and for any automated/outbound telemarketing, **DLT registration** (TRAI). Caller-ID rules apply. Acefone/Servetel and Exotel walk you through this — it's normal, just budget a day or two for onboarding.

**Recommendation for India:** **Acefone / Servetel** (they explicitly sell SIP trunking that plugs into Asterisk) — or **Exotel** if you prefer a more managed setup.

---

## 12. Cost estimation — precise per-minute & per-100-minutes

**Our stack cost = (cloud AI per-minute) + (phone trunk per-minute) + (fixed server & number rental).**

### Per-minute AI cost (same for US & India)
| Piece | Cost/min |
|---|---|
| STT — Groq `whisper-large-v3` | ~$0.00185 (₹0.15) |
| LLM — Groq Llama 3.3 70B (~a few hundred tokens/turn) | ~$0.0006 (₹0.05) |
| TTS — Kokoro (self-hosted CPU) | **₹0 marginal** (server already paid) |
| **AI subtotal** | **~$0.0025 / min (₹0.20/min)** |

### 🇺🇸 US — all-in per phone minute
| | /min | /100 min |
|---|---|---|
| AI subtotal | ~$0.0025 | ~$0.25 |
| Telnyx inbound | ~$0.0035 | ~$0.35 |
| **Total (calls)** | **~$0.006/min** | **~$0.60 / 100 min** |
| + fixed: number ~$1/mo, server (already paid) | | |

### 🇮🇳 India — all-in per phone minute
| | /min | /100 min |
|---|---|---|
| AI subtotal | ~₹0.20 | ~₹20 |
| SIP trunk (Acefone/Servetel inbound) | ~₹0.40–0.60 | ~₹40–60 |
| **Total (calls)** | **~₹0.65–0.80/min** | **~₹65–80 / 100 min** |
| + fixed: number ~₹500–1,500/mo, server (already paid) | | |

### Old vendors (what you were paying) — for contrast
| | /min | /100 min |
|---|---|---|
| ElevenLabs TTS | ~$0.06–0.30 (₹5–25) | ₹500–2,500 |
| + Whisper API STT | ~$0.006 (₹0.5) | ₹50 |
| + Twilio voice | ~$0.0085 (₹0.7) | ₹70 |
| **Old total** | **~₹6–26 / min** | **~₹620–2,620 / 100 min** |

➡️ **Roughly 8–15× cheaper per minute**, and the AI part is basically free because TTS is self-hosted. The only real variable cost left is the phone trunk — which is the cheap part.

---

## 13. Do you need a GPU? (now & later)

**Right now: NO.** Here's why:
- **TTS (Kokoro-82M)** runs fine on **CPU** — it's specifically a small, fast model.
- **STT (Groq)** and **LLM (Groq)** are **cloud APIs** — the compute happens on Groq's servers, not yours.
- So the Hostinger KVM2 (2 vCPU, 8 GB, **no GPU**) runs the whole thing, browser demo and phone calls included.

**Redeploying later also won't need a GPU** — unless you deliberately turn on a GPU-only feature:

| You'd want a GPU only if… | Because… |
|---|---|
| **Real-time voice *cloning*** (F5-TTS / XTTS) — speaking in a *custom enrolled* voice | Cloning models are large and need a GPU to run in real time. (Kokoro's 22 built-in voices do **not**.) |
| **Self-hosting Whisper large-v3** locally at high volume (to drop Groq's per-minute cost) | On CPU large-v3 is slow; a GPU makes it real-time. Only worth it at very high call volume. |
| **Self-hosting the LLM** (instead of Groq) | 70B models need serious GPU. Almost never worth it vs. Groq's price. |
| **Many concurrent calls** | Each call runs a Kokoro synth on CPU; a 2-vCPU box handles a handful at once. For dozens of simultaneous calls, add vCPUs or a GPU. |

**Bottom line:** for your current design (Kokoro on CPU + Groq for STT/LLM), you never need a GPU — not for the website, not for phone calls at normal volume. Keep a GPU in your back pocket only for custom voice cloning or very high concurrency.

---

## 14. Security checklist (things easy to miss)

- ✅ **`.env` is never committed** — it holds `GROQ_API_KEY`, `OPENAI_API_KEY`, `ADMIN_PASSWORD`, `TUNNEL_TOKEN`. It's in `.gitignore`. Keep it that way.
- 🔑 **Rotate any secret you ever pasted in plaintext** (OpenAI key, VPS root password) — and keep the GitHub repo **Private**.
- 🔒 **Change `ADMIN_PASSWORD`** from the default `admin123` in `.env` before real use.
- 🌐 The **Cloudflare Tunnel token** grants account access — treat it like a password; it lives only in the VPS `.env`.
- 🧱 Because we use a tunnel, **no inbound ports are open** on the VPS firewall — that's a security win.
- 🔁 API keys are **SHA-256-hashed** in Postgres (never stored raw); revoke from the Admin page.

---

## 15. Command cheat sheet

```bash
# ---- On the VPS (~/voice-ai) ----
git pull                                   # get latest code
docker compose up -d --build               # rebuild + restart everything
docker compose up -d --build dashboard     # rebuild just the website
docker compose up -d --build tts-service   # rebuild just TTS (e.g., new voices)
docker compose restart caddy               # reload Caddy after Caddyfile change
docker compose ps                          # what's running
docker compose logs -f websocket-gateway   # tail a service's logs
docker compose down                        # stop everything

# ---- Turn on phone calls (after you have a SIP trunk) ----
# fill SIP_TRUNK_USER / SIP_TRUNK_PASS / SIP_DID_NUMBER in .env, then:
docker compose --profile telephony up -d

# ---- Turn on metrics dashboards ----
docker compose --profile monitoring up -d  # Grafana on :3001

# ---- On your PC ----
git add -A && git commit -m "..." && git push
```

---

## 16. Quick FAQ / gotchas

- **Mic doesn't work?** It must be **HTTPS** — use `https://voice.foliofyx.in`, not the raw IP.
- **Admin page shows JSON instead of a password box?** Caddy must route only `/admin/verify|keys|activity` to the gateway and the `/admin` *page* to the dashboard (fixed in the Caddyfile).
- **Changed a voice but the agent didn't change?** The live voice is stored in tts-service and read on the next turn — start a fresh session.
- **Phone audio choppy/robotic?** Sample-rate mismatch — the bridge converts 24 kHz TTS → 16 kHz for the call; keep that conversion in place.
- **Don't add the stack to Hostinger's "Docker Manager"** — it runs independently via `docker compose` over SSH.
- **India numbers need onboarding** (KYC + possibly DLT) — budget a day; it's normal, not a blocker.

---

*This platform merges ElevenLabs + Whisper + Twilio into one service you own. The website and browser agent are live now; phone calls are one SIP-trunk signup away — and no GPU required.*
