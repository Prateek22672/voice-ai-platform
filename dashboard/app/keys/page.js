'use client';
import { useState } from 'react';

export default function Keys() {
  const [out, setOut] = useState('');
  const [busy, setBusy] = useState(false);

  async function createKey() {
    setBusy(true);
    try {
      const r = await fetch('http://localhost:8080/admin/keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: 'dashboard-key' }),
      });
      setOut(JSON.stringify(await r.json(), null, 2));
    } catch {
      setOut('API Gateway unreachable — is it running on port 8080?');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">API Keys</h1>
        <p className="mt-2 text-[15px] text-[#8b949e]">
          Create bearer keys for the public REST gateway. Keys are hashed at rest and shown only
          once — copy them immediately.
        </p>
      </header>

      <button
        onClick={createKey}
        disabled={busy}
        className="rounded-lg bg-[#4f7cff] px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#3d63d6] disabled:opacity-60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#4f7cff]"
      >
        {busy ? 'Creating…' : 'Create key'}
      </button>

      <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-xl border border-[#2a2f3a] bg-[#1a1d26] p-5 text-sm leading-relaxed text-[#e6e6e6]">
        {out || 'No key created yet. Click "Create key" to mint one via the API Gateway.'}
      </pre>
    </div>
  );
}
