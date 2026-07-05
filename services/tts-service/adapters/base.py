"""TTS adapter interface. Every backend implements synth_stream().
Swap backends via TTS_BACKEND env — zero changes elsewhere."""
from abc import ABC, abstractmethod
from typing import AsyncIterator

class TTSAdapter(ABC):
    sample_rate: int = 24000

    @abstractmethod
    async def synth_stream(self, text: str, voice: str | None = None) -> AsyncIterator[bytes]:
        """Yield PCM16 mono audio chunks (~200ms each). Must start yielding ASAP."""
        ...

    async def clone_voice(self, name: str, reference_wav: bytes) -> str:
        raise NotImplementedError(f"{type(self).__name__} does not support cloning")

def load_adapter(backend: str) -> "TTSAdapter":
    if backend == "kokoro":
        from adapters.kokoro_adapter import KokoroAdapter; return KokoroAdapter()
    if backend == "f5tts":
        from adapters.f5tts_adapter import F5TTSAdapter; return F5TTSAdapter()
    if backend == "cosyvoice":
        from adapters.cosyvoice_adapter import CosyVoiceAdapter; return CosyVoiceAdapter()
    if backend == "xtts":
        from adapters.xtts_adapter import XTTSAdapter; return XTTSAdapter()
    if backend == "espeak":
        from adapters.espeak_adapter import EspeakAdapter; return EspeakAdapter()
    raise ValueError(f"Unknown TTS_BACKEND: {backend}")
