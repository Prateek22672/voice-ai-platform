-- Voice AI Platform schema
CREATE TABLE IF NOT EXISTS tenants (
  tenant_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_keys (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  name TEXT DEFAULT 'default',
  key_hash TEXT UNIQUE NOT NULL,          -- sha256 of raw key, never store raw
  revoked BOOLEAN DEFAULT false,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS calls (
  call_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  direction TEXT,                          -- inbound|outbound|browser
  to_number TEXT,
  status TEXT,
  duration_s INT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recordings (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  call_id TEXT NOT NULL,
  kind TEXT,                               -- in|out|merged
  object_key TEXT NOT NULL,                -- MinIO/S3 key
  size_bytes BIGINT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rec_call ON recordings(call_id);

CREATE TABLE IF NOT EXISTS transcripts (
  call_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  content JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS usage_events (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  event_type TEXT NOT NULL,                -- stt_seconds|tts_chars|call_minutes|*_ms
  value DOUBLE PRECISION,
  meta TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage_tenant ON usage_events(tenant_id, event_type);

-- seed dev tenant
INSERT INTO tenants (tenant_id, name) VALUES ('dev', 'dev-tenant') ON CONFLICT DO NOTHING;
