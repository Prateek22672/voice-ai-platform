# api-gateway
Public REST entrypoint. API key auth (sha256 hashed in Postgres) + per-key rate limit + proxy.

## Run standalone
```bash
pip install -r requirements.txt
DEV_API_KEY=dev-test-key python app.py   # DEV_API_KEY bypasses DB for local testing
python test_standalone.py
```

## Create real tenant key
```bash
curl -X POST http://localhost:8080/admin/keys -H "Content-Type: application/json" \
  -d '{"tenant_id":"acme","name":"prod"}'
# -> {"api_key":"vk_..."} — hashed at rest, shown once
```
Note: WS traffic goes to websocket-gateway directly (port 8000); this gateway proxies REST.
