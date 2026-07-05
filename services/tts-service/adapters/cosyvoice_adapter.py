"""CosyVoice 2 — strong multilingual + native streaming. GPU recommended.
Install per https://github.com/FunAudioLLM/CosyVoice (not pip-only)."""
import asyncio
import numpy as np
from adapters.base import TTSAdapter

class CosyVoiceAdapter(TTSAdapter):
    sample_rate = 22050
    def __init__(self):
        from cosyvoice.cli.cosyvoice import CosyVoice2
        self.model = CosyVoice2("pretrained_models/CosyVoice2-0.5B")

    async def synth_stream(self, text, voice=None):
        loop = asyncio.get_event_loop()
        outs = await loop.run_in_executor(
            None, lambda: list(self.model.inference_sft(text, voice or "default", stream=True)))
        for out in outs:
            audio = out["tts_speech"].numpy().flatten()
            yield (audio * 32767).astype(np.int16).tobytes()
