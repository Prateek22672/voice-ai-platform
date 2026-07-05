"""Phase 0 — VAD spike. Runs anywhere (ONNX, no torch, model bundled in pip wheel).
Generates speech (espeak) + silence, verifies Silero detects speech regions correctly."""
import subprocess, time, wave
import numpy as np

def gen_wav(path, text=None, seconds=2):
    if text:
        subprocess.run(["espeak-ng", "-w", path, text], check=True)
    else:
        with wave.open(path, "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            w.writeframes(b"\x00\x00" * 16000 * seconds)

def load_16k(path):
    with wave.open(path) as w:
        sr = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)/32768
    if sr != 16000:
        idx = np.round(np.arange(0, len(pcm), sr/16000)).astype(int)
        pcm = pcm[idx[idx < len(pcm)]]
    return pcm

def main():
    from silero_vad import load_silero_vad, get_speech_timestamps
    t0 = time.time()
    model = load_silero_vad(onnx=True)
    print(f"model load: {time.time()-t0:.2f}s")

    gen_wav("_speech.wav", "the quick brown fox jumps over the lazy dog")
    gen_wav("_silence.wav")
    speech, silence = load_16k("_speech.wav"), load_16k("_silence.wav")

    t0 = time.time()
    ts_speech = get_speech_timestamps(speech, model, sampling_rate=16000)
    lat_ms = (time.time()-t0)*1000
    ts_silence = get_speech_timestamps(silence, model, sampling_rate=16000)

    print(f"speech file  -> {len(ts_speech)} speech segment(s), VAD latency {lat_ms:.1f}ms "
          f"for {len(speech)/16000:.1f}s audio")
    print(f"silence file -> {len(ts_silence)} speech segment(s) (expect 0)")
    assert len(ts_speech) > 0, "FAIL: speech not detected"
    assert len(ts_silence) == 0, "FAIL: silence misdetected as speech"
    print("VAD: GO")

if __name__ == "__main__":
    main()
