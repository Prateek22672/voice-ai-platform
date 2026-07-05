"""Phase 0 — TTS spike. First-chunk latency + total synth time per backend.
Run: TTS_BACKEND=kokoro python spike_tts.py  (espeak for plumbing-only test)
GPU strongly recommended for kokoro/f5tts/cosyvoice real-time performance."""
import asyncio, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "tts-service"))

TEXT = ("Hello, thank you for calling. I am your AI assistant. "
        "How can I help you today with your appointment?")

async def main():
    from adapters.base import load_adapter
    backend = os.getenv("TTS_BACKEND", "espeak")
    t0 = time.time()
    ad = load_adapter(backend)
    print(f"backend '{backend}' load: {time.time()-t0:.2f}s")

    t0 = time.time(); first = None; total_bytes = 0
    async for chunk in ad.synth_stream(TEXT):
        if first is None:
            first = (time.time()-t0)*1000
        total_bytes += len(chunk)
    total = (time.time()-t0)*1000
    audio_s = total_bytes / 2 / ad.sample_rate
    print(f"first-chunk: {first:.0f}ms | total synth: {total:.0f}ms for {audio_s:.1f}s audio "
          f"(RTF={total/1000/audio_s:.2f})")
    target = 250
    verdict = "GO" if first <= target else ("GO with caveats (CPU?)" if first <= 1500 else "NO-GO on this hardware")
    print(f"TTS ({backend}): {verdict}  [target first-chunk <= {target}ms on GPU]")

if __name__ == "__main__":
    asyncio.run(main())
