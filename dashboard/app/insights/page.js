'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { apiBase } from '../lib/api';
const STT_BASE = apiBase(8001); // stt-service (direct :8001, or same-origin behind the tunnel)
const LLM_BASE = apiBase(8003); // conversation-service (LLM usage)
const AUTH_HEADER = { Authorization: 'Bearer dev-test-key' };

const RATES_USD_PER_MIN = {
  'gpt-4o-transcribe': 0.006,
  'gpt-4o-mini-transcribe': 0.003,
  'whisper-1': 0.006,
  'whisper-large-v3': 0.00185,          // Groq — same accuracy, ~3x cheaper
  'whisper-large-v3-turbo': 0.000667,   // Groq — cheapest
  'distil-whisper-large-v3-en': 0.000333,
};

// which provider bills each STT model (for the per-provider bill split)
const GROQ_STT_MODELS = ['whisper-large-v3', 'whisper-large-v3-turbo', 'distil-whisper-large-v3-en'];
const isGroqStt = (m) => GROQ_STT_MODELS.includes(m);
const isGroqLlm = (m) => (m || '').includes('groq') || (m || '').includes('llama');

export default function InsightsPage() {
  const [currency, setCurrency] = useState('INR'); // 'USD' | 'INR'
  const [usage, setUsage] = useState(null);
  const [llm, setLlm] = useState(null); // real LLM usage (tokens + cost)
  const [backendInfo, setBackendInfo] = useState(null);
  const [unreachable, setUnreachable] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [switchMsg, setSwitchMsg] = useState(null); // { ok: boolean, text: string }
  const [estMinutes, setEstMinutes] = useState(300);
  const [estModel, setEstModel] = useState('whisper-large-v3-turbo');
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

  const fetchLlm = useCallback(async () => {
    try {
      const res = await fetch(`${LLM_BASE}/v1/usage_llm`, { cache: 'no-store' });
      if (!res.ok) throw new Error('bad status');
      setLlm(await res.json());
    } catch {
      /* LLM usage panel just shows — until reachable */
    }
  }, []);

  const refreshAll = useCallback(() => {
    fetchUsage();
    fetchBackend();
    fetchLlm();
  }, [fetchUsage, fetchBackend, fetchLlm]);

  useEffect(() => {
    refreshAll();
    const id = setInterval(() => {
      fetchUsage();
      fetchLlm();
    }, 10000);
    return () => {
      clearInterval(id);
      if (switchMsgTimer.current) clearTimeout(switchMsgTimer.current);
    };
  }, [refreshAll, fetchUsage, fetchLlm]);

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
      // reset the LLM counter too so both halves of the bill restart together
      try {
        await fetch(`${LLM_BASE}/v1/usage_llm/reset`, { method: 'POST', headers: { ...AUTH_HEADER } });
      } catch { /* llm reset optional */ }
      await fetchUsage();
      await fetchLlm();
    } catch {
      setUnreachable(true);
    }
  };

  // Derived values (safe defaults while loading)
  const totalCalls = usage ? Number(usage.total_calls) || 0 : 0;
  const totalMinutes = usage ? Number(usage.total_minutes) || 0 : 0;
  const totalCostUsd = usage ? Number(usage.est_cost_usd) || 0 : 0;
  const byModel = usage && Array.isArray(usage.by_model) ? usage.by_model : [];

  // LLM usage (real logged token counts from the conversation service)
  const llmByModel = llm && Array.isArray(llm.by_model) ? llm.by_model : [];
  const llmCalls = llm ? Number(llm.total_calls) || 0 : 0;
  const llmTokensIn = llm ? Number(llm.prompt_tokens) || 0 : 0;
  const llmTokensOut = llm ? Number(llm.completion_tokens) || 0 : 0;
  const llmCostUsd = llm ? Number(llm.est_cost_usd) || 0 : 0;

  // per-provider bill split: measured usage × official list price
  const groqSttUsd = byModel.filter((r) => isGroqStt(r.model))
    .reduce((s, r) => s + (Number(r.cost_usd) || 0), 0);
  const openaiSttUsd = byModel.filter((r) => !isGroqStt(r.model))
    .reduce((s, r) => s + (Number(r.cost_usd) || 0), 0);
  const groqLlmUsd = llmByModel.filter((r) => isGroqLlm(r.model))
    .reduce((s, r) => s + (Number(r.cost_usd) || 0), 0);
  const openaiLlmUsd = llmByModel.filter((r) => !isGroqLlm(r.model))
    .reduce((s, r) => s + (Number(r.cost_usd) || 0), 0);
  const groqBillUsd = groqSttUsd + groqLlmUsd;
  const openaiBillUsd = openaiSttUsd + openaiLlmUsd;

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
              Insights <span className="text-white/55 font-normal">— usage &amp; billing</span>
            </h1>
            <p className="mt-1 text-sm text-white/55">
              Every STT call and LLM turn is logged on our server. Money shown = that measured
              usage × the provider&apos;s official list price.
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

        {/* Estimated bill by provider — the headline numbers */}
        <section className="grid gap-4 md:grid-cols-2">
          <div className="rounded-xl border border-[#3fb950]/30 bg-[#3fb950]/[0.04] backdrop-blur-xl p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">Groq — estimated bill</h2>
              <span className="rounded-full bg-[#3fb950]/15 px-2.5 py-0.5 text-xs font-semibold text-[#3fb950]">
                billed key
              </span>
            </div>
            <p className="mt-3 text-3xl font-bold tabular-nums">{money(groqBillUsd)}</p>
            <ul className="mt-3 space-y-1.5 text-sm text-white/70">
              <li className="flex justify-between">
                <span>Transcription (Whisper)</span>
                <span className="tabular-nums">{money(groqSttUsd)}</span>
              </li>
              <li className="flex justify-between">
                <span>LLM (Llama, {llmTokensIn.toLocaleString()} in / {llmTokensOut.toLocaleString()} out tokens)</span>
                <span className="tabular-nums">{money(groqLlmUsd)}</span>
              </li>
            </ul>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-6">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold">OpenAI — estimated bill</h2>
              <span className="rounded-full border border-white/10 px-2.5 py-0.5 text-xs text-white/55">
                backup
              </span>
            </div>
            <p className="mt-3 text-3xl font-bold tabular-nums">{money(openaiBillUsd)}</p>
            <ul className="mt-3 space-y-1.5 text-sm text-white/70">
              <li className="flex justify-between">
                <span>Transcription (gpt-4o / whisper-1)</span>
                <span className="tabular-nums">{money(openaiSttUsd)}</span>
              </li>
              <li className="flex justify-between">
                <span>LLM</span>
                <span className="tabular-nums">{money(openaiLlmUsd)}</span>
              </li>
            </ul>
          </div>

          <p className="text-xs text-white/45 md:col-span-2">
            These are computed from calls logged on <em>our</em> server × official list prices —
            they are estimates, not the invoice. The authoritative bill is the provider console
            (console.groq.com → Usage / platform.openai.com → Usage). Kokoro TTS is self-hosted:
            ₹0, nothing billed.
          </p>
        </section>

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
            <p className="text-xs uppercase tracking-wide text-white/55">STT calls</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {totalCalls.toLocaleString()}
            </p>
            <p className="mt-1 text-xs text-white/55">each = one thing you said</p>
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
            <p className="text-xs uppercase tracking-wide text-white/55">STT cost</p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-white">
              {money(totalCostUsd)}
            </p>
            <p className="mt-1 text-xs text-white/55">all STT models combined</p>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
            <p className="text-xs uppercase tracking-wide text-white/55">Avg cost / min</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">
              {totalMinutes > 0 ? money(totalCostUsd / totalMinutes) : '—'}
            </p>
            <p className="mt-1 text-xs text-white/55">per minute of speech</p>
          </div>
        </section>

        {/* LLM tiles — the other half of the Groq key */}
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
            <p className="text-xs uppercase tracking-wide text-white/55">LLM turns</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">{llmCalls.toLocaleString()}</p>
            <p className="mt-1 text-xs text-white/55">agent replies generated</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
            <p className="text-xs uppercase tracking-wide text-white/55">Tokens in</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">{llmTokensIn.toLocaleString()}</p>
            <p className="mt-1 text-xs text-white/55">prompt + conversation history</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
            <p className="text-xs uppercase tracking-wide text-white/55">Tokens out</p>
            <p className="mt-2 text-2xl font-semibold tabular-nums">{llmTokensOut.toLocaleString()}</p>
            <p className="mt-1 text-xs text-white/55">what the agent said</p>
          </div>
          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
            <p className="text-xs uppercase tracking-wide text-white/55">LLM cost</p>
            <p className="mt-2 text-3xl font-bold tabular-nums text-white">{money(llmCostUsd)}</p>
            <p className="mt-1 text-xs text-white/55">
              {llm && llm.estimated_calls > 0
                ? `${llm.estimated_calls} of ${llmCalls} calls token-counted locally`
                : 'exact token counts from the API'}
            </p>
          </div>
        </section>

        {/* Explainer */}
        <section className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-5">
          <h2 className="text-sm font-semibold text-white/55">What&apos;s being counted</h2>
          <p className="mt-2 text-sm leading-relaxed">
            Every turn is logged twice: the STT call that heard you (
            <span className="font-semibold tabular-nums">{totalCalls.toLocaleString()}</span> calls,{' '}
            <span className="font-semibold tabular-nums">{totalMinutes.toFixed(2)}</span> min of
            speech — silence is never billed) and the LLM call that generated the reply (
            <span className="font-semibold tabular-nums">{llmCalls.toLocaleString()}</span> turns,{' '}
            <span className="font-semibold tabular-nums">
              {(llmTokensIn + llmTokensOut).toLocaleString()}
            </span>{' '}
            tokens). Current STT rate:{' '}
            <span className="font-semibold tabular-nums">{currentRateLabel}</span>. TTS (Kokoro) is
            self-hosted — <span className="font-semibold">₹0, unmetered</span>.
          </p>
        </section>

        {/* Per-model table */}
        <section className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-6">
          <h2 className="text-base font-semibold">STT usage by model</h2>
          {byModel.length === 0 ? (
            <p className="mt-4 text-sm text-white/55">
              No cloud STT calls logged yet — talk to the agent and this fills in live.
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

        {/* LLM usage by model */}
        {llmByModel.length > 0 && (
          <section className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-6">
            <h2 className="text-base font-semibold">LLM usage by model</h2>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-left text-xs uppercase tracking-wide text-white/55">
                    <th scope="col" className="pb-2 pr-4 font-medium">Model</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">Turns</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">Tokens in</th>
                    <th scope="col" className="pb-2 pr-4 text-right font-medium">Tokens out</th>
                    <th scope="col" className="pb-2 text-right font-medium">
                      Cost ({currency === 'INR' ? '₹' : '$'})
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {llmByModel.map((row) => (
                    <tr key={row.model} className="border-b border-white/10/60 last:border-0">
                      <td className="py-2.5 pr-4 font-medium">{row.model}</td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">
                        {(Number(row.calls) || 0).toLocaleString()}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">
                        {(Number(row.prompt_tokens) || 0).toLocaleString()}
                      </td>
                      <td className="py-2.5 pr-4 text-right tabular-nums">
                        {(Number(row.completion_tokens) || 0).toLocaleString()}
                      </td>
                      <td className="py-2.5 text-right tabular-nums">{money(row.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Rate card + estimator */}
        <section className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-white/[0.03] backdrop-blur-xl p-6">
            <h2 className="text-base font-semibold">Rate card (official list prices)</h2>
            <ul className="mt-4 space-y-3 text-sm">
              <li className="flex items-center justify-between border-b border-white/10/60 pb-3">
                <span>
                  Groq whisper-large-v3-turbo{' '}
                  <span className="rounded-full bg-[#3fb950]/15 px-2 py-0.5 text-[10px] font-semibold text-[#3fb950]">
                    ACTIVE STT
                  </span>
                </span>
                <span className="tabular-nums">
                  {money(0.000667)}
                  <span className="text-white/55">/min</span>
                </span>
              </li>
              <li className="flex items-center justify-between border-b border-white/10/60 pb-3">
                <span>Groq whisper-large-v3</span>
                <span className="tabular-nums">
                  {money(0.00185)}
                  <span className="text-white/55">/min</span>
                </span>
              </li>
              <li className="flex items-center justify-between border-b border-white/10/60 pb-3">
                <span>Groq Llama 3.3 70B (LLM)</span>
                <span className="tabular-nums text-xs">
                  {money(0.59)} <span className="text-white/55">in</span> · {money(0.79)}{' '}
                  <span className="text-white/55">out /1M tokens</span>
                </span>
              </li>
              <li className="flex items-center justify-between border-b border-white/10/60 pb-3">
                <span>OpenAI gpt-4o-transcribe</span>
                <span className="tabular-nums">
                  {money(0.006)}
                  <span className="text-white/55">/min</span>
                </span>
              </li>
              <li className="flex items-center justify-between border-b border-white/10/60 pb-3">
                <span>OpenAI gpt-4o-mini-transcribe</span>
                <span className="tabular-nums">
                  {money(0.003)}
                  <span className="text-white/55">/min</span>
                </span>
              </li>
              <li className="flex items-center justify-between">
                <span>Self-hosted Whisper · Kokoro TTS</span>
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
                  <option value="whisper-large-v3-turbo">Groq whisper-large-v3-turbo (active)</option>
                  <option value="whisper-large-v3">Groq whisper-large-v3</option>
                  <option value="gpt-4o-transcribe">OpenAI gpt-4o-transcribe</option>
                  <option value="gpt-4o-mini-transcribe">OpenAI gpt-4o-mini-transcribe</option>
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
