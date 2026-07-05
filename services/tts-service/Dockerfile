FROM python:3.11-slim
RUN apt-get update && apt-get install -y espeak-ng ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/tts-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Default image ships espeak fallback; for GPU builds add: RUN pip install kokoro soundfile  (or f5-tts)
ARG TTS_EXTRA=""
RUN if [ -n "$TTS_EXTRA" ]; then pip install --no-cache-dir $TTS_EXTRA; fi
COPY shared /app/shared
COPY services/tts-service /app
ENV PORT=8002 TTS_BACKEND=espeak
CMD ["python", "app.py"]
