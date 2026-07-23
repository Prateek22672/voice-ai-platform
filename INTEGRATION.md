# Voice AI — Integration Guide (for the Interview Platform)

Everything you need to connect your **AI Interview Platform** to this Voice AI service:
the base URL, how to get your API key, every endpoint, a **live green/red status dot**, and a
**drop-in live voice-agent client**. Paste this whole file to Claude on the other platform and it
can wire it up.

---

## 0. The essentials

| Thing | Value |
|---|---|
| **Base URL** | `https://voice.foliofyx.in` |
| **Live voice WebSocket** | `wss://voice.foliofyx.in/v1/agent/stream` |
| **Status endpoint** (green/red) | `GET https://voice.foliofyx.in/v1/status` |
| **Auth for REST API** | HTTP header `Authorization: Bearer vk_xxx` |
| **Auth for the live voice WS** | none required (open over the secure tunnel) |

> **HTTPS/WSS only** — the microphone (`getUserMedia`) will not work over plain http.

---

## 1. Get your API key (one-time, 30 seconds)

The key is only needed for the **REST API** (custom TTS, sessions, usage). The **live voice WS
does not need a key.**

1. Open **https://voice.foliofyx.in/admin**
2. Enter the **admin password** (ask the owner — set in the server `.env` as `ADMIN_PASSWORD`).
3. Click **Create key**, name it `interview-platform`.
4. **Copy the `vk_…` value immediately** — it's shown once and stored hashed.
5. In your interview platform, save it as an env var, e.g. `VOICE_API_KEY=vk_…`.

You can revoke/rotate it anytime from the same Admin page.

---

## 2. All endpoints

### Public (no key)
| Method | Path | Purpose |
|---|---|---|
| `GET` | `/v1/status` | Health of the whole service (for the green/red dot). Optionally send your key to also check it's valid. |
| `GET` | `/v1/tts/catalog` | List all natural voices + the current live agent voice. |
| `WSS` | `/v1/agent/stream` | **The live voice interview** — full STT → LLM → TTS loop. |

### REST API (require `Authorization: Bearer vk_…`)
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/v1/tts` | `{ "text": "...", "voice": "af_heart" }` → `audio/wav`. Synthesize any text. |
| `POST` | `/v1/sessions` | `{ "system_prompt": "..." }` → `{ "session_id": "..." }`. Start a text conversation. |
| `POST` | `/v1/sessions/{id}/turn` | `{ "text": "..." }` → SSE stream of the agent's reply sentences. |
| `GET`  | `/v1/usage` | Usage / cost metrics. |
| `POST` | `/v1/calls` | `{ "to": "+91...", "agent_prompt": "..." }` → place a **phone call** (needs telephony enabled). |

### Admin (password header `X-Admin-Password`, not the key) — you'll use the website for these
`/admin/keys` (create/list), `/admin/keys/{id}/revoke`, `/admin/activity` (live connections).

---

## 3. Live green/red "connected" dot

`GET /v1/status` returns:
```json
{
  "ok": true,
  "service": "voice-ai",
  "components": { "voice_ws": "up", "stt": "up", "tts": "up", "llm": "up" },
  "api_key_valid": true,
  "time": 1751800000
}
```
- `ok: true` → everything healthy → **green**.
- Send your key (`Authorization: Bearer vk_…`) to also get `api_key_valid` — show red if the key is wrong/revoked.

### Drop-in React component
```jsx
'use client';
import { useEffect, useState } from 'react';

const VOICE_BASE = 'https://voice.foliofyx.in';
const VOICE_API_KEY = process.env.NEXT_PUBLIC_VOICE_API_KEY || ''; // optional

