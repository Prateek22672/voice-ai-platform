'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

// host-aware: call whatever server the page is served from (works locally AND when deployed)
const STT_BASE = typeof window !== 'undefined'
  ? `http://${window.location.hostname}:8001`
  : 'http://localhost:8001';
const AUTH_HEADER = { Authorization: 'Bearer dev-test-key' };

const RATES_USD_PER_MIN = {
  'gpt-4o-transcribe': 0.006,
  'gpt-4o-mini-transcribe': 0.003,
  'whisper-1': 0.006,
  'whisper-large-v3': 0.00185,          // Groq — same accuracy, ~3x cheaper
  'whisper-large-v3-turbo': 0.000667,   // Groq — cheapest
  'distil-whisper-large-v3-en': 0.000333,
};

export default function InsightsPage() {
  const [currency, setCurrency] = useState('INR'); // 'USD' | 'INR'
  const [usage, setUsage] = useState(null);
  const [backendInfo, setBackendInfo] = useState(null);
  const [unreachable, setUnreachable] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [switchMsg, setSwitchMsg] = useState(null); // { ok: boolean, text: string }
  const [estMinutes, setEstMinutes] = useState(300);
  const [estModel, setEstModel] = useState('gpt-4o-transcribe');
  const switchMsgTimer = useRef(null);

  const usdInr =
    usage && typeof usage.usd_inr === 'number' && usage.usd_inr > 0 ? usage.usd_inr : 85;

  const money = useCallback(
    (usd) => {
      const v = Number(usd) || 0;
      if (currency === 'INR') {
        return '₹' + (v * usdInr).toFixed(2);
      }
      // USD: 4 dp when small, 2 dp otherwise
      return '$' + (Math.abs(v) > 0 && Math.abs(v) < 1 ? v.toFixed(4) : v.toFixed(2));
    },
    [currency, usdInr]
  );

  const fetchUsage = useCallback(async () => {
    try {
      const res = await fetch(`${STT_BASE}/v1/usage_stt`, { cache: 'no-store' });
      if (!res.ok) throw new Error('bad status');
      const data = await res.json();
      setUsage(data);
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  const fetchBackend = useCallback(async () => {
    try {
      const res = await fetch(`${STT_BASE}/v1/stt/backend`, { cache: 'no-store' });
      if (!res.ok) throw new Error('bad status');
      const data = await res.json();
      setBackendInfo(data);
      setUnreachable(false);
    } catch {
      setUnreachable(true);
    }
  }, []);

  const refreshAll = useCallback(() => {
    fetchUsage();
    fetchBackend();
  }, [fetchUsage, fetchBackend]);

  useEffect(() => {
    refreshAll();
    const id = setInterval(fetchUsage, 10000);
    return () => {
      clearInterval(id);
      if (switchMsgTimer.current) clearTimeout(switchMsgTimer.current);
    };
  }, [refreshAll, fetchUsage]);

  const showSwitchMsg = (ok, text) => {
    setSwitchMsg({ ok, text });
    if (switchMsgTimer.current) clearTimeout(switchMsgTimer.current);
    switchMsgTimer.current = setTimeout(() => setSwitchMsg(null), 6000);
  };

  const switchBackend = async (target) => {
    if (!backendInfo || switching) return;
    if (backendInfo.backend === target) return;
    if (target === 'openai' && !backendInfo.openai_ready) return;
    if (target === 'groq' && !backendInfo.groq_ready) return;
    setSwitching(true);
    try {
      const res = await fetch(`${STT_BASE}/v1/stt/backend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...AUTH_HEADER },
        body: JSON.stringify({ backend: target }),
      });
      if (!res.ok) throw new Error('switch failed');
      await res.json();
      await fetchBackend();
      showSwitchMsg(
        true,
        target === 'openai' ? 'Switched to OpenAI — new sessions use it'
          : target === 'groq' ? 'Switched to Groq Whisper — new sessions use it'
          : 'Switched to self-hosted Whisper — new sessions use it'
      );
    } catch {
      showSwitchMsg(false, 'Could not switch STT mode — is the STT service running?');
    } finally {
      setSwitching(false);
    }
  };

  const resetCounter = async () => {
    try {
      const res = await fetch(`${STT_BASE}/v1/usage_stt/reset`, {
        method: 'POST',
        headers: { ...AUTH_HEADER },
      });
      if (!res.ok) throw new Error('reset failed');
      await fetchUsage();
    } catch {
      setUnreachable(true);
    }
  };

  // Derived values (safe defaults while loading)
  const totalCalls = usage ? Number(usage.total_calls) || 0 : 0;
  const totalMinutes = usage ? Number(usage.total_minutes) || 0 : 0;
  const totalCostUsd = usage ? Number(usage.est_cost_usd) || 0 : 0;
  const byModel = usage && Array.isArray(usage.by_model) ? usage.by_model : [];

  const activeBackend = backendInfo ? backendInfo.backend : null;
  const openaiReady = backendInfo ? !!backendInfo.openai_ready : false;
  const openaiModel = (backendInfo && backendInfo.openai_model) || 'gpt-4o-transcribe';
  const groqReady = backendInfo ? !!backendInfo.groq_ready : false;
  const groqModel = (backendInfo && backendInfo.groq_model) || 'whisper-large-v3';

  const currentRateUsd =
    activeBackend === 'openai' ? RATES_USD_PER_MIN[openaiModel] || 0.006
      : activeBackend === 'groq' ? RATES_USD_PER_MIN[groqModel] || 0.00185 : 0;
  const currentRateLabel =
    activeBackend === 'openai' ? `${money(currentRateUsd)}/min (${openaiModel})`
      : activeBackend === 'groq' ? `${money(currentRateUsd)}/min (${groqModel})`
      : `${money(0)}/min (self-hosted, free)`;

  const estMinutesNum = Math.max(0, Number(estMinutes) || 0);
  const estCostUsd = estMinutesNum * (RATES_USD_PER_MIN[estModel] || 0);

  const inrPerMinOpenai = (RATES_USD_PER_MIN[openaiModel] || 0.006) * usdInr;
  const inrPerMinGroq = (RATES_USD_PER_MIN[groqModel] || 0.00185) * usdInr;
  const backendLabel = activeBackend === 'openai' ? 'OpenAI'
    : activeBackend === 'groq' ? 'Groq' : 'Whisper';

  const focusRing =
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40 focus-visible:ring-offset-2 focus-visible:ring-offset-black';

  return (
    <div className="min-h-screen bg-black text-white px-6 py-8 md:px-10">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Header */}
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Insights <span className="text-white/55 font-normal">— STT usage &amp; cost</span>
            </h1>
            <p className="mt-1 text-sm text-white/55">
              Compare self-hosted (free) vs OpenAI (paid, ChatGPT-grade), and track exactly what
              you spend.
            </p>
          </div>

          {/* Currency toggle */}
          <div
            className="inline-flex shrink-0 items-center rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-1"
            role="group"
            aria-label="Display currency"
          >
            <button
              type="button"
              aria-pressed={currency === 'USD'}
              onClick={() => setCurrency('USD')}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${focusRing} ${
                currency === 'USD' ? 'bg-white text-black' : 'text-white/55 hover:text-white'
              }`}
            >
              $ USD
            </button>
            <button
              type="button"
              aria-pressed={currency === 'INR'}
              onClick={() => setCurrency('INR')}
              className={`rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ${focusRing} ${
                currency === 'INR' ? 'bg-white text-black' : 'text-white/55 hover:text-white'
              }`}
            >
              ₹ INR
            </button>
          </div>
        </div>

        {/* Unreachable banner */}
        {unreachable && (
          <div className="rounded-xl border border-[#e5484d]/40 bg-[#e5484d]/10 px-4 py-3 text-sm text-[#e5484d]">
            STT service unreachable at {STT_BASE}. Start the STT service and hit Refresh.
          </div>
        )}

        {/* STT Mode switcher */}
        <section className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold">STT Mode</h2>
            {activeBackend && (
              <span className="rounded-full border border-white/10 px-2.5 py-0.5 text-xs text-white/55">
                active: <span className="text-white">{backendLabel}</span>
              </span>
            )}
          </div>

          <div className="mt-4 grid gap-4 md:grid-cols-3">
            {/* Whisper card */}
            <button
              type="button"
              aria-pressed={activeBackend === 'whisper'}
              disabled={switching}
              onClick={() => switchBackend('whisper')}
              className={`rounded-xl border p-5 text-left transition-colors disabled:cursor-wait ${focusRing} ${
                activeBackend === 'whisper'
                  ? 'border-white/40 ring-1 ring-white/20 bg-white/[0.06]'
                  : 'border-white/10 hover:border-white/30'
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold">Self-hosted Whisper</span>
                <span className="rounded-full bg-[#3fb950]/15 px-2.5 py-0.5 text-xs font-semibold text-[#3fb950]">
                  FREE
                </span>
              </div>
              <p className="mt-2 text-xs text-white/55">
                runs on your hardware · ₹0/min · slower on CPU
              </p>
            </button>

            {/* OpenAI card */}
            <button
              type="button"
              aria-pressed={activeBackend === 'openai'}
              disabled={switching || !openaiReady}
              onClick={() => switchBackend('openai')}
              className={`rounded-xl border p-5 text-left transition-colors ${focusRing} ${
                activeBackend === 'openai'
                  ? 'border-white/40 ring-1 ring-white/20 bg-white/[0.06]'
                  : 'border-white/10 hover:border-white/30'
              } ${!openaiReady ? 'cursor-not-allowed opacity-50 hover:border-white/10' : ''} ${
                switching ? 'cursor-wait' : ''
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold">OpenAI {openaiModel}</span>
                <span className="rounded-full bg-[#e3b341]/15 px-2.5 py-0.5 text-xs font-semibold text-[#e3b341] tabular-nums">
                  PAID ~₹{inrPerMinOpenai.toFixed(2)}/min
                </span>
              </div>
              <p className="mt-2 text-xs text-white/55">ChatGPT-grade accuracy · ~1–2s · cloud</p>
              {!openaiReady && (
                <p className="mt-2 text-xs text-[#e3b341]">
                  Set OPENAI_API_KEY on the server to enable
                </p>
              )}
            </button>

            {/* Groq card */}
            <button
              type="button"
              aria-pressed={activeBackend === 'groq'}
              disabled={switching || !groqReady}
              onClick={() => switchBackend('groq')}
              className={`rounded-xl border p-5 text-left transition-colors ${focusRing} ${
                activeBackend === 'groq'
                  ? 'border-white/40 ring-1 ring-white/20 bg-white/[0.06]'
                  : 'border-white/10 hover:border-white/30'
              } ${!groqReady ? 'cursor-not-allowed opacity-50 hover:border-white/10' : ''} ${
                switching ? 'cursor-wait' : ''
              }`}
            >
              <div className="flex items-center justify-between gap-3">
                <span className="text-sm font-semibold">Groq {groqModel}</span>
                <span className="rounded-full bg-[#3fb950]/15 px-2.5 py-0.5 text-xs font-semibold text-[#3fb950] tabular-nums">
                  ~₹{inrPerMinGroq.toFixed(2)}/min
                </span>
              </div>
              <p className="mt-2 text-xs text-white/55">same accuracy · ~1s (fastest) · ~3× cheaper</p>
              {!groqReady && (
                <p className="mt-2 text-xs text-[#e3b341]">
                  Set GROQ_API_KEY on the server to enable
                </p>
              )}
            </button>
          </div>

          {switchMsg && (
            <p
              role="status"
              className={`mt-3 text-sm ${switchMsg.ok ? 'text-[#3fb950]' : 'text-[#e5484d]'}`}
            >
              {switchMsg.text}
            </p>
          )}

          <p className="mt-3 text-xs text-white/55">
            Switching affects the next conversation you start. The API key stays on the server —
            never sent to your browser.
          </p>
        </section>

        {/* Stat tiles */}
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
            <p className="text-xs uppercase tracking-wide text-white/55">Total calls</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {totalCalls.toLocaleString()}
            </p>
            <p className="mt-1 text-xs text-white/55">transcription requests</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
            <p className="text-xs uppercase tracking-wide text-white/55">Speech transcribed</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {totalMinutes.toFixed(2)}{' '}
              <span className="text-sm font-normal text-white/55">min</span>
            </p>
            <p className="mt-1 text-xs text-white/55">silence excluded</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
            <p className="text-xs uppercase tracking-wide text-white/55">Total cost</p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-white">
              {money(totalCostUsd)}
            </p>
            <p className="mt-1 text-xs text-white/55">estimated, all models</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
            <p className="text-xs uppercase tracking-wide text-white/55">Avg cost / min</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {totalMinutes > 0 ? money(totalCostUsd / totalMinutes) : '—'}
            </p>
            <p className="mt-1 text-xs text-white/55">per minute of speech</p>
          </div>
        </section>

        {/* Explainer */}
        <section className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
          <h2 className="text-sm font-semibold text-white/55">What&apos;s being counted</h2>
          <p className="mt-2 text-sm leading-relaxed">
            You&apos;ve made{' '}
            <span className="font-semibold tabular-nums">{totalCalls.toLocaleString()}</span>{' '}
            transcription calls covering{' '}
            <span className="font-semibold tabular-nums">{totalMinutes.toFixed(2)}</span> minutes
            of speech. Each call = one thing you said (one turn). Only your speech is billed —
            silence is skipped by the voice detector. At{' '}
            <span className="font-semibold tabular-nums">{currentRateLabel}</span>, that&apos;s{' '}
            <span className="font-semibold tabular-nums">{money(totalCostUsd)}</span> so far.
          </p>
        </section>

        {/* Per-model table */}
        <section className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-6">
          <h2 className="text-base font-semibold">Usage by model</h2>
          {byModel.length === 0 ? (
            <p className="mt-4 text-sm text-white/55">
              No OpenAI calls yet — switch to OpenAI mode and talk to the agent.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-white/55">
                    <th scope="col" className="pb-2 pr-4 font-medium">
                      Model
                    </th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">
                      Calls
                    </th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">
                      Minutes
                    </th>
                    <th scope="col" className="pb-2 text-right font-medium">
                      Cost ({currency === 'INR' ? '₹' : '$'})
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {byModel.map((row) => (
                    <tr key={row.model} className="border-b border-white/10/60 last:border-0">
                      <td className="py-2.5 pr-4 font-medium">{row.model}</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">
                        {(Number(row.calls) || 0).toLocaleString()}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">
                        {(Number(row.minutes) || 0).toFixed(2)}
                      </td>
                      <td className="py-2.5 text-right tabular-nums">{money(row.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {/* Rate card + estimator */}
        <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-6">
            <h2 className="text-base font-semibold">Rate card</h2>
            <ul className="mt-4 space-y-3 text-sm">
              <li className="flex items-center justify-between border-b border-white/10/60 pb-3">
                <span>gpt-4o-transcribe</span>
                <span className="tabular-nums">
                  {money(0.006)}
                  <span className="text-white/55">/min</span>
                </span>
              </li>
              <li className="flex items-center justify-between border-b border-white/10/60 pb-3">
                <span>gpt-4o-mini-transcribe</span>
                <span className="tabular-nums">
                  {money(0.003)}
                  <span className="text-white/55">/min</span>
                </span>
              </li>
              <li className="flex items-center justify-between">
                <span>Self-hosted Whisper</span>
                <span className="font-semibold text-[#3fb950]">free</span>
              </li>
            </ul>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-6">
            <h2 className="text-base font-semibold">Monthly estimator</h2>
            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              <label className="flex-1 text-xs text-white/55">
                minutes of speech per month
                <input
                  type="number"
                  min="0"
                  value={estMinutes}
                  onChange={(e) => setEstMinutes(e.target.value)}
                  className={`mt-1 w-full rounded-lg border border-white/10 bg-black px-3 py-2 text-sm text-white tabular-nums ${focusRing}`}
                />
              </label>
              <label className="flex-1 text-xs text-white/55">
                model
                <select
                  value={estModel}
                  onChange={(e) => setEstModel(e.target.value)}
                  className={`mt-1 w-full rounded-lg border border-white/10 bg-black px-3 py-2 text-sm text-white ${focusRing}`}
                >
                  <option value="gpt-4o-transcribe">gpt-4o-transcribe</option>
                  <option value="gpt-4o-mini-transcribe">gpt-4o-mini-transcribe</option>
                </select>
              </label>
            </div>
            <p className="mt-4 text-sm text-white/55">
              Projected monthly cost:{' '}
              <span className="text-xl font-semibold tabular-nums text-white">
                {money(estCostUsd)}
              </span>
            </p>
          </div>
        </section>

        {/* Controls */}
        <section className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={refreshAll}
            className={`rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl px-4 py-2 text-sm font-medium hover:border-white/40 transition-colors ${focusRing}`}
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={resetCounter}
            className={`rounded-xl border border-[#e5484d]/40 bg-white/[0.03] backdrop-blur-xl px-4 py-2 text-sm font-medium text-[#e5484d] hover:bg-[#e5484d]/10 transition-colors ${focusRing}`}
          >
            Reset counter
          </button>
          <span className="text-xs text-white/55">auto-refreshes every 10s</span>
        </section>
      </div>
    </div>
  );
}
