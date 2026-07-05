"""Standalone: health + auth rejection + auth acceptance (dev key)."""
import json, os, subprocess, urllib.request, urllib.error
BASE = os.getenv("APIGW_URL", "http://localhost:8080")
r = json.load(urllib.request.urlopen(f"{BASE}/health"))
assert r["ok"]; print("PASS health")
try:
    urllib.request.urlopen(f"{BASE}/v1/usage")
    raise SystemExit("FAIL: no-key request should be 401")
except urllib.error.HTTPError as e:
    assert e.code == 401; print("PASS 401 without key")
out = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
    "-H", f"Authorization: Bearer {os.getenv('DEV_API_KEY','dev-test-key')}",
    f"{BASE}/v1/usage"], capture_output=True, text=True).stdout
# 502/404 acceptable standalone (upstream down) — only 401 is a failure
assert out != "401", "dev key rejected"
print(f"PASS auth accepted (upstream status {out})"); print("ALL PASS")
