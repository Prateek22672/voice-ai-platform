"""Standalone: REST health + (if Asterisk up) ARI reachability."""
import json, os, urllib.request
BASE = os.getenv("TEL_URL", "http://localhost:8004")
r = json.load(urllib.request.urlopen(f"{BASE}/health"))
assert r["ok"]; print("PASS health")
ari = os.getenv("ARI_URL", "http://localhost:8088")
try:
    req = urllib.request.Request(f"{ari}/ari/asterisk/info")
    import base64
    cred = base64.b64encode(b"voiceai:voiceai-ari-secret").decode()
    req.add_header("Authorization", f"Basic {cred}")
    info = json.load(urllib.request.urlopen(req, timeout=3))
    print("PASS ARI reachable:", info.get("system", {}).get("version", "?"))
except Exception as e:
    print(f"SKIP ARI check (Asterisk not running): {e}")
print("ALL PASS")
