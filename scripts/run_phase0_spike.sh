#!/usr/bin/env bash
# Runs all Phase 0 spikes in sequence. Install deps first:
#   pip install faster-whisper silero-vad onnxruntime numpy
#   apt install espeak-ng            (test audio generation)
#   + one TTS backend (pip install kokoro soundfile) for a real TTS number
set -e
cd "$(dirname "$0")/../phase0"
echo "=== VAD spike ===";        python spike_vad.py
echo "=== STT spike ===";        python spike_stt.py
echo "=== TTS spike ===";        python spike_tts.py
echo "=== E2E loop spike ===";   python spike_e2e.py
echo "=== Asterisk spike: manual — see spike_asterisk.md ==="
echo "All automated spikes done. Update FEASIBILITY_REPORT.md with the numbers above."
