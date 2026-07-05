# Cost Model — managed APIs vs self-hosted
Estimates, not quotes. Recompute: `python3 scripts/cost_calc.py <minutes_per_month>`.

## Assumptions
- Managed: ElevenLabs ~$0.03-0.10/min TTS-heavy usage, Whisper API $0.006/min, Twilio ~$0.014/min
  voice. Blended ~$0.05/min for a talking agent (excl. LLM both sides).
- Self-hosted: GPU rental L4 ~$0.60/hr handles ~15 concurrent calls => ~$0.0007/min at 60%
  utilization; storage/bandwidth pennies. Real floor is utilization: idle GPU still bills.

| Monthly minutes | Managed (~$0.05/min) | Self-hosted GPU (60% util) | Self-hosted realistic incl. idle/ops |
|---|---|---|---|
| 100 | $5 | $0.07 | ~$50 (min 1 GPU always-on) — NOT worth it |
| 1,000 | $50 | $0.70 | ~$50 — breakeven-ish |
| 10,000 | $500 | $7 | ~$60-120 — clearly worth it |
| 100,000 | $5,000 | $70 | ~$300-800 (multi-GPU) — 6-15x cheaper |

**Rule of thumb:** below ~5k min/month stay managed; above ~20-50k min/month self-hosting wins
decisively. SIP carrier cost (~$0.005-0.02/min) unavoidable in BOTH models.
