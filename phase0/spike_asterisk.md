# Phase 0 — Asterisk spike (manual, needs machine with open UDP)
Cannot run in restricted sandbox — run on your dev box:

```bash
docker compose --profile telephony up --build asterisk telephony-service
# 1. ARI reachable?
curl -u voiceai:voiceai-ari-secret http://localhost:8088/ari/asterisk/info
# 2. Register softphone (Zoiper/Linphone): user=softphone pass=test1234 server=<host-ip>:5060
# 3. Dial 100. Expect: call answered, StasisStart in telephony-service logs,
#    RTP flowing (tcpdump -i any udp port 18000), AI responds.
```
Pass = softphone hears TTS reply to spoken question. Validates full RTP<->WS bridge, $0 carrier cost.
