"""Kokoro-82M — best latency/quality ratio for real-time agents. CPU-viable, GPU-fast.
pip install kokoro>=0.9 soundfile"""
import asyncio, os
import numpy as np
from adapters.base import TTSAdapter

class KokoroAdapter(TTSAdapter):
    sample_rate = 24000
    def __init__(self):
        from kokoro import KPipeline
        self._KPipeline = KPipeline
        self.default_lang = os.getenv("KOKORO_LANG", "a")     # 'a' US, 'b' British
        # <1.0 = slower/calmer speech. Default was too fast; 0.9 is a natural phone pace.
        self.speed = float(os.getenv("KOKORO_SPEED", "0.9"))
        # Eager-load the default pipeline so startup prewarm keeps the first turn fast;
        # other-accent pipelines are built lazily the first time such a voice is used.
        self._pipes = {self.default_lang: KPipeline(lang_code=self.default_lang)}

    def _pipe_for(self, voice):
        # Voice id's first letter encodes accent: 'a' American, 'b' British. Match the
        # phonemizer to it so British voices are pronounced British, not American.
        lang = voice[0] if voice and voice[0] in ("a", "b") else self.default_lang
        if lang not in self._pipes:
            self._pipes[lang] = self._KPipeline(lang_code=lang)
        return self._pipes[lang]

    async def synth_stream(self, text, voice=None):
        voice = voice or os.getenv("KOKORO_VOICE", "af_heart")
        pipe = self._pipe_for(voice)
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, lambda: list(pipe(text, voice=voice, speed=self.speed)))
        for _, _, audio in results:
            pcm = (np.asarray(audio) * 32767).astype(np.int16).tobytes()
            step = int(self.sample_rate * 0.2) * 2
            for i in range(0, len(pcm), step):
                yield pcm[i:i+step]
