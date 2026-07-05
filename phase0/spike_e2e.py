"""Phase 0 — minimal end-to-end loop: audio -> STT -> canned response -> TTS -> audio.
No LLM, no services — direct library calls. Measures pipeline round trip."""
import asyncio, os, subprocess, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "tts-service"))

async def main():
    from faster_whisper import WhisperModel
    from adapters.base import load_adapter

    subprocess.run(["espeak-ng", "-w", "_e2e_in.wav",
                    "what time does the office open tomorrow"], check=True)
    model = WhisperModel(os.getenv("WHISPER_MODEL", "tiny"))
    tts = load_adapter(os.getenv("TTS_BACKEND", "espeak"))

    t0 = time.time()
    segments, _ = model.transcribe("_e2e_in.wav")
    transcript = " ".join(s.text.strip() for s in segments)
    t_stt = (time.time()-t0)*1000

    response = "The office opens at nine A M tomorrow morning."  # canned (LLM later)

    t1 = time.time(); first = None
    async for chunk in tts.synth_stream(response):
        if first is None:
            first = (time.time()-t1)*1000
    print(f"transcript: '{transcript}'")
    print(f"STT: {t_stt:.0f}ms | TTS first-chunk: {first:.0f}ms | "
          f"pipeline (STT + TTS-first-audio): {t_stt + first:.0f}ms")
    print("Target with LLM added: 300-700ms total. LLM first-token adds ~100-300ms.")

if __name__ == "__main__":
    asyncio.run(main())
