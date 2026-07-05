"""Health check only in isolation (full flow needs STT/TTS/Conv up — see scripts/test_e2e.py)."""
import json, os, urllib.request
BASE = os.getenv("GW_URL", "http://localhost:8000")
r = json.load(urllib.request.urlopen(f"{BASE}/health"))
assert r["ok"]; print("PASS health"); print("ALL PASS")
