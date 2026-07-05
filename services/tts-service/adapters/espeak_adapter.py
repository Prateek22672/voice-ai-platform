"""espeak-ng fallback — robotic, zero GPU, zero downloads. CI/plumbing tests ONLY."""
import asyncio, os, subprocess, tempfile, wave
from adapters.base import TTSAdapter

class EspeakAdapter(TTSAdapter):
    sample_rate = 22050
    async def synth_stream(self, text, voice=None):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        proc = await asyncio.create_subprocess_exec(
            "espeak-ng", "-w", path, text,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await proc.wait()
        with wave.open(path) as w:
            self.sample_rate = w.getframerate()
            pcm = w.readframes(w.getnframes())
        os.unlink(path)
        step = int(self.sample_rate * 0.2) * 2
        for i in range(0, len(pcm), step):
            yield pcm[i:i+step]
