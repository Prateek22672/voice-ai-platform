#!/usr/bin/env python3
"""Recompute cost comparison at a usage tier: python3 cost_calc.py 25000"""
import sys
mins = float(sys.argv[1]) if len(sys.argv) > 1 else 10000
managed_per_min = 0.05          # blended ElevenLabs+Whisper+Twilio estimate
gpu_hr = 0.60                   # L4 cloud rental
concurrent_per_gpu = 15
util = 0.6
gpu_min_cost = gpu_hr / 60 / concurrent_per_gpu / util
gpus_needed = max(1, round(mins / 30 / 24 / 60 / concurrent_per_gpu + 0.5))  # rough peak sizing
idle_floor = gpus_needed * gpu_hr * 24 * 30 * 0.3   # 30% of always-on as conservative idle share
managed = mins * managed_per_min
self_hosted = mins * gpu_min_cost + idle_floor
print(f"{mins:,.0f} min/month:")
print(f"  managed APIs : ${managed:,.2f}")
print(f"  self-hosted  : ${self_hosted:,.2f}  ({gpus_needed} GPU(s), incl. idle floor)")
print(f"  savings      : ${managed - self_hosted:,.2f}  ({(1 - self_hosted/max(managed,0.01))*100:.0f}%)")
print("  carrier/SIP per-minute cost extra in both models.")
