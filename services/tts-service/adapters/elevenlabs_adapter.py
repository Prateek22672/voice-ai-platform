"""ElevenLabs — the premium tier. True ElevenLabs voices + their GPU latency through OUR
pipeline (browser agent, phone calls, /v1/tts — everything works unchanged).
Env:
  ELEVENLABS_API_KEY  (required)
  ELEVEN_MODEL        default eleven_turbo_v2_5   (their low-latency conversational model)
  ELEVEN_VOICE        default Rachel              (used when no ElevenLabs voice id is passed)
Costs their per-character rates — use for premium clients; Kokoro stays the free default."""
import os
import httpx
from adapters.base import TTSAdapter

class ElevenLabsAdapter(TTSAdapter):
    sample_rate = 24000   # pcm_24000 matches the rest of the pipeline exactly

    def __init__(self):
        self.key = os.environ["ELEVENLABS_API_KEY"]   # fail fast if missing
        self.model = os.getenv("ELEVEN_MODEL", "eleven_turbo_v2_5")
        self.default_voice = os.getenv("ELEVEN_VOICE", "21m00Tcm4TlvDq8ikWAM")  # Rachel

    def _voice_id(self, voice):
        # Kokoro ids (af_heart, bm_george...) contain '_' — they mean "platform default voice",
        # so map them to the configured ElevenLabs voice instead of 404ing on their API.
        if not voice or "_" in voice:
            return self.default_voice
        return voice

    async def synth_stream(self, text, voice=None):
        vid = self._voice_id(voice)
        url = (f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/stream"
               f"?output_format=pcm_24000")
        payload = {"text": text, "model_id": self.model,
                   "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
        headers = {"xi-api-key": self.key, "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=30) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as r:
                if r.status_code >= 300:
                    body = await r.aread()
                    raise RuntimeError(f"ElevenLabs {r.status_code}: {body[:200]!r}")
                buf = b""
                async for chunk in r.aiter_bytes():
                    buf += chunk
                    # ship ~200ms chunks (24k * 0.2s * 2 bytes), keep PCM16 frame alignment
                    while len(buf) >= 9600:
                        cut = 9600 - (9600 % 2)
                        yield buf[:cut]
                        buf = buf[cut:]
                if len(buf) >= 2:
                    yield buf[: len(buf) - (len(buf) % 2)]