export function VoiceStatusDot({ pollMs = 10000 }) {
  const [state, setState] = useState('checking'); // 'up' | 'down' | 'checking'

  useEffect(() => {
    let alive = true;
    const check = async () => {
      try {
        const r = await fetch(`${VOICE_BASE}/v1/status`, {
          headers: VOICE_API_KEY ? { Authorization: `Bearer ${VOICE_API_KEY}` } : {},
          cache: 'no-store',
        });
        const d = await r.json();
        const ok = d.ok && (d.api_key_valid !== false);
        if (alive) setState(ok ? 'up' : 'down');
      } catch {
        if (alive) setState('down');
      }
    };
    check();
    const id = setInterval(check, pollMs);
    return () => { alive = false; clearInterval(id); };
  }, [pollMs]);

  const color = state === 'up' ? '#22c55e' : state === 'down' ? '#ef4444' : '#9ca3af';
  const label = state === 'up' ? 'Voice service connected'
              : state === 'down' ? 'Voice service offline' : 'Checking…';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
      <span style={{ width: 10, height: 10, borderRadius: '50%', background: color,
                     boxShadow: state === 'up' ? '0 0 8px #22c55e' : 'none' }} />
      {label}
    </span>
  );
}
```

### Vanilla JS version
```js
async function checkVoiceStatus() {
  try {
    const r = await fetch('https://voice.foliofyx.in/v1/status', { cache: 'no-store' });
    const d = await r.json();
    return d.ok ? 'up' : 'down';
  } catch { return 'down'; }
}
// setInterval(async () => { dot.className = await checkVoiceStatus(); }, 10000);
```

---

## 4. Embed the live voice interview (the main feature)

Connect a WebSocket, send `start` with your interviewer prompt, stream mic audio in, play the
agent's audio back. This runs the whole STT → LLM → TTS loop for you.

**Protocol**
- Send once: `{"event":"start","system_prompt":"<your interviewer instructions>","greet":true,"language":"en"}`
  - `language`: `"en"` (default) | `"hi"` Hindi | `"te"` Telugu — sets transcription language,
    makes the agent speak that language, and picks a native default voice (`hf_alpha` Hindi /
    `te_mms` open-source Telugu) plus native backchannels ("हाँ जी", "సరే").
  - `greet:true` → **the agent opens the conversation** (greets + asks the first question) without
    waiting for the candidate to speak. Optionally pass `"greeting_prompt":"<how to open>"` to
    control the opening line. Omit `greet` (or set false) to have the agent wait for the user first.
- Then send: binary **PCM16 mono 16 kHz** mic frames — **continuously, including while the agent
  is speaking** (keep `echoCancellation: true` on `getUserMedia`; that's what stops self-hearing).
- You receive:
  - binary **PCM16 mono 24 kHz** = agent speech (play it),
  - JSON events: `ready`, `state` (`agent`/`listening`), `partial_transcript`, `transcript`,
    `agent_text`, `audio_meta` (`{sample_rate}` — arrives BEFORE the first audio chunk of a
    sentence; set your playback rate from it, since voices differ: Kokoro 24k, Telugu MMS 16k),
    `audio_done` (`{sample_rate}`), `turn_done`, `interrupt`.
- **Barge-in (full-duplex):** if the user starts talking while the agent is speaking, the server
  stops generation and sends `{"type":"interrupt"}` — on that event you MUST stop every scheduled
  audio buffer immediately so the agent goes silent, then keep streaming the mic as normal.

### Drop-in client class
```js
class VoiceAgent {
  constructor(systemPrompt, { onLog, greet = true } = {}) {
    this.url = 'wss://voice.foliofyx.in/v1/agent/stream';
    this.systemPrompt = systemPrompt;
    this.greet = greet;              // agent opens the conversation on its own
    this.onLog = onLog || (() => {});
    this.ttsRate = 24000; this.nextPlay = 0; this.pendingPause = 0;
    this.agentActive = false; this.agentPlaying = false;
    this.liveSources = [];           // scheduled audio, flushed instantly on barge-in
  }
  flushPlayback() {                  // the user interrupted -> silence the agent mid-word
    this.liveSources.forEach((s) => { try { s.stop(); } catch {} });
    this.liveSources = []; this.nextPlay = 0; this.pendingPause = 0; this.agentPlaying = false;
  }

