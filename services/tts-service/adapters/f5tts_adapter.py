"""F5-TTS — top open-source naturalness + zero-shot voice cloning. Needs GPU for real-time.
pip install f5-tts. Reference voices in ./voices/<name>.wav + .txt transcript."""
import asyncio, os
import numpy as np
from adapters.base import TTSAdapter

class F5TTSAdapter(TTSAdapter):
    sample_rate = 24000
    def __init__(self):
        from f5_tts.api import F5TTS
        self.model = F5TTS()
        self.voice_dir = os.getenv("VOICE_DIR", "./voices")

    def _ref(self, voice):
        wav = os.path.join(self.voice_dir, f"{voice}.wav")
        txt = os.path.join(self.voice_dir, f"{voice}.txt")
        ref_text = open(txt).read().strip() if os.path.exists(txt) else ""
        return wav, ref_text

    async def synth_stream(self, text, voice=None):
        ref_wav, ref_text = self._ref(voice or "default")
        loop = asyncio.get_event_loop()
        wav, sr, _ = await loop.run_in_executor(
            None, lambda: self.model.infer(ref_file=ref_wav, ref_text=ref_text, gen_text=text))
        self.sample_rate = sr
        pcm = (np.asarray(wav) * 32767).astype(np.int16).tobytes()
        step = int(sr * 0.2) * 2
        for i in range(0, len(pcm), step):
            yield pcm[i:i+step]

    async def clone_voice(self, name, reference_wav):
        os.makedirs(self.voice_dir, exist_ok=True)
        with open(os.path.join(self.voice_dir, f"{name}.wav"), "wb") as f:
            f.write(reference_wav)
        return name
