'use client';

import { useCallback, useEffect, useState } from 'react';
import dynamic from 'next/dynamic';
import { ArrowRight, RefreshCw } from 'lucide-react';
import Button from './components/ui/Button';

const Beams = dynamic(
  () => import('./components/ui/ethereal-beams-hero').then((m) => m.Beams),
  { ssr: false }
);

const SERVICES = [
  {
    name: 'Voice Gateway',
    url: 'http://localhost:8000/health',
    port: 8000,
    desc: 'Realtime full-duplex voice sessions — the entry point your mic talks to.',
  },
  {
    name: 'Speech-to-Text',
    url: 'http://localhost:8001/health',
    port: 8001,
    desc: 'Transcribes speech to text. Swappable: self-hosted Whisper or OpenAI.',
  },
  {
    name: 'Text-to-Speech',
    url: 'http://localhost:8002/health',
    port: 8002,
    desc: 'Natural neural voice via Kokoro; supports cloned voices on F5-TTS.',
  },
  {
    name: 'Conversation / Groq',
    url: 'http://localhost:8003/health',
    port: 8003,
    desc: 'The brain — Groq Llama 3.3 70B, around 225ms per response.',
  },
  {
    name: 'Recording',
    url: 'http://localhost:8005/health',
    port: 8005,
    desc: 'Stores recordings and transcripts on your servers.',
  },
  {
    name: 'Analytics',
    url: 'http://localhost:8006/health',
    port: 8006,
    desc: 'Usage metrics, latency, cost basis.',
  },
  {
    name: 'API Gateway',
    url: 'http://localhost:8080/health',
    port: 8080,
    desc: 'Public REST front door with API keys.',
  },
];

const PIPELINE = ['You', 'Gateway', 'Whisper', 'Groq', 'Kokoro', 'You'];
const PIPELINE_SUBS = ['speak', 'session', 'speech to text', 'thinks', 'text to voice', 'hear reply'];

const STATS = [
  { value: '12', label: 'Services running' },
  { value: '~₹0.62', label: 'Cost / min, self-hosted' },
  { value: '225ms', label: 'LLM response' },
];

const WHY = [
  {
    title: 'Runs on your hardware',
    desc: 'No per-minute vendor fees — the whole stack lives on machines you control.',
  },
  {
    title: 'Your data stays in-house',
    desc: 'Recordings and transcripts never leave your servers. DPDP-friendly.',
  },
  {
    title: 'Swap models in one line',
    desc: 'Whisper or OpenAI, Kokoro or F5-TTS, any LLM — one env var each.',
  },
];

function StatusDot({ status }) {
  const color =
    status === 'up' ? 'bg-emerald-400' : status === 'down' ? 'bg-red-400' : 'bg-white/40';
  const pulse = status === 'checking' ? ' animate-pulse' : '';
  return (
    <span aria-hidden="true" className={`inline-block h-2 w-2 rounded-full ${color}${pulse}`} />
  );
}

