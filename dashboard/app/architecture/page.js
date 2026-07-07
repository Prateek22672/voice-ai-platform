'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { apiBase } from '../lib/api';

const FX = 85; // ≈ ₹85 / $1

/* ---------- small presentational helpers (self-contained) ---------- */

function Card({ children, className = '' }) {
  return (
    <div
      className={`rounded-2xl border border-white/10 bg-white/[0.03] p-5 backdrop-blur-xl md:p-6 ${className}`}
    >
      {children}
    </div>
  );
}

function Tag({ tone = 'muted', children }) {
  const tones = {
    muted: 'bg-white/[0.06] text-white/60 border-white/10',
    green: 'bg-[#3fb950]/10 text-[#3fb950] border-[#3fb950]/30',
    red: 'bg-[#e5484d]/10 text-[#e5484d] border-[#e5484d]/30',
    amber: 'bg-[#e3b341]/10 text-[#e3b341] border-[#e3b341]/30',
    white: 'bg-white/10 text-white border-white/20',
  };
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-[11px] font-medium tracking-wide ${tones[tone] || tones.muted}`}
    >
      {children}
    </span>
  );
}

function SectionHeading({ kicker, title, intro }) {
  return (
    <div className="mb-8">
      {kicker ? (
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-white/40">
          {kicker}
        </p>
      ) : null}
      <h2 className="text-balance text-2xl font-semibold tracking-tight text-white md:text-3xl">
        {title}
      </h2>
      {intro ? (
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-white/60 md:text-base">
          {intro}
        </p>
      ) : null}
    </div>
  );
}

/* ------------------------------ page ------------------------------ */

export default function ArchitecturePage() {
  const [currency, setCurrency] = useState('INR'); // default ₹
  const [usage, setUsage] = useState(null); // live STT usage or null

  /* money(inr): format an INR amount in the selected currency */
  const money = useCallback(
    (inr, opts = {}) => {
      if (inr === null || inr === undefined || Number.isNaN(Number(inr))) return '—';
      const n = Number(inr);
      if (currency === 'USD') {
        const usd = n / FX;
        return `$${usd.toLocaleString('en-US', {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })}`;
      }
      const maxFrac = opts.maxFrac !== undefined ? opts.maxFrac : n < 100 ? 2 : 0;
      return `₹${n.toLocaleString('en-IN', {
        minimumFractionDigits: 0,
        maximumFractionDigits: maxFrac,
      })}`;
    },
    [currency]
  );

  /* range helper, e.g. ₹500–800 */
  const moneyRange = useCallback(
    (loInr, hiInr) => `${money(loInr)}–${money(hiInr)}`,
    [money]
  );

  /* live OpenAI STT usage — the only truly live number on this page */
  useEffect(() => {
    let cancelled = false;

    async function fetchUsage() {
      try {
        const res = await fetch(`${apiBase(8001)}/v1/usage_stt`, {
          cache: 'no-store',
        });
        if (!res.ok) throw new Error('bad status');
        const data = await res.json();
        if (!cancelled && data && typeof data === 'object') setUsage(data);
      } catch (e) {
        if (!cancelled) setUsage(null); // fail quietly → "—"
      }
    }

    fetchUsage();
    const id = setInterval(fetchUsage, 15000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const liveText = useMemo(() => {
    if (!usage) {
      return { calls: '—', minutes: '—', cost: '—', mode: '—' };
    }
    const calls =
      usage.total_calls !== undefined && usage.total_calls !== null
        ? Number(usage.total_calls).toLocaleString('en-IN')
        : '—';
    const minutes =
      usage.total_minutes !== undefined && usage.total_minutes !== null
        ? Number(usage.total_minutes).toLocaleString('en-IN', {
            maximumFractionDigits: 1,
          })
        : '—';
    const cost =
      usage.est_cost_inr !== undefined && usage.est_cost_inr !== null
        ? money(usage.est_cost_inr, { maxFrac: 2 })
        : '—';
    const mode = usage.backend || '—';
    return { calls, minutes, cost, mode };
  }, [usage, money]);

  /* ------------------------- static data ------------------------- */

  const pipelineCards = [
    {
      name: 'Voice Activity Detection',
      tech: 'Silero VAD (ONNX)',
      role: 'Detects when you are speaking vs silence, and decides turn-taking — when the AI should listen and when it should reply.',
      runs: 'Our server (tiny model, CPU is fine)',
      costInr: 0,
      costNote: '/min',
      improve: 'Add a semantic endpointing model so it knows when a sentence is truly finished, not just when audio goes quiet.',
    },
    {
      name: 'Speech-to-Text',
      tech: 'Groq whisper-large-v3-turbo (default) · faster-whisper / OpenAI (swappable)',
      role: 'Turns your speech into text the brain can read — wrapped in our own audio clean-up, domain biasing and confidence-based gibberish rejection.',
      runs: 'Groq cloud (default) · our server or OpenAI (swappable)',
      costInr: null,
      costCustom: 'dual', // rendered specially
      improve: 'Switch engines live from Insights; large-v3 on a GPU for top self-hosted accuracy, or OpenAI gpt-4o-transcribe for maximum accuracy with zero hardware.',
    },
    {
      name: 'The Brain (LLM)',
      tech: 'Groq · Llama 3.3 70B via litellm',
      role: 'Reads the transcript and decides what to say next — the intelligence of the call.',
      runs: 'Groq cloud, ~225ms responses',
      costInr: 0.17,
      costNote: '/min · estimate',
      improve: 'litellm means we can swap to any model (GPT, Claude, Gemini, local) by changing one line.',
    },
    {
      name: 'Text-to-Speech',
      tech: 'Kokoro-82M (neural) · F5-TTS for cloning',
      role: 'Speaks the reply in a natural human voice; F5-TTS adds voice cloning of real people.',
      runs: 'Our GPU (CPU works, but ~7s per reply)',
      costInr: 0,
      costNote: '/min',
      improve: 'A GPU makes it real-time and unlocks cloned employee voices.',
    },
    {
      name: 'Realtime Gateway',
      tech: 'FastAPI WebSocket + browser Web Audio',
      role: 'Full-duplex transport between mic and models: sentence-streaming, barge-in (interrupt the AI mid-sentence), half-duplex turn-taking.',
      runs: 'Our server',
      costInr: 0,
      costNote: '/min',
      improve: null,
    },
  ];

  const telephonyCards = [
    {
      name: 'Media Server',
      tech: 'Asterisk 20 · ARI + externalMedia · slin16 16kHz',
      role: 'Bridges the live phone call’s audio into our realtime gateway and back — the plumbing between the phone network and the AI.',
      thirdParty: 'None — fully self-hosted (SIP/RTP)',
      cost: 'free',
    },
    {
      name: 'SIP Carrier (the phone line)',
      tech: 'Plivo Zentrunk (India-licensed) · alt: Exotel / Acefone',
      role: 'The licensed link to the Indian PSTN. A plain VPS cannot legally terminate calls to Indian numbers — TRAI requires a licensed operator.',
      thirdParty: 'Plivo',
      cost: 'carrier',
    },
    {
      name: 'Compliance (India)',
      tech: 'DLT registration (TRAI TCCCPR)',
      role: 'DND/consent scrubbing, the 9am–9pm calling window, and AI-disclosure at call start. Not optional for outbound calling.',
      thirdParty: 'DLT platform (one-time registration)',
      cost: 'dlt',
    },
  ];

  const costRows = [
    {
      component: 'Voice (TTS)',
      old: { label: 'ElevenLabs', inr: 7.65 },
      ours: { label: 'Kokoro', inr: 0 },
    },
    {
      component: 'Transcription (STT)',
      old: { label: 'Whisper API', inr: 0.51 },
      ours: { label: 'self-hosted', inr: 0, alt: { label: 'or OpenAI', inr: 0.51 } },
    },
    {
      component: 'Brain (LLM)',
      old: { label: 'Groq', inr: 0.17 },
      ours: { label: 'Groq', inr: 0.17 },
    },
    {
      component: 'Phone line',
      old: { label: 'Twilio', inr: 0.45 },
      ours: { label: 'Plivo', inr: 0.45 },
    },
  ];

  const OLD_PER_MIN = 8.8;
  const OURS_PER_MIN = 0.62;
  const OURS_OPENAI_PER_MIN = 1.13;
  const SERVER_MONTHLY = 1000;

  const projections = [1000, 10000, 50000].map((mins) => ({
    mins,
    old: mins * OLD_PER_MIN,
    ours: mins * OURS_PER_MIN + SERVER_MONTHLY,
  }));

  const gpuOptions = [
    {
      option: 'Own GPU (RTX 3090 / 4060 Ti 16GB)',
      cost: `${moneyRange(60000, 90000)} once + ~${money(1000)}/mo power`,
      fit: 'Best long-run economics',
      tone: 'green',
    },
    {
      option: 'Cloud GPU part-time (L4, ~12h/day)',
      cost: `~${money(9000)}/mo`,
      fit: 'Testing / medium volume',
      tone: 'muted',
    },
    {
      option: 'Cloud GPU 24×7 (L4)',
      cost: `~${money(37000)}/mo`,
      fit: 'High, always-on volume',
      tone: 'muted',
    },
    {
      option: 'Serverless GPU (per-second billing)',
      cost: 'Scales with call volume',
      fit: 'Low or spiky traffic',
      tone: 'muted',
    },
  ];

  const accuracyStages = [
    {
      step: '1 · Clean the audio',
      when: 'Before STT',
      tone: 'green',
      desc: 'Every mic frame is DC-offset corrected, high-pass filtered to remove <80Hz rumble/hum, and peak-normalized to a consistent loudness. Whisper makes far fewer errors on clean, evenly-loud audio.',
    },
    {
      step: '2 · Bias for the domain',
      when: 'During STT',
      tone: 'muted',
      desc: 'A domain prompt (e.g. “a software-engineering job interview”) primes Whisper toward the right vocabulary, so names and technical terms are transcribed correctly instead of guessed.',
    },
    {
      step: '3 · Reject gibberish by confidence',
      when: 'During STT',
      tone: 'amber',
      desc: "We read Whisper's own confidence signals — average log-probability, no-speech probability, compression ratio. Low-confidence or noise-like results are dropped, so the model never invents a sentence from mumbling or background noise.",
    },
    {
      step: '4 · Clean the text',
      when: 'After STT',
      tone: 'muted',
      desc: 'Known hallucination phrases (“thank you for watching”, a stray “you.”) are stripped, and runaway word-repetition is collapsed.',
    },
  ];

  /* ------------------------------ render ------------------------------ */

  return (
    <main className="min-h-screen bg-[#0a0a0a] text-white antialiased">
      <div className="mx-auto max-w-6xl px-4 py-10 md:px-8 md:py-14">
        {/* top bar: back link + currency toggle */}
        <div className="mb-10 flex flex-wrap items-center justify-between gap-4">
          <a
            href="/"
            className="rounded-lg px-2 py-1 text-sm text-white/60 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
          >
            ← Overview
          </a>

          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-white/40 sm:inline">≈ ₹85 / $1</span>
            <div
              role="group"
              aria-label="Currency"
              className="flex overflow-hidden rounded-full border border-white/15 bg-white/[0.04] p-0.5 text-sm"
            >
              <button
                type="button"
                aria-pressed={currency === 'USD'}
                onClick={() => setCurrency('USD')}
                className={`rounded-full px-3.5 py-1.5 font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50 ${
                  currency === 'USD'
                    ? 'bg-white text-black'
                    : 'text-white/60 hover:text-white'
                }`}
              >
                $ USD
              </button>
              <button
                type="button"
                aria-pressed={currency === 'INR'}
                onClick={() => setCurrency('INR')}
                className={`rounded-full px-3.5 py-1.5 font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50 ${
                  currency === 'INR'
                    ? 'bg-white text-black'
                    : 'text-white/60 hover:text-white'
                }`}
              >
                ₹ INR
              </button>
            </div>
          </div>
        </div>

        {/* header */}
        <header className="mb-8">
          <h1 className="text-balance bg-gradient-to-b from-white to-white/70 bg-clip-text text-4xl font-semibold tracking-tight text-transparent md:text-5xl">
            Architecture &amp; Costs
          </h1>
          <p className="mt-4 max-w-3xl text-base leading-relaxed text-white/60 md:text-lg">
            How the voice pipeline and the phone system work — every technology, and exactly
            what it costs, old vs new.
          </p>
        </header>

        {/* live usage banner */}
        <div
          className="mb-16 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-4 backdrop-blur-xl"
          aria-live="polite"
        >
          <span className="relative flex h-2.5 w-2.5">
            <span
              className={`absolute inline-flex h-full w-full rounded-full ${
                usage ? 'animate-ping bg-[#3fb950]/60' : 'bg-white/20'
              }`}
            />
            <span
              className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                usage ? 'bg-[#3fb950]' : 'bg-white/30'
              }`}
            />
          </span>
          <span className="text-sm text-white/80">
            Live OpenAI STT usage:{' '}
            <strong className="font-semibold text-white tabular-nums">{liveText.calls}</strong>{' '}
            calls ·{' '}
            <strong className="font-semibold text-white tabular-nums">{liveText.minutes}</strong>{' '}
            min ·{' '}
            <strong className="font-semibold text-white tabular-nums">{liveText.cost}</strong>{' '}
            spent · mode:{' '}
            <strong className="font-semibold text-white">{liveText.mode}</strong>
          </span>
          <span className="ml-auto text-xs text-white/40">
            refreshes every 15s · every other figure on this page is an estimate
          </span>
        </div>

        {/* ============================ PART 1 ============================ */}
        <section className="mb-20" aria-labelledby="part1-title">
          <SectionHeading
            kicker="Part 1"
            title={
              <span id="part1-title">The Voice Pipeline — the brain &amp; voice</span>
            }
            intro="This half turns speech into a spoken AI reply. It runs on our servers."
          />

          <div className="grid gap-4 md:grid-cols-2">
            {pipelineCards.map((c) => (
              <Card key={c.name}>
                <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                  <h3 className="text-lg font-semibold text-white">{c.name}</h3>
                  {c.costCustom === 'dual' ? (
                    <span className="flex flex-col items-end gap-1">
                      <Tag tone="green">{money(0)}/min self-hosted</Tag>
                      <Tag tone="amber">{money(0.51)}/min OpenAI · estimate</Tag>
                    </span>
                  ) : (
                    <Tag tone={c.costInr === 0 ? 'green' : 'white'}>
                      <span className="tabular-nums">
                        {money(c.costInr)}
                        {c.costNote}
                      </span>
                    </Tag>
                  )}
                </div>
                <p className="text-sm leading-relaxed text-white/60">{c.role}</p>
                <dl className="mt-4 space-y-2 text-sm">
                  <div className="flex gap-2">
                    <dt className="w-16 shrink-0 text-white/40">Tech</dt>
                    <dd className="text-white/80">{c.tech}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-16 shrink-0 text-white/40">Runs on</dt>
                    <dd className="text-white/80">{c.runs}</dd>
                  </div>
                  {c.costCustom === 'dual' ? (
                    <div className="flex gap-2">
                      <dt className="w-16 shrink-0 text-white/40">Cost</dt>
                      <dd className="text-white/80">
                        <span className="tabular-nums text-[#3fb950]">{money(0)}/min</span>{' '}
                        self-hosted (needs a GPU for real-time), or{' '}
                        <span className="tabular-nums text-[#e3b341]">
                          {money(0.51)}/min
                        </span>{' '}
                        via OpenAI — ChatGPT-grade accuracy, no GPU needed.
                      </dd>
                    </div>
                  ) : null}
                  {c.improve ? (
                    <div className="flex gap-2">
                      <dt className="w-16 shrink-0 text-white/40">Improve</dt>
                      <dd className="text-white/60">{c.improve}</dd>
                    </div>
                  ) : null}
                </dl>
              </Card>
            ))}

            {/* Part 1 subtotal callout */}
            <Card className="border-[#3fb950]/30 bg-[#3fb950]/[0.05] md:col-span-2">
              <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#3fb950]">
                Part 1 subtotal · estimate
              </p>
              <p className="mt-2 text-lg text-white/80">
                Self-hosted voice ={' '}
                <strong className="tabular-nums text-white">~{money(0.17)}/min</strong> — just
                the LLM; STT, TTS and VAD are {money(0)} on our hardware. With OpenAI STT
                instead ={' '}
                <strong className="tabular-nums text-white">~{money(0.68)}/min</strong>.
              </p>
            </Card>
          </div>
        </section>

        {/* ===================== ACCURACY & ROBUSTNESS ===================== */}
        <section className="mb-20" aria-labelledby="accuracy-title">
          <SectionHeading
            kicker="Accuracy & robustness"
            title={<span id="accuracy-title">Keeping transcription clean — our own pipeline</span>}
            intro="Beyond the STT model, we wrap every utterance in our own audio + text processing so the agent hears you correctly and never invents words from noise."
          />

          <div className="grid gap-4 md:grid-cols-2">
            {accuracyStages.map((s) => (
              <Card key={s.step}>
                <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                  <h3 className="text-lg font-semibold text-white">{s.step}</h3>
                  <Tag tone={s.tone}>{s.when}</Tag>
                </div>
                <p className="text-sm leading-relaxed text-white/60">{s.desc}</p>
              </Card>
            ))}
          </div>

          {/* gibberish handling callout */}
          <Card className="mt-4 border-[#3fb950]/30 bg-[#3fb950]/[0.05]">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#3fb950]">
              How we handle gibberish
            </p>
            <p className="mt-2 text-lg text-white/80">
              Noise is dropped silently. Speech we can&rsquo;t understand triggers a gentle,{' '}
              <strong className="text-white">escalating re-prompt</strong> — &ldquo;Sorry, I
              didn&rsquo;t catch that, could you repeat?&rdquo; — never a wrong answer.
            </p>
            <p className="mt-2 text-sm leading-relaxed text-white/60">
              The core rule: uncertain text{' '}
              <strong className="text-white">never reaches the LLM</strong>, so the agent
              can&rsquo;t confidently respond to nonsense. The re-prompt escalates (repeat →
              speak louder → check your mic) and resets the instant you&rsquo;re understood.
            </p>
          </Card>
        </section>

        {/* ============================ PART 2 ============================ */}
        <section className="mb-20" aria-labelledby="part2-title">
          <SectionHeading
            kicker="Part 2"
            title={
              <span id="part2-title">
                Telephony — connecting to a real India phone number
              </span>
            }
            intro="This half connects the voice pipeline to the actual phone network so it can call and receive on a domestic Indian number."
          />

          <div className="grid gap-4 md:grid-cols-3">
            {telephonyCards.map((c) => (
              <Card key={c.name}>
                <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
                  <h3 className="text-lg font-semibold text-white">{c.name}</h3>
                  {c.cost === 'free' ? <Tag tone="green">{money(0)}/min</Tag> : null}
                  {c.cost === 'carrier' ? (
                    <Tag tone="amber">~{money(0.45)}/min · estimate</Tag>
                  ) : null}
                  {c.cost === 'dlt' ? <Tag tone="amber">one-time</Tag> : null}
                </div>
                <p className="text-sm leading-relaxed text-white/60">{c.role}</p>
                <dl className="mt-4 space-y-2 text-sm">
                  <div className="flex gap-2">
                    <dt className="w-20 shrink-0 text-white/40">Tech</dt>
                    <dd className="text-white/80">{c.tech}</dd>
                  </div>
                  <div className="flex gap-2">
                    <dt className="w-20 shrink-0 text-white/40">3rd-party</dt>
                    <dd className="text-white/80">{c.thirdParty}</dd>
                  </div>
                  {c.cost === 'carrier' ? (
                    <div className="flex gap-2">
                      <dt className="w-20 shrink-0 text-white/40">Cost</dt>
                      <dd className="text-white/80">
                        <span className="tabular-nums">~{money(0.45)}/min</span> domestic +
                        number rental{' '}
                        <span className="tabular-nums">{moneyRange(500, 800)}/mo</span>
                      </dd>
                    </div>
                  ) : null}
                  {c.cost === 'dlt' ? (
                    <div className="flex gap-2">
                      <dt className="w-20 shrink-0 text-white/40">Cost</dt>
                      <dd className="text-white/80">
                        One-time DLT{' '}
                        <span className="tabular-nums">{moneyRange(5000, 6000)}</span>
                      </dd>
                    </div>
                  ) : null}
                </dl>
              </Card>
            ))}
          </div>

          {/* Part 2 subtotal callout */}
          <Card className="mt-4 border-[#e3b341]/30 bg-[#e3b341]/[0.05]">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#e3b341]">
              Part 2 subtotal · estimate
            </p>
            <p className="mt-2 text-lg text-white/80">
              <strong className="tabular-nums text-white">~{money(0.45)}/min</strong> (the
              carrier) + a fixed monthly number rental + a one-time DLT registration.
            </p>
            <p className="mt-2 text-sm text-white/60">
              The phone-line cost is the same for <em>any</em> provider (it&rsquo;s licensed
              PSTN) — it&rsquo;s the one cost self-hosting can&rsquo;t remove.
            </p>
          </Card>
        </section>

        {/* ============================ TOTAL COST ============================ */}
        <section className="mb-20" aria-labelledby="total-title">
          <SectionHeading
            kicker="Total cost"
            title={<span id="total-title">Per minute, itemized</span>}
            intro="Every line of a one-minute call, old way (rented APIs) vs ours (self-hosted). All figures are estimates."
          />

          <Card className="p-0 md:p-0">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-white/40">
                    <th scope="col" className="px-5 py-4 font-medium">
                      Component
                    </th>
                    <th scope="col" className="px-5 py-4 font-medium text-[#e5484d]">
                      Old way (rented)
                    </th>
                    <th scope="col" className="px-5 py-4 font-medium text-[#3fb950]">
                      Ours (self-hosted)
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {costRows.map((r) => (
                    <tr key={r.component} className="border-b border-white/5">
                      <th
                        scope="row"
                        className="px-5 py-4 font-medium text-white/90"
                      >
                        {r.component}
                      </th>
                      <td className="px-5 py-4 text-white/70">
                        {r.old.label}{' '}
                        <span className="tabular-nums text-[#e5484d]">
                          {money(r.old.inr)}
                        </span>
                      </td>
                      <td className="px-5 py-4 text-white/70">
                        {r.ours.label}{' '}
                        <span
                          className={`tabular-nums ${
                            r.ours.inr === 0 ? 'text-[#3fb950]' : 'text-white'
                          }`}
                        >
                          {money(r.ours.inr)}
                        </span>
                        {r.ours.alt ? (
                          <span className="text-white/50">
                            {' '}
                            ({r.ours.alt.label}{' '}
                            <span className="tabular-nums">{money(r.ours.alt.inr)}</span>)
                          </span>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                  <tr className="bg-white/[0.03]">
                    <th scope="row" className="px-5 py-4 font-semibold text-white">
                      TOTAL / min
                    </th>
                    <td className="px-5 py-4 font-semibold tabular-nums text-[#e5484d]">
                      ~{money(OLD_PER_MIN)}
                    </td>
                    <td className="px-5 py-4 font-semibold text-[#3fb950]">
                      <span className="tabular-nums">~{money(OURS_PER_MIN)}</span>{' '}
                      (self-hosted){' '}
                      <span className="font-normal text-white/60">
                        / <span className="tabular-nums">~{money(OURS_OPENAI_PER_MIN)}</span>{' '}
                        (with OpenAI STT)
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Card>

          {/* savings highlight */}
          <Card className="mt-4 border-[#3fb950]/40 bg-[#3fb950]/[0.07]">
            <p className="text-balance text-xl font-semibold text-[#3fb950] md:text-2xl">
              You save <span className="tabular-nums">~{money(8.2)}/min</span> — about
              7–15× cheaper at scale
            </p>
          </Card>

          {/* monthly projection */}
          <div className="mt-8">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.15em] text-white/40">
              Monthly projection · estimates
            </h3>
            <Card className="p-0 md:p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[480px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-white/40">
                      <th scope="col" className="px-5 py-3 font-medium">
                        Minutes / month
                      </th>
                      <th scope="col" className="px-5 py-3 font-medium text-[#e5484d]">
                        Old way
                      </th>
                      <th scope="col" className="px-5 py-3 font-medium text-[#3fb950]">
                        Ours (self-hosted)
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {projections.map((p) => (
                      <tr key={p.mins} className="border-b border-white/5 last:border-0">
                        <th
                          scope="row"
                          className="px-5 py-3 font-medium tabular-nums text-white/90"
                        >
                          {p.mins.toLocaleString('en-IN')} min
                        </th>
                        <td className="px-5 py-3 tabular-nums text-[#e5484d]">
                          ~{money(p.old)}
                        </td>
                        <td className="px-5 py-3 tabular-nums text-[#3fb950]">
                          ~{money(p.ours)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="px-5 pb-4 pt-3 text-xs text-white/40">
                Old = minutes × ~{money(OLD_PER_MIN)}. Ours = minutes × ~{money(OURS_PER_MIN)}{' '}
                + ~{money(SERVER_MONTHLY)}/mo server. Estimates only.
              </p>
            </Card>
          </div>
        </section>

        {/* ============================ GPU ============================ */}
        <section className="mb-16" aria-labelledby="gpu-title">
          <SectionHeading
            kicker="Hardware"
            title={<span id="gpu-title">GPU — what it changes</span>}
            intro="The GPU question decides how much of the pipeline we can run in-house in real-time. Here is exactly what it does and doesn't affect."
          />

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <h3 className="mb-2 text-lg font-semibold text-white">What a GPU helps</h3>
              <p className="text-sm leading-relaxed text-white/60">
                It makes the STT and TTS neural networks run in{' '}
                <strong className="text-white">~0.1–1s</strong> instead of{' '}
                <strong className="text-white">7–35s</strong>. It&rsquo;s about{' '}
                <strong className="text-white">speed, not accuracy</strong> — large-v3 is
                just as accurate on CPU, only far slower.
              </p>
            </Card>

            <Card>
              <h3 className="mb-2 text-lg font-semibold text-white">Where it applies</h3>
              <p className="text-sm leading-relaxed text-white/60">
                Only <strong className="text-white">STT + TTS inference</strong>. It does{' '}
                <strong className="text-white">not</strong> affect the LLM (that runs on
                Groq&rsquo;s cloud) and <strong className="text-white">not</strong> the
                telephony half at all.
              </p>
            </Card>

            <Card>
              <h3 className="mb-2 text-lg font-semibold text-white">
                How we handle no-GPU right now
              </h3>
              <ol className="list-decimal space-y-2 pl-5 text-sm leading-relaxed text-white/60">
                <li>
                  OpenAI STT API — fast + ChatGPT-grade accuracy, no GPU, at{' '}
                  <span className="tabular-nums text-white">{money(0.51)}/min</span>.
                </li>
                <li>Small local Whisper — free, but noticeably weaker accuracy.</li>
                <li>
                  Kokoro TTS on CPU — works, but ~7s per reply (the remaining lag).
                </li>
              </ol>
            </Card>

            <Card className="border-[#e3b341]/30">
              <h3 className="mb-2 text-lg font-semibold text-[#e3b341]">
                Limitations right now (CPU-only)
              </h3>
              <ul className="list-disc space-y-2 pl-5 text-sm leading-relaxed text-white/60">
                <li>large-v3 is too slow (~35s per clip, and can run out of memory).</li>
                <li>Kokoro reply lag of ~7s.</li>
                <li>No voice cloning — F5-TTS needs a GPU.</li>
                <li>Can&rsquo;t get both top accuracy and real-time locally.</li>
              </ul>
            </Card>

            <Card className="border-[#3fb950]/30 md:col-span-2">
              <h3 className="mb-2 text-lg font-semibold text-[#3fb950]">
                Advantages with a GPU
              </h3>
              <ul className="grid list-disc gap-x-8 gap-y-2 pl-5 text-sm leading-relaxed text-white/60 md:grid-cols-2">
                <li>
                  Real-time large-v3 self-hosted — OpenAI-grade STT at{' '}
                  <span className="tabular-nums text-white">{money(0)}/min</span>.
                </li>
                <li>Real-time Kokoro speech.</li>
                <li>Voice cloning (F5-TTS) with real employee voices.</li>
                <li>Fully in-house: no per-minute API fees, DPDP-friendly data handling.</li>
              </ul>
            </Card>
          </div>

          {/* GPU cost table */}
          <div className="mt-8">
            <h3 className="mb-3 text-sm font-semibold uppercase tracking-[0.15em] text-white/40">
              GPU cost — cloud vs own · estimates
            </h3>
            <Card className="p-0 md:p-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <thead>
                    <tr className="border-b border-white/10 text-xs uppercase tracking-wider text-white/40">
                      <th scope="col" className="px-5 py-3 font-medium">
                        Option
                      </th>
                      <th scope="col" className="px-5 py-3 font-medium">
                        Cost
                      </th>
                      <th scope="col" className="px-5 py-3 font-medium">
                        Best for
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {gpuOptions.map((g) => (
                      <tr key={g.option} className="border-b border-white/5 last:border-0">
                        <th
                          scope="row"
                          className="px-5 py-3 font-medium text-white/90"
                        >
                          {g.option}
                        </th>
                        <td className="px-5 py-3 tabular-nums text-white/70">{g.cost}</td>
                        <td className="px-5 py-3">
                          <Tag tone={g.tone}>{g.fit}</Tag>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        </section>

        {/* footer note */}
        <footer className="border-t border-white/10 pt-6">
          <p className="max-w-3xl text-xs leading-relaxed text-white/40">
            Figures are engineering estimates at ~₹85/$ except the live OpenAI usage banner.
            The phone line is licensed PSTN (unavoidable in any model). GPU is the only real
            hardware cost — for production real-time; R&amp;D runs on the OpenAI API for
            pennies.
          </p>
        </footer>
      </div>
    </main>
  );
}