  async start() {
    this.ctx = new AudioContext();
    this.inRate = this.ctx.sampleRate;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
    this.ws = new WebSocket(this.url);
    this.ws.binaryType = 'arraybuffer';

    this.ws.onopen = () => {
      this.ws.send(JSON.stringify({ event: 'start', system_prompt: this.systemPrompt, greet: this.greet }));
      const src = this.ctx.createMediaStreamSource(this.stream);
      const proc = this.ctx.createScriptProcessor(4096, 1, 1);
      proc.onaudioprocess = (e) => {
        // full-duplex: mic stays hot even while the agent speaks — that's what enables barge-in
        const f32 = e.inputBuffer.getChannelData(0);
        const ds = this.#downsample(f32, this.inRate);
        const i16 = new Int16Array(ds.length);
        for (let i = 0; i < ds.length; i++) i16[i] = Math.max(-1, Math.min(1, ds[i])) * 32767;
        if (this.ws.readyState === 1) this.ws.send(i16.buffer);
      };
      src.connect(proc); proc.connect(this.ctx.destination);
      this._src = src; this._proc = proc;
    };

    this.ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        const d = JSON.parse(ev.data);
        if (d.type === 'state') this.agentActive = (d.state === 'agent');
        else if (d.type === 'interrupt') this.flushPlayback();   // user talked over the agent
        else if (d.type === 'transcript') {                      // new user turn -> stale tail audio off
          if (this.agentPlaying) this.flushPlayback();
          this.onLog('you', d.text); }
        else if (d.type === 'agent_text') this.onLog('agent', d.text);
        else if (d.type === 'audio_done') { this.ttsRate = d.sample_rate || 24000;
          this.pendingPause = 0.15 + Math.random() * 0.2; }      // varied breath between sentences
      } else {
        this.#play(ev.data);
      }
    };
  }

  stop() {
    try { this.ws && this.ws.send(JSON.stringify({ event: 'close' })); } catch {}
    this.ws && this.ws.close();
    this._proc && this._proc.disconnect(); this._src && this._src.disconnect();
    this.stream && this.stream.getTracks().forEach((t) => t.stop());
    this.ctx && this.ctx.close();
  }

  #downsample(f32, inRate) {
    if (inRate === 16000) return f32;
    const ratio = inRate / 16000, outLen = Math.floor(f32.length / ratio), out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const s = Math.floor(i * ratio), e = Math.floor((i + 1) * ratio); let sum = 0, n = 0;
      for (let j = s; j < e && j < f32.length; j++) { sum += f32[j]; n++; }
      out[i] = n ? sum / n : 0;
    }
    return out;
  }

  #play(arrbuf) {
    const i16 = new Int16Array(arrbuf), f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
    const buf = this.ctx.createBuffer(1, f32.length, this.ttsRate);
    buf.copyToChannel(f32, 0);
    const s = this.ctx.createBufferSource(); s.buffer = buf; s.connect(this.ctx.destination);
    this.liveSources.push(s);
    s.onended = () => { const i = this.liveSources.indexOf(s); if (i >= 0) this.liveSources.splice(i, 1); };
    const now = this.ctx.currentTime;
    if (this.nextPlay < now + 0.12) this.nextPlay = now + 0.12;
    if (this.pendingPause) { this.nextPlay += this.pendingPause; this.pendingPause = 0; }
    s.start(this.nextPlay); this.nextPlay += buf.duration;
    this.agentPlaying = true;
    clearTimeout(this._endT);
    this._endT = setTimeout(() => { this.agentPlaying = false; }, (this.nextPlay - now) * 1000 + 250);
  }
}

// Usage:
// const agent = new VoiceAgent('You are an interviewer. Ask one question at a time…',
//   { onLog: (who, text) => console.log(who, text) });
// startBtn.onclick = () => agent.start();
// stopBtn.onclick  = () => agent.stop();
```

> A full working reference is live at **https://voice.foliofyx.in/voice-client.html** — view source to see the exact same logic in a complete page.

---

## 5. REST examples

**Synthesize speech (any voice):**
```bash
curl -X POST https://voice.foliofyx.in/v1/tts \
  -H "Authorization: Bearer vk_YOURKEY" \
  -H "Content-Type: application/json" \
  -d '{"text":"Welcome to your interview.","voice":"af_heart"}' \
  --output hello.wav
