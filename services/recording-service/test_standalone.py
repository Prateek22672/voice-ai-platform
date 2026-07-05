import json, os, urllib.request
BASE = os.getenv("REC_URL", "http://localhost:8005")
r = json.load(urllib.request.urlopen(f"{BASE}/health"))
assert r["ok"]; print("PASS health"); print("ALL PASS (full test needs MinIO+PG: see docker-compose)")
