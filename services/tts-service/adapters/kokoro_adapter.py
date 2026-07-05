"""Kokoro-82M — best latency/quality ratio for real-time agents. CPU-viable, GPU-fast.
pip install kokoro>=0.9 soundfile"""
import asyncio, os
import numpy as np
from adapters.base import TTSAdapter

class KokoroAdapter(TTSAdapter):
    sample_rate = 24000
    def __init__(self):
        from kokoro import KPipeline
        self.pipe = KPipeline(lang_code=os.getenv("KOKORO_LANG", "a"))  # 'a' US, 'b' British
        # <1.0 = slower/calmer speech. Default was too fast; 0.9 is a natural phone pace.
        self.speed = float(os.getenv("KOKORO_SPEED", "0.9"))

    async def synth_stream(self, text, voice=None):
        voice = voice or os.getenv("KOKORO_VOICE", "af_heart")
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: list(self.pipe(text, voice=voice, speed=self.speed)))
        for _, _, audio in results:
            pcm = (np.asarray(audio) * 32767).astype(np.int16).tobytes()
            step = int(self.sample_rate * 0.2) * 2
            for i in range(0, len(pcm), step):
                yield pcm[i:i+step]
