# Integrating the Voice AI service into your AI Interview Platform

Replace your interview platform's slow/inaccurate STT + TTS by calling this self-hosted service over
its API. Groq `whisper-large-v3` + our audio/text cleanup for transcription; Kokoro for the voice.

---

## 1. What you need

| Thing | Value (local dev) |
|---|---|
| REST base URL | `http://localhost:8080`  *(the API gateway)* |
| Realtime voice WS | `ws://localhost:8000/v1/agent/stream` |
| Auth header | `Authorization: Bearer <YOUR_API_KEY>` |
| Get a key | Dashboard → **Admin** (password `admin123`) → *Create a key* |

> Put the key in your interview platform as an env var, e.g. `VOICE_API_KEY=vk_...`. Never hard-code it.

When deployed, swap `localhost` for your voice server's host/domain (see §5).

---

## 2. Speech → Text (transcribe the candidate)

`POST /v1/stt` — multipart form, field `file` = audio (wav/mp3/webm). Returns JSON `{ text, ... }`.

```ts
// interview platform (Node / Next.js API route)
export async function transcribe(audio: Blob): Promise<string> {
  const form = new FormData();
  form.append("file", audio, "answer.wav");
  const r = await fetch("http://localhost:8080/v1/stt", {
    method: "POST",
    headers: { Authorization: `Bearer ${process.env.VOICE_API_KEY}` },
    body: form,
  });
  if (!r.ok) throw new Error(`STT ${r.status}`);
  const { text } = await r.json();
  return text;                    // accurate transcript, cleaned by our pipeline
}
```

## 3. Text → Speech (the AI interviewer's voice)

`POST /v1/tts` — JSON `{ text, voice? }`. Returns `audio/wav` bytes.

```ts
export async function speak(text: string): Promise<ArrayBuffer> {
  const r = await fetch("http://localhost:8080/v1/tts", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${process.env.VOICE_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ text }),      // e.g. "Tell me about a hard bug you fixed."
  });
  if (!r.ok) throw new Error(`TTS ${r.status}`);
  return r.arrayBuffer();                // play this wav in the browser
}
```

## 4. (Optional) Full realtime spoken interview — one WebSocket

For a live two-way voice interview (candidate speaks, AI replies aloud), open the gateway WS and stream
mic audio. This runs the whole loop (STT → LLM → TTS) with turn-taking + barge-in built in.

```ts
const ws = new WebSocket("ws://localhost:8000/v1/agent/stream");
ws.binaryType = "arraybuffer";
ws.onopen = () => ws.send(JSON.stringify({
  event: "start",
  system_prompt: "You are a senior engineering interviewer. Ask one question at a time.",
}));
// then stream PCM16 16kHz mic frames: ws.send(int16Buffer)
ws.onmessage = (e) => {
  if (typeof e.data === "string") {
    const msg = JSON.parse(e.data);      // {type:'transcript'|'agent_text'|'state'|...}
  } else {
    playPcm(e.data);                     // agent voice audio (PCM16 @ 24kHz)
  }
};
```
*(The ready-made browser client at `dashboard/public/voice-client.html` is a working reference for this.)*

---

## 5. Does the voice service need to be deployed? — Yes, for anything beyond same-machine

- **Same machine (local dev):** if your interview platform runs on the same PC, `http://localhost:8080`
  works right now — nothing to deploy.
- **Interview platform deployed (Render/Vercel/etc.):** a deployed app **cannot** reach your laptop's
  `localhost`. You must deploy this voice service to a server with a **public URL**, then point the
  interview platform at that URL.

**Deploy options (cheapest first):**
1. **A VPS** (DigitalOcean / Hetzner / AWS) running `docker compose up -d` → gives a public IP/domain.
   CPU-only works for **Groq STT** (cloud) but TTS (Kokoro) will be slow.
2. **A GPU server** (cloud L4 or your own) → real-time TTS + self-hosted STT, fully in-house.
3. Put **TLS (https/wss)** in front (nginx/Caddy) and move the admin gate to real auth before production.

Because everything is Dockerized, deploying is the *same* `docker compose up` on the server — just set
the `.env` (keys, `ADMIN_PASSWORD`) and open ports 8080 (REST) + 8000 (WS).

---

## 6. Watching the connection

Every REST call with your key shows up live in **Dashboard → Admin → Connected clients** — you'll see
`ai-interview-platform` turn green with its request count and which endpoints it's hitting. That's your
"connected / not connected" indicator.