```

**List voices (no key):**
```bash
curl https://voice.foliofyx.in/v1/tts/catalog
```

**Check status with key validity:**
```bash
curl https://voice.foliofyx.in/v1/status -H "Authorization: Bearer vk_YOURKEY"
```

---

## 6. Phone Calls API — for external websites (e.g., a realtor site)

The platform is also a **calling service**: any product with a `vk_` API key can place real phone
calls where our AI agent speaks (natural voice), listens (Whisper), converses (Groq), and returns
the **full transcript**. Same auth model as everything else — create a key in Admin per website
(e.g. `realtor-site`) so usage is tracked separately.

### Place a call
```bash
curl -X POST https://voice.foliofyx.in/v1/calls \
  -H "Authorization: Bearer vk_YOURKEY" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "+919876543210",
    "scenario": "realestate",
    "voice": "af_heart",
    "max_duration_s": 300,
    "agent_prompt": "You are a professional AI real-estate assistant calling from Sunrise Realty. You MUST say you are an AI assistant at the start. Qualify the lead: buying or investing, preferred location, budget, timeline. Answer questions helpfully; for exact prices offer a specialist callback. One short question at a time; under two sentences per reply.",
    "greeting_prompt": "Greet the person by name (Ravi), say you are an AI assistant from Sunrise Realty following up on their enquiry, and ask if now is a good time."
  }'
# -> {"call_id":"...","status":"dialing","max_duration_s":300}
```

| Field | Required | Notes |
|---|---|---|
| `to` | ✅ | E.164, e.g. `+91…` / `+1…` |
| `agent_prompt` | ✅ | The agent's full persona + goal. Always include the AI disclosure instruction. |
| `greeting_prompt` | — | How the agent opens the call (it always speaks first). |
| `voice` | — | Any id from `GET /v1/tts/catalog` (e.g. `af_heart`, `bf_emma`). Omit = platform default. |
| `max_duration_s` | — | Auto hang-up. Default 300 (5 min), hard cap 1800. |
| `scenario` | — | Free label for your own reporting. |

### Track the call + get the conversation
```bash
GET /v1/calls                      # list recent calls (status, duration, turns)
GET /v1/calls/{call_id}            # one call: status dialing|answered|ended, duration_s
GET /v1/calls/{call_id}/transcript # the full conversation, live during the call:
# {"transcript":[{"role":"agent","text":"Hello, I'm ...","t":7.2},
#                {"role":"caller","text":"Yes, tell me more","t":14.9}, ...]}
POST /v1/calls/{call_id}/hangup    # end it early
```
Poll `/transcript` every few seconds during a call for a live view; after `status:"ended"` the
transcript is final and stored server-side.

### Integration pattern for the realtor website
1. Owner creates an API key named `realtor-site` in **Admin** → put it in the site's backend env.
2. Their backend calls `POST /v1/calls` when a lead should be contacted (form submission, follow-up
   queue, missed enquiry).
3. Poll `GET /v1/calls/{id}` until `ended`, then fetch `/transcript` and save the lead's answers
   (budget, location, timeline) into their CRM.
4. The status dot (§3) works for them too, and their traffic shows in Admin → Connected clients.

> **Compliance:** the agent must disclose it's an AI (keep that line in every `agent_prompt`), keep
> calls inside 9am–9pm for India, and honor do-not-call requests. For production outbound marketing
> in India, DLT registration applies.

## 7. Notes & gotchas

- **CORS** is open (`*`), so you can call `/v1/status`, `/v1/tts`, `/v1/tts/catalog` directly from
  your interview platform's frontend.
- **Never expose `vk_` keys in public frontend code** if you can avoid it — for the status dot it's
  optional; for `/v1/tts` prefer calling from your backend. The live voice WS needs no key.
- **Live connections** you make show up on **https://voice.foliofyx.in/admin** → "Connected clients",
  so you can visually confirm the integration is talking.
- **Voices:** change the agent's live voice anytime at **https://voice.foliofyx.in/voices** — no code
  change needed; new sessions use the new voice.
- **Available voices** for the `voice` field: `af_heart` (default), `af_bella`, `af_sarah`,
  `bf_emma`, `am_michael`, `bm_george`, … (full list from `/v1/tts/catalog`).