export default function Overview() {
  const [status, setStatus] = useState({});
  const [checkedAt, setCheckedAt] = useState(null);

  const checkAll = useCallback(() => {
    setStatus(Object.fromEntries(SERVICES.map((s) => [s.port, 'checking'])));
    SERVICES.forEach((s) => {
      // Most services don't send CORS headers, so a no-cors reachability
      // probe is the reliable signal: resolve = running, reject = unreachable.
      fetch(`http://${window.location.hostname}:${s.port}/health`, { mode: 'no-cors', cache: 'no-store' })
        .then(() => setStatus((prev) => ({ ...prev, [s.port]: 'up' })))
        .catch(() => setStatus((prev) => ({ ...prev, [s.port]: 'down' })));
    });
    setCheckedAt(new Date());
  }, []);

  useEffect(() => {
    checkAll();
  }, [checkAll]);

  return (
    <div className="-mx-6 -mt-8 md:-mx-10 md:-mt-10">
      {/* ---------- Hero ---------- */}
      <section className="relative flex min-h-[85vh] items-center justify-center overflow-hidden">
        {/* Beams background — client-only; radial gradient is the pre-mount / fallback look */}
        <div
          aria-hidden="true"
          className="absolute inset-0 [background:radial-gradient(90%_70%_at_50%_20%,rgba(255,255,255,0.08),transparent_60%),#000]"
        >
          <Beams beamWidth={2} beamHeight={18} beamNumber={12} lightColor="#ffffff" speed={2} noiseIntensity={1.75} scale={0.2} rotation={30} />
        </div>
        {/* Readability overlay */}
        <div
          aria-hidden="true"
          className="absolute inset-0 bg-gradient-to-t from-black via-black/40 to-transparent"
        />

        <div className="relative z-10 mx-auto flex max-w-4xl flex-col items-center px-6 py-24 text-center">
          <span className="mb-8 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs font-medium tracking-wide text-white/80 backdrop-blur-xl">
            <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
            Self-hosted · No ElevenLabs · No Twilio
          </span>

          <h1 className="text-balance text-4xl font-semibold leading-[1.08] tracking-tight sm:text-6xl md:text-7xl">
            Own your{' '}
            <span className="bg-gradient-to-b from-white to-white/40 bg-clip-text text-transparent">
              voice AI
            </span>
          </h1>
          <p className="mt-4 text-balance text-lg font-light text-white/60 sm:text-xl">
            Your Whisper, your voice, your phone line.
          </p>

          <p className="mt-6 max-w-2xl text-balance text-sm leading-relaxed text-white/50 sm:text-base">
            A complete voice-agent stack that replaces ElevenLabs, Twilio and the Whisper API with
            services you run yourself. Every layer is swappable with one environment variable.
          </p>

          <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
            <Button href="/voice-client.html" external variant="primary">
              Test it here
              <ArrowRight aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
            </Button>
            <Button href="/architecture" variant="outline">
              View Architecture
            </Button>
            <Button href="/insights" variant="ghost">
              Insights
            </Button>
          </div>

          <dl className="mt-16 grid w-full max-w-2xl grid-cols-3 gap-px overflow-hidden rounded-2xl border border-white/10 bg-white/10 backdrop-blur-xl">
            {STATS.map((s) => (
              <div key={s.label} className="flex flex-col items-center bg-black/60 px-3 py-5">
                <dd className="text-2xl font-semibold tabular-nums tracking-tight sm:text-3xl">
                  {s.value}
                </dd>
                <dt className="mt-1 text-[11px] font-medium uppercase tracking-wider text-white/40 sm:text-xs">
                  {s.label}
                </dt>
              </div>
            ))}
          </dl>
        </div>
      </section>

      {/* ---------- Below the hero ---------- */}
      <div className="mx-auto max-w-6xl space-y-20 px-6 py-20 md:px-10">
        {/* Services status */}
        <section aria-labelledby="services-heading">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 id="services-heading" className="text-2xl font-semibold tracking-tight">
                Services
              </h2>
              <p className="mt-1 text-sm text-white/50">
                Live reachability of every microservice on this machine.
              </p>
            </div>
            <div className="flex items-center gap-3">
              {checkedAt && (
                <span className="text-xs tabular-nums text-white/40">
                  Checked {checkedAt.toLocaleTimeString()}
                </span>
              )}
              <button
                onClick={checkAll}
                className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-4 py-2 text-sm text-white backdrop-blur-xl transition-colors hover:border-white/30 hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
              >
                <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" strokeWidth={2} />
                Re-check
              </button>
            </div>
          </div>

          <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {SERVICES.map((s) => {
              const st = status[s.port] || 'checking';
              return (
                <li
                  key={s.port}
                  className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl transition-colors hover:border-white/20 hover:bg-white/[0.05]"
                >
                  <div className="flex items-start justify-between gap-3">
                    <h3 className="font-medium leading-snug">{s.name}</h3>
                    <span className="flex shrink-0 items-center gap-1.5 pt-0.5 text-xs">
                      <StatusDot status={st} />
                      <span
                        className={
                          st === 'up'
                            ? 'text-emerald-400'
                            : st === 'down'
                            ? 'text-red-400'
                            : 'text-white/40'
                        }
                      >
                        {st === 'up' ? 'running' : st === 'down' ? 'unreachable' : 'checking'}
                      </span>
                    </span>
                  </div>
                  <p className="mt-2 text-sm leading-relaxed text-white/50">{s.desc}</p>
                  <p className="mt-4 text-xs tabular-nums text-white/40">
                    localhost:<span className="text-white/80">{s.port}</span>
                  </p>
                </li>
              );
            })}
          </ul>
        </section>

        {/* Pipeline strip */}
        <section aria-labelledby="pipeline-heading">
          <h2 id="pipeline-heading" className="mb-6 text-2xl font-semibold tracking-tight">
            Pipeline
          </h2>
          <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl">
            <div className="overflow-x-auto pb-1">
              <ol className="flex min-w-max items-center gap-3">
                {PIPELINE.map((label, i) => (
                  <li key={i} className="flex items-center gap-3">
                    <div className="flex min-w-[104px] flex-col items-center rounded-xl border border-white/10 bg-black px-4 py-3 text-center">
                      <span className="text-sm font-medium">{label}</span>
                      <span className="mt-0.5 text-[11px] text-white/40">{PIPELINE_SUBS[i]}</span>
                    </div>
                    {i < PIPELINE.length - 1 && (
                      <ArrowRight
                        aria-hidden="true"
                        className="h-4 w-4 shrink-0 text-white/30"
                        strokeWidth={1.75}
                      />
                    )}
                  </li>
                ))}
              </ol>
            </div>
            <p className="mt-5 text-sm text-white/50">
              You speak, it&apos;s transcribed, the AI thinks, and the reply is spoken back sentence
              by sentence. Barge-in supported.
            </p>
          </div>
        </section>

        {/* Why self-hosted */}
        <section aria-labelledby="why-heading">
          <h2 id="why-heading" className="mb-6 text-2xl font-semibold tracking-tight">
            Why self-hosted
          </h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {WHY.map((c, i) => (
              <div
                key={c.title}
                className="rounded-2xl border border-white/10 bg-white/[0.03] p-7 backdrop-blur-xl transition-colors hover:border-white/20"
              >
                <span className="text-xs font-medium tabular-nums text-white/30">
                  0{i + 1}
                </span>
                <h3 className="mt-3 text-lg font-medium tracking-tight">{c.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-white/50">{c.desc}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
