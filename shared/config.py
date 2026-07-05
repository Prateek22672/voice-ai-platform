"""Central config. All services read env vars through here."""
import os

def env(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(key, default)
    if required and not val:
        raise RuntimeError(f"Missing required env var: {key}")
    return val

POSTGRES_URL = env("POSTGRES_URL", "postgresql+asyncpg://voice:voice@postgres:5432/voiceai")
REDIS_URL    = env("REDIS_URL", "redis://redis:6379/0")
NATS_URL     = env("NATS_URL", "nats://nats:4222")
MINIO_ENDPOINT   = env("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = env("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = env("MINIO_SECRET_KEY", "minioadmin")
MINIO_BUCKET     = env("MINIO_BUCKET", "recordings")
JWT_SECRET   = env("JWT_SECRET", "dev-secret-change-me")

# STT
WHISPER_MODEL   = env("WHISPER_MODEL", "small")          # tiny|base|small|medium|large-v3
WHISPER_DEVICE  = env("WHISPER_DEVICE", "auto")          # auto|cuda|cpu
WHISPER_COMPUTE = env("WHISPER_COMPUTE", "default")      # default|float16|int8
VAD_THRESHOLD   = float(env("VAD_THRESHOLD", "0.5"))

# TTS
TTS_BACKEND = env("TTS_BACKEND", "kokoro")               # kokoro|f5tts|cosyvoice|xtts|espeak
TTS_DEVICE  = env("TTS_DEVICE", "auto")
TTS_DEFAULT_VOICE = env("TTS_DEFAULT_VOICE", "af_heart")

# LLM
LLM_MODEL = env("LLM_MODEL", "claude-sonnet-4-6")        # any litellm model string
OPENAI_API_KEY    = env("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", "")

# Telephony
ARI_URL      = env("ARI_URL", "http://asterisk:8088")
ARI_USER     = env("ARI_USER", "voiceai")
ARI_PASSWORD = env("ARI_PASSWORD", "voiceai-ari-secret")
TELNYX_API_KEY = env("TELNYX_API_KEY", "")
SIP_TRUNK_HOST = env("SIP_TRUNK_HOST", "sip.telnyx.com")
SIP_TRUNK_USER = env("SIP_TRUNK_USER", "")
SIP_TRUNK_PASS = env("SIP_TRUNK_PASS", "")
SIP_DID_NUMBER = env("SIP_DID_NUMBER", "")
