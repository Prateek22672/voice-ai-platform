"""Generate a listenable Kokoro voice sample WAV so you can judge quality by ear.
Run: TTS_BACKEND=kokoro python gen_voice_sample.py
Output: ../kokoro_sample.wav  (open it in any audio player)"""
import asyncio, os, sys, wave
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "tts-service"))

TEXT = ("Hi, thanks for calling Riverside Realty. This is your A I assistant. "
        "I can help you book a viewing, check listing prices, or connect you "
        "with an agent. What can I do for you today?")
VOICE = os.getenv("KOKORO_VOICE", "af_heart")
OUT = os.path.join(os.path.dirname(__file__), "..", "kokoro_sample.wav")

async def main():
    from adapters.base import load_adapter
    ad = load_adapter(os.getenv("TTS_BACKEND", "kokoro"))
    pcm = b""
    async for chunk in ad.synth_stream(TEXT, voice=VOICE):
        pcm += chunk
    with wave.open(OUT, "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(ad.sample_rate)
        w.writeframes(pcm)
    print(f"wrote {OUT}  ({len(pcm)/2/ad.sample_rate:.1f}s, voice={VOICE}, {ad.sample_rate}Hz)")

if __name__ == "__main__":
    asyncio.run(main())
