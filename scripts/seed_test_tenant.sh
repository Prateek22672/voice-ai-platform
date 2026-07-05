#!/usr/bin/env bash
# Creates a real (hashed) tenant API key via the gateway admin endpoint.
curl -s -X POST http://localhost:8080/admin/keys \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"test-tenant","name":"seeded"}' | python3 -m json.tool
