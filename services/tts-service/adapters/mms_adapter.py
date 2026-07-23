"""Meta MMS-TTS (open-source, CC-BY-NC) — languages Kokoro can't speak, starting with TELUGU.
Small VITS models (~140MB each), CPU-viable, no API key, no per-character billing.
Voice ids look like 'te_mms' — the language prefix picks the model:
  te -> facebook/mms-tts-tel   (Telugu)
  (hi stays on Kokoro's native Hindi voices, but mms-tts-hin is wired as a fallback)
Needs: pip install transformers  (torch is already present via Kokoro).
Input must be native script (Telugu script for 'te'); output is 16 kHz PCM16."""
import asyncio, os
import numpy as np
from adapters.base import TTSAdapter

_LANG_MODELS = {
    "te": "facebook/mms-tts-tel",
    "hi": "facebook/mms-tts-hin",
}

class MMSAdapter(TTSAdapter):
    sample_rate = 16000   # MMS VITS models generate 16 kHz audio

    def __init__(self):
        self._models = {}   # lang -> (model, tokenizer); lazy so boot stays fast

    def _load(self, lang: str):
        if lang not in self._models:
            from transformers import VitsModel, AutoTokenizer
            name = _LANG_MODELS.get(lang, _LANG_MODELS["te"])
            model = VitsModel.from_pretrained(name)
            model.eval()
            self._models[lang] = (model, AutoTokenizer.from_pretrained(name))
        return self._models[lang]

    async def synth_stream(self, text, voice=None):
        lang = (voice or "te_mms").split("_")[0]
        if lang not in _LANG_MODELS:
            lang = "te"
        loop = asyncio.get_event_loop()

        def _synth():
            import torch
            model, tok = self._load(lang)
            inputs = tok(text, return_tensors="pt")
            with torch.no_grad():
                wav = model(**inputs).waveform
            return wav.squeeze().cpu().numpy()

        audio = await loop.run_in_executor(None, _synth)
        pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        step = int(self.sample_rate * 0.2) * 2      # ~200ms chunks, PCM16-aligned
        for i in range(0, len(pcm), step):
            yield pcm[i:i + step]
