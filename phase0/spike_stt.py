"""Phase 0 — STT spike. faster-whisper latency + sanity accuracy.
Needs: pip install faster-whisper; network to huggingface.co for first model download.
Run: WHISPER_MODEL=tiny python spike_stt.py   (tiny=CPU dev; large-v3 on GPU)"""
import os, subprocess, time

REF = "the quick brown fox jumps over the lazy dog"

def main():
    from faster_whisper import WhisperModel
    size = os.getenv("WHISPER_MODEL", "tiny")
    device = os.getenv("WHISPER_DEVICE", "auto")
    t0 = time.time()
    model = WhisperModel(size, device=device,
                         compute_type=os.getenv("WHISPER_COMPUTE", "default"))
    print(f"model '{size}' load: {time.time()-t0:.2f}s (device={device})")

    subprocess.run(["espeak-ng", "-w", "_stt_test.wav", REF], check=True)
    t0 = time.time()
    segments, info = model.transcribe("_stt_test.wav")
    text = " ".join(s.text.strip() for s in segments).lower()
    lat = (time.time()-t0)*1000
    print(f"latency: {lat:.0f}ms for {info.duration:.1f}s audio "
          f"(RTF={lat/1000/info.duration:.2f} — <1.0 = faster than realtime)")
    print(f"ref: {REF}")
    print(f"out: {text}")
    hits = sum(1 for w in REF.split() if w in text)
    print(f"word overlap: {hits}/{len(REF.split())}")
    print("STT: GO" if hits >= 6 else "STT: CHECK OUTPUT (espeak audio is robotic; "
          "test with a real speech recording for a fair accuracy read)")

if __name__ == "__main__":
    main()
