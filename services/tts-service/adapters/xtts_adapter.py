"""XTTS v2 (Coqui) — mature, 17 languages, cloning. Heavier latency than Kokoro/F5.
pip install TTS"""
import asyncio
import numpy as np
from adapters.base import TTSAdapter

class XTTSAdapter(TTSAdapter):
    sample_rate = 24000
    def __init__(self):
        from TTS.api import TTS
        self.model = TTS("tts_models/multilingual/multi-dataset/xtts_v2")

    async def synth_stream(self, text, voice=None):
        loop = asyncio.get_event_loop()
        wav = await loop.run_in_executor(
            None, lambda: self.model.tts(text=text, speaker_wav=voice, language="en"))
        pcm = (np.asarray(wav) * 32767).astype(np.int16).tobytes()
        step = int(self.sample_rate * 0.2) * 2
        for i in range(0, len(pcm), step):
            yield pcm[i:i+step]
