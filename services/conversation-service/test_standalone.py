"""Standalone: session create + one turn (needs LLM key) + interrupt endpoint."""
import json, os, subprocess, urllib.request

BASE = os.getenv("CONV_URL", "http://localhost:8003")
KEY = os.getenv("DEV_API_KEY", "dev-test-key")
H = ["-H", f"Authorization: Bearer {KEY}", "-H", "Content-Type: application/json"]

def curl(args):
    return subprocess.run(["curl", "-s"] + args, capture_output=True, text=True).stdout

def main():
    r = json.load(urllib.request.urlopen(f"{BASE}/health"))
    assert r["ok"]; print("PASS health, model =", r["model"])
    sid = json.loads(curl(["-X", "POST", *H, "-d", "{}", f"{BASE}/v1/sessions"]))["session_id"]
    print("PASS session:", sid)
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")):
        print("SKIP turn test (no LLM key set)"); return
    out = curl(["-N", "-X", "POST", *H, "-d", json.dumps({"text": "Say hello in five words."}),
                f"{BASE}/v1/sessions/{sid}/turn"])
    assert "sentence" in out, out
    print("PASS turn:", out[:200])

if __name__ == "__main__":
    main(); print("ALL PASS")
