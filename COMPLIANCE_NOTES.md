# Compliance — NEEDS LEGAL REVIEW BEFORE PRODUCTION. Not legal advice.

## Call recording consent
- US: some states require ALL-party consent (CA, FL, PA, WA, ...). Federal = one-party.
  Safe default: announce "this call may be recorded" at call start. Make announcement a
  per-tenant config, ON by default.
- EU/GDPR: recording = personal data processing. Need lawful basis, retention policy,
  right-to-erasure (recording-service delete path exists; wire a retention job).
- India (relevant — Hyderabad base): DPDP Act 2023 applies to voice data. Additionally TRAI
  restricts VoIP<->PSTN interconnect domestically — India PSTN calling requires a licensed
  operator/gateway. Telnyx/Plivo route US/EU legally; domestic India calling needs a local
  licensed partner.

## Outbound dialing (realtor product)
- US: TCPA — prior express consent for autodialed/prerecorded calls to cell phones; DNC
  registry scrubbing; calling-hours restrictions. AI voice calls: FCC 2024 ruling treats AI
  voices as "artificial" under TCPA. High-penalty area ($500-1,500/call). Legal review mandatory.
- Disclose AI agent identity at call start (several states moving to require this).

## Voice cloning
- Only clone with documented consent of the voice owner. Store consent artifact with the
  voice profile. Never clone public figures/celebrities.

## Interviews (Hireview)
- Recording consent from candidates (explicit, logged).
- AI-in-hiring regulations: NYC Local Law 144 (bias audit), EU AI Act (high-risk category).
  If AI output influences hiring decisions, compliance burden rises sharply — keep human
  decision-in-loop, document.

## Security posture (implemented / to-do)
- [x] API keys hashed at rest, revocable
- [x] No raw audio/transcripts logged at INFO
- [ ] TLS termination (put nginx/caddy in front for prod)
- [ ] SRTP on trunk where carrier supports
- [ ] Postgres + MinIO encryption at rest (enable at infra layer)
