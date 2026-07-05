'use client';

import { useCallback, useEffect, useState } from 'react';

// host-aware: call whatever server the page is served from (works locally AND when deployed)
const GW = typeof window !== 'undefined'
  ? `http://${window.location.hostname}:8090`
  : 'http://localhost:8090';

/* ---- small premium UI atoms (self-contained) ---- */
function Card({ children, className = '' }) {
  return (
    <div className={`rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl md:p-6 ${className}`}>
      {children}
    </div>
  );
}
function Field(props) {
  return (
    <input
      {...props}
      className={`w-full rounded-xl border border-white/10 bg-white/[0.04] px-3.5 py-2.5 text-sm text-white placeholder-white/30 outline-none focus-visible:ring-2 focus-visible:ring-white/30 ${props.className || ''}`}
    />
  );
}
function Btn({ children, variant = 'primary', ...props }) {
  const v =
    variant === 'primary'
      ? 'bg-white text-black hover:bg-white/90'
      : variant === 'danger'
      ? 'border border-white/10 text-[#e5484d] hover:border-[#e5484d]/50 hover:bg-[#e5484d]/10'
      : 'border border-white/10 text-white hover:border-white/30 hover:bg-white/5';
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center rounded-full px-5 py-2.5 text-sm font-semibold transition-colors disabled:opacity-40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 ${v} ${props.className || ''}`}
    >
      {children}
    </button>
  );
}

export default function AdminPage() {
  const [pw, setPw] = useState('');
  const [unlocked, setUnlocked] = useState(false);
  const [checking, setChecking] = useState(true);
  const [error, setError] = useState('');
  const [keys, setKeys] = useState([]);
  const [keyName, setKeyName] = useState('interview-platform');
  const [newKey, setNewKey] = useState(null); // raw key shown once
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState('');
  const [activity, setActivity] = useState([]); // live connected clients

  const adminFetch = useCallback(
    (path, opts = {}, password) =>
      fetch(GW + path, {
        ...opts,
        headers: {
          'Content-Type': 'application/json',
          'X-Admin-Password': password !== undefined ? password : pw,
          ...(opts.headers || {}),
        },
      }),
    [pw]
  );

  const loadKeys = useCallback(
    async (password) => {
      try {
        const r = await adminFetch('/admin/keys', {}, password);
        if (!r.ok) return;
        const d = await r.json();
        setKeys(Array.isArray(d.keys) ? d.keys : []);
      } catch {
        /* ignore */
      }
    },
    [adminFetch]
  );

  const loadActivity = useCallback(
    async (password) => {
      try {
        const r = await adminFetch('/admin/activity', {}, password);
        if (!r.ok) return;
        const d = await r.json();
        setActivity(Array.isArray(d.clients) ? d.clients : []);
      } catch {
        /* ignore */
      }
    },
    [adminFetch]
  );

  // poll live connections every 4s while unlocked
  useEffect(() => {
    if (!unlocked) return;
    loadActivity();
    const id = setInterval(loadActivity, 4000);
    return () => clearInterval(id);
  }, [unlocked, loadActivity]);

  // try a saved password on mount
  useEffect(() => {
    let cancelled = false;
    const saved = typeof window !== 'undefined' ? sessionStorage.getItem('adminpw') : null;
    (async () => {
      if (saved) {
        try {
          const r = await fetch(GW + '/admin/verify', { headers: { 'X-Admin-Password': saved } });
          if (!cancelled && r.ok) {
            setPw(saved);
            setUnlocked(true);
            loadKeys(saved);
          }
        } catch {
          /* ignore */
        }
      }
      if (!cancelled) setChecking(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [loadKeys]);

  async function login(e) {
    e.preventDefault();
    setError('');
    setBusy(true);
    try {
      const r = await fetch(GW + '/admin/verify', { headers: { 'X-Admin-Password': pw } });
      if (r.ok) {
        sessionStorage.setItem('adminpw', pw);
        setUnlocked(true);
        loadKeys(pw);
      } else if (r.status === 401) {
        setError('Wrong password.');
      } else {
        setError('Admin is disabled on the server.');
      }
    } catch {
      setError('API Gateway unreachable on :8080. Is it running?');
    } finally {
      setBusy(false);
    }
  }

  function lock() {
    sessionStorage.removeItem('adminpw');
    setUnlocked(false);
    setPw('');
    setKeys([]);
    setNewKey(null);
  }

  async function createKey() {
    setBusy(true);
    setNewKey(null);
    try {
      const r = await adminFetch('/admin/keys', {
        method: 'POST',
        body: JSON.stringify({ name: keyName || 'default', tenant_id: keyName || undefined }),
      });
      const d = await r.json();
      if (r.ok) {
        setNewKey(d);
        loadKeys();
      } else {
        setError(d.detail || 'Failed to create key');
      }
    } catch {
      setError('API Gateway unreachable');
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id) {
    if (!confirm('Revoke this key? Any product using it stops working immediately.')) return;
    await adminFetch(`/admin/keys/${id}/revoke`, { method: 'POST' });
    loadKeys();
  }

  function copy(text, tag) {
    navigator.clipboard?.writeText(text);
    setCopied(tag);
    setTimeout(() => setCopied(''), 1500);
  }

  /* ---------------- LOGIN GATE ---------------- */
  if (!unlocked) {
    return (
      <div className="mx-auto flex min-h-[70vh] max-w-md flex-col justify-center">
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-white/40">Restricted</p>
        <h1 className="text-balance text-3xl font-bold tracking-tight">Admin</h1>
        <p className="mt-2 mb-6 text-sm text-white/60">
          Mint and manage API keys that let your other products (e.g. the AI interview platform)
          call this voice service. Password required.
        </p>
        <Card>
          <form onSubmit={login} className="space-y-3">
            <label className="block text-xs uppercase tracking-wide text-white/50">Admin password</label>
            <Field
              type="password"
              value={pw}
              onChange={(e) => setPw(e.target.value)}
              placeholder="••••••••"
              autoFocus
            />
            {error ? <p className="text-sm text-[#e5484d]">{error}</p> : null}
            <Btn type="submit" disabled={busy || checking}>
              {busy ? 'Checking…' : 'Unlock'}
            </Btn>
          </form>
        </Card>
        <p className="mt-4 text-xs text-white/40">
          Set the password with <code className="text-white/60">ADMIN_PASSWORD</code> in
          <code className="text-white/60"> .env</code>. This is an R&amp;D gate — use JWT/SSO for production.
        </p>
      </div>
    );
  }

  /* ---------------- ADMIN PANEL ---------------- */
  const base = typeof window !== 'undefined' ? window.location.hostname : 'localhost';
  return (
    <div className="mx-auto max-w-4xl">
      <div className="mb-8 flex items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-white/40">Admin</p>
          <h1 className="text-balance text-3xl font-bold tracking-tight">API keys &amp; integration</h1>
          <p className="mt-2 max-w-2xl text-sm text-white/60">
            Create a key for each product that calls this service. Keys are hashed at rest and shown
            once. Use one for your AI interview platform.
          </p>
        </div>
        <Btn variant="ghost" onClick={lock}>Lock</Btn>
      </div>

      {/* live connections */}
      <Card className="mb-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-white/50">Connected clients</h2>
          <span className="flex items-center gap-2 text-xs text-white/55">
            <span className={`h-2 w-2 rounded-full ${activity.some((c) => c.active) ? 'bg-[#3fb950]' : 'bg-white/25'}`} />
            {activity.some((c) => c.active) ? 'live traffic' : 'idle'}
          </span>
        </div>
        {activity.length === 0 ? (
          <p className="text-sm text-white/40">
            No client has called the API yet. Point your interview platform at
            <code className="mx-1 text-white/70">http://{base}:8080</code> with a key below.
          </p>
        ) : (
          <ul className="divide-y divide-white/5">
            {activity.map((c) => (
              <li key={c.tenant_id} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                <span className="flex items-center gap-2.5">
                  <span className={`h-2.5 w-2.5 rounded-full ${c.active ? 'bg-[#3fb950]' : 'bg-white/25'}`} />
                  <span className="font-mono text-sm text-white">{c.tenant_id}</span>
                  <span className="text-xs text-white/40">
                    {Object.keys(c.paths || {}).join(' · ') || '—'}
                  </span>
                </span>
                <span className="tabular-nums text-xs text-white/55">
                  {c.requests} req · {c.active ? `${c.seconds_ago}s ago` : 'idle'}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* create */}
      <Card className="mb-6">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-[0.12em] text-white/50">Create a key</h2>
        <div className="flex flex-col gap-3 sm:flex-row">
          <Field
            value={keyName}
            onChange={(e) => setKeyName(e.target.value)}
            placeholder="product name, e.g. interview-platform"
          />
          <Btn onClick={createKey} disabled={busy}>{busy ? 'Creating…' : 'Create key'}</Btn>
        </div>
        {newKey ? (
          <div className="mt-4 rounded-xl border border-[#3fb950]/40 bg-[#3fb950]/[0.06] p-4">
            <p className="text-sm text-[#3fb950]">Key created for tenant “{newKey.tenant_id}”. Copy it now — it is not shown again.</p>
            <div className="mt-2 flex items-center gap-2">
              <code className="flex-1 overflow-x-auto whitespace-nowrap rounded-lg bg-black/40 px-3 py-2 font-mono text-sm text-white">
                {newKey.api_key}
              </code>
              <Btn variant="ghost" onClick={() => copy(newKey.api_key, 'key')}>
                {copied === 'key' ? 'Copied' : 'Copy'}
              </Btn>
            </div>
          </div>
        ) : null}
      </Card>

      {/* list */}
      <Card className="mb-8">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-white/50">Existing keys</h2>
          <Btn variant="ghost" onClick={() => loadKeys()} className="px-4 py-2">Refresh</Btn>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[520px] text-sm">
            <thead>
              <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-white/40">
                <th scope="col" className="px-3 py-2 font-medium">Tenant</th>
                <th scope="col" className="px-3 py-2 font-medium">Name</th>
                <th scope="col" className="px-3 py-2 font-medium">Created</th>
                <th scope="col" className="px-3 py-2 font-medium">Status</th>
                <th scope="col" className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {keys.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-3 py-6 text-center text-white/40">No keys yet.</td>
                </tr>
              ) : (
                keys.map((k) => (
                  <tr key={k.id} className="border-b border-white/5 last:border-0">
                    <td className="px-3 py-3 font-mono text-white">{k.tenant_id}</td>
                    <td className="px-3 py-3 text-white/70">{k.name}</td>
                    <td className="px-3 py-3 text-white/50">{(k.created_at || '').slice(0, 10)}</td>
                    <td className="px-3 py-3">
                      {k.revoked ? (
                        <span className="rounded-full bg-[#e5484d]/10 px-2 py-0.5 text-xs text-[#e5484d]">revoked</span>
                      ) : (
                        <span className="rounded-full bg-[#3fb950]/10 px-2 py-0.5 text-xs text-[#3fb950]">active</span>
                      )}
                    </td>
                    <td className="px-3 py-3 text-right">
                      {!k.revoked && <Btn variant="danger" className="px-4 py-1.5" onClick={() => revoke(k.id)}>Revoke</Btn>}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* integration guide */}
      <h2 className="mb-1 text-xl font-semibold tracking-tight">Connect your AI interview platform</h2>
      <p className="mb-5 max-w-2xl text-sm text-white/60">
        Your other product authenticates with the key above and calls this service over its public API.
        Replace <code className="text-white/70">{base}</code> with your server’s host/domain in production.
      </p>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h3 className="mb-3 text-sm font-semibold text-white">1 · REST API (sessions, STT, TTS, calls)</h3>
          <p className="mb-3 text-sm text-white/60">
            Base URL <code className="text-white/80">http://{base}:8080</code> · header
            <code className="text-white/80"> Authorization: Bearer vk_…</code>
          </p>
          <pre className="overflow-x-auto rounded-xl bg-black/50 p-4 text-xs leading-relaxed text-white/90">{`# create a conversation session
curl -X POST http://${base}:8080/v1/sessions \\
  -H "Authorization: Bearer vk_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"system_prompt":"You are an interviewer..."}'

# routes proxied: /v1/sessions /v1/stt /v1/tts
#                 /v1/calls /v1/recordings /v1/usage`}</pre>
        </Card>

        <Card>
          <h3 className="mb-3 text-sm font-semibold text-white">2 · Realtime voice (WebSocket)</h3>
          <p className="mb-3 text-sm text-white/60">
            For a live spoken interview, open the gateway WebSocket and stream mic audio.
          </p>
          <pre className="overflow-x-auto rounded-xl bg-black/50 p-4 text-xs leading-relaxed text-white/90">{`const ws = new WebSocket(
  "ws://${base}:8000/v1/agent/stream"
);
ws.onopen = () => ws.send(JSON.stringify({
  event: "start",
  system_prompt: "You are an interviewer..."
}));
// then stream PCM16 16kHz mic frames;
// receive transcript + agent audio back`}</pre>
        </Card>
      </div>

      <div className="mt-4">
        <Card>
          <h3 className="mb-2 text-sm font-semibold text-white">Phone interviews (India)</h3>
          <p className="text-sm text-white/60">
            To have the agent call a real Indian number, POST to
            <code className="text-white/80"> /v1/calls</code> with a Plivo SIP trunk configured — see the
            <a href="/architecture" className="text-white underline decoration-white/30 hover:decoration-white"> Architecture</a> page
            for the telephony setup and compliance (DLT).
          </p>
        </Card>
      </div>

      <p className="mt-8 text-xs text-white/40">
        Security: keys are sha256-hashed at rest and shown once; revoked keys stop working immediately.
        This admin gate is a shared password for R&amp;D — move to JWT/SSO and TLS before production.
      </p>
    </div>
  );
}
