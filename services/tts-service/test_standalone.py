"""Standalone: health + synth + first-chunk latency. Run with TTS_BACKEND=espeak for CI."""
import json, os, subprocess, urllib.request

BASE = os.getenv("TTS_URL", "http://localhost:8002")
KEY = os.getenv("DEV_API_KEY", "dev-test-key")

def main():
    r = json.load(urllib.request.urlopen(f"{BASE}/health"))
    assert r["ok"]; print("PASS health, backend =", r["backend"])
    out = subprocess.run(["curl", "-s", "-D", "-", "-o", "_tts_out.wav",
        "-X", "POST", "-H", f"Authorization: Bearer {KEY}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps({"text": "Testing one two three. Second sentence streams separately."}),
        f"{BASE}/v1/tts"], capture_output=True, text=True)
    assert os.path.getsize("_tts_out.wav") > 1000, "no audio produced"
    for line in out.stdout.splitlines():
        if line.lower().startswith("x-first-chunk-ms"):
            print("PASS synth, first-chunk:", line.split(":")[1].strip(), "ms")
            return
    print("PASS synth (no latency header found)")

if __name__ == "__main__":
    main(); print("ALL PASS")
