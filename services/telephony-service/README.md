# telephony-service
Twilio replacement: Asterisk (SIP/RTP) + ARI controller (this app) + SIP trunk carrier.

## Components
- `Dockerfile.asterisk` — Asterisk 20 with ARI enabled, Telnyx trunk + test softphone configured.
- `ari_app.py` — REST API (/v1/calls) + ARI event loop + RTP<->WebSocket audio bridge into the
  same STT->LLM->TTS pipeline the browser uses.

## Phase 0 test WITHOUT a SIP trunk (free)
1. `docker compose --profile telephony up asterisk telephony-service`
2. Install a softphone (Zoiper/Linphone) on your laptop/phone.
3. Register: user `softphone`, pass `test1234`, server `<docker-host-ip>:5060`.
4. Dial any number -> lands in Stasis -> AI answers. Full pipeline test, $0 carrier cost.

## Phase 2 with Telnyx
1. Buy a number + create SIP connection at portal.telnyx.com.
2. Set `SIP_TRUNK_USER/SIP_TRUNK_PASS/SIP_DID_NUMBER` in `.env`.
3. Point Telnyx SIP connection at your server's public IP:5060.
4. Outbound: `curl -X POST .../v1/calls -d '{"to":"+15551234567","agent_prompt":"..."}'`

## Notes
- externalMedia uses slin16 (16kHz PCM) — matches STT input directly, no transcode on inbound leg.
- RTP ports 18000+ per call; open UDP range in firewall for production.
- India note (Hyderabad): TRAI regulations restrict VoIP-to-PSTN interconnect domestically;
  for India calling use a licensed carrier/operator gateway. Telnyx/Plivo work for US/EU numbers.
