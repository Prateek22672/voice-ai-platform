"""Standalone test: health + batch transcription with a generated tone/speech file.
Requires service running: DEV_API_KEY=dev-test-key WHISPER_MODEL=tiny python app.py"""
import os, sys, wave, math, struct, urllib.request, json

BASE = os.getenv("STT_URL", "http://localhost:8001")
KEY = os.getenv("DEV_API_KEY", "dev-test-key")

def make_test_wav(path="_test.wav"):
    # If espeak-ng available, synthesize real speech; else 1s sine (health-only value)
    if os.system("which espeak-ng > /dev/null 2>&1") == 0:
        os.system(f'espeak-ng -w {path} "hello this is a test of the transcription service"')
    else:
        with wave.open(path, "w") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
            for i in range(16000):
                w.writeframes(struct.pack("<h", int(32767*0.3*math.sin(2*math.pi*440*i/16000))))
    return path

def main():
    r = urllib.request.urlopen(f"{BASE}/health")
    assert json.load(r)["ok"], "health failed"
    print("PASS health")
    path = make_test_wav()
    import subprocess
    out = subprocess.run(["curl", "-s", "-H", f"Authorization: Bearer {KEY}",
                          "-F", f"file=@{path}", f"{BASE}/v1/stt"], capture_output=True, text=True)
    resp = json.loads(out.stdout)
    print("PASS batch:", resp)
    assert "text" in resp

if __name__ == "__main__":
    main()
    print("ALL PASS")
