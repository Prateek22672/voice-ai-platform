# recording-service
Audio artifacts -> MinIO/S3; index + transcripts -> Postgres. Presigned download URLs.
Standalone: needs MinIO + Postgres (docker-compose brings both).
```bash
DEV_API_KEY=dev-test-key MINIO_ENDPOINT=localhost:9000 \
  POSTGRES_URL=postgresql://voice:voice@localhost:5432/voiceai python app.py
python test_standalone.py
```
