import json, os, urllib.request
BASE = os.getenv("ANA_URL", "http://localhost:8006")
r = json.load(urllib.request.urlopen(f"{BASE}/health"))
assert r["ok"]; print("PASS health")
m = urllib.request.urlopen(f"{BASE}/metrics").read().decode()
print("PASS metrics endpoint"); print("ALL PASS")
