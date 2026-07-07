'use client';

import { useCallback, useEffect, useState } from 'react';
import { Phone, PhoneOff, Loader2, ChevronDown, ChevronUp, RefreshCw } from 'lucide-react';
import { apiBase } from '../lib/api';

const GW = apiBase(8090); // api-gateway → telephony-service
const TTS = apiBase(8002); // tts-service (voice catalog)
const AUTH = { Authorization: 'Bearer dev-test-key', 'Content-Type': 'application/json' };

// Shared professional conduct baked into every scenario: confident, courteous, handles
// questions instead of dodging them, and never bluffs.
const CONDUCT =
  ' Speaking style: confident, courteous and professional, like a top-tier customer-care executive. ' +
  'Open every reply with a very short sentence. Ask exactly ONE question at a time and wait. ' +
  'If the person asks a question, answer it helpfully FIRST, then continue. If you do not know a ' +
  'specific detail (exact price, address, legal terms), say a specialist from the team will follow up ' +
  'with the exact details — never invent facts. If they are busy, offer to call back and end politely. ' +
  'If they are not interested, thank them warmly and end the call. Keep every reply under two sentences.';

const SCENARIOS = [
  {
    id: 'interview',
    title: 'Interview screening',
    desc: 'Professionally screens a candidate: experience, skills, availability.',
    prompt:
      'You are a professional AI interview assistant calling on behalf of the hiring team. ' +
      'You MUST say you are an AI assistant at the start. Screen the candidate about their software ' +
      'experience, key skills, current role, notice period and salary expectations. After 4-5 ' +
      'questions, summarize what you heard in one sentence, thank them, and say the team will follow up.' +
      CONDUCT,
    greeting:
      'Greet the person by name if known, say you are an AI assistant calling on behalf of the hiring ' +
      'team about their job application, and ask if now is a good time for a quick two-minute screening.',
  },
  {
    id: 'realestate',
    title: 'Real-estate assistant',
    desc: 'Presents properties, answers queries, collects budget, location & timeline.',
    prompt:
      'You are a professional AI real-estate assistant calling from the sales team. You MUST say you ' +
      'are an AI assistant at the start. Goal: understand what the person is looking for and qualify ' +
      'their interest: buying or investing, preferred location, budget range, timeline, and financing ' +
      'needs. Answer their questions about the process confidently; for exact prices or site visits, ' +
      'offer to have a property specialist call back and confirm their preferred time.' +
      CONDUCT,
    greeting:
      'Greet the person by name if known, say you are an AI assistant calling from the real-estate ' +
      'team, and ask if they have a minute to talk about finding the right property for them.',
  },
  {
    id: 'support',
    title: 'Customer follow-up',
    desc: 'Checks in on a customer: satisfaction, issues, and next steps.',
    prompt:
      'You are a professional AI customer-care assistant making a courtesy follow-up call. You MUST ' +
      'say you are an AI assistant at the start. Goal: check the customer is satisfied, note any ' +
      'issues or questions they have, and reassure them the team will resolve anything outstanding. ' +
      'Collect a clear description of any problem they mention.' + CONDUCT,
    greeting:
      'Greet the person by name if known, say you are an AI assistant calling to follow up on their ' +
      'recent experience, and ask if they have a quick minute.',
  },
  {
    id: 'custom',
    title: 'Custom topic',
    desc: 'You write exactly what the agent should talk about.',
    prompt: '',
    greeting: '',
  },
];

function StatusPill({ status }) {
  const map = {
    dialing: 'bg-[#e3b341]/15 text-[#e3b341]',
    ringing: 'bg-[#e3b341]/15 text-[#e3b341]',
    answered: 'bg-[#3fb950]/15 text-[#3fb950]',
    ended: 'bg-white/10 text-white/55',
  };
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${map[status] || 'bg-white/10 text-white/55'}`}>
      {status}
    </span>
  );
}

export default function CallsPage() {
  const [to, setTo] = useState('');
  const [scenario, setScenario] = useState('interview');
  const [customTopic, setCustomTopic] = useState('');
  const [extraContext, setExtraContext] = useState('');
  const [maxMin, setMaxMin] = useState(5); // auto-hangup limit (cost control)
  const [voice, setVoice] = useState(''); // '' = platform default (Voice Studio live voice)
  const [voices, setVoices] = useState([]);
  const [placing, setPlacing] = useState(false);
  const [msg, setMsg] = useState(null); // {ok, text}
  const [calls, setCalls] = useState([]);
  const [open, setOpen] = useState(null); // call_id expanded
  const [transcripts, setTranscripts] = useState({}); // call_id -> transcript
  const [nowTs, setNowTs] = useState(Date.now() / 1000); // 1s ticker for the live-call timer

  // one call at a time in R&D — the first dialing/answered call is "the live call"
  const activeCall = calls.find((c) => c.status === 'dialing' || c.status === 'answered') || null;

  useEffect(() => {
    if (!activeCall) return;
    const id = setInterval(() => setNowTs(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, [activeCall]);

  const loadCalls = useCallback(async () => {
    try {
      const r = await fetch(`${GW}/v1/calls`, { headers: AUTH, cache: 'no-store' });
      if (!r.ok) return;
      const d = await r.json();
      setCalls(Array.isArray(d.calls) ? d.calls : []);
    } catch { /* telephony profile may be off */ }
  }, []);

  const loadTranscript = useCallback(async (id) => {
    try {
      const r = await fetch(`${GW}/v1/calls/${id}/transcript`, { headers: AUTH, cache: 'no-store' });
      if (!r.ok) return;
      const d = await r.json();
      setTranscripts((p) => ({ ...p, [id]: d.transcript || [] }));
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    loadCalls();
    // natural-voice catalog for the per-call voice picker
    fetch(`${TTS}/v1/tts/catalog`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => setVoices(d.voices || []))
      .catch(() => {});
    const id = setInterval(() => {
      loadCalls();
      if (open) loadTranscript(open); // live transcript while a call runs
    }, 4000);
    return () => clearInterval(id);
  }, [loadCalls, loadTranscript, open]);

  function buildPrompts() {
    const s = SCENARIOS.find((x) => x.id === scenario);
    if (scenario === 'custom') {
      const topic = customTopic.trim() || 'a friendly check-in call';
      return {
        prompt:
          `You are a professional AI assistant on a phone call. You MUST say you are an AI assistant ` +
          `at the start. The purpose of this call: ${topic}.` + CONDUCT +
          (extraContext.trim() ? ` Extra context: ${extraContext.trim()}` : ''),
        greeting:
          `Greet the person, say you are an AI assistant, and briefly state you are calling about: ${topic}.`,
      };
    }
    return {
      prompt: s.prompt + (extraContext.trim() ? ` Extra context for this call: ${extraContext.trim()}` : ''),
      greeting: s.greeting,
    };
  }

  async function placeCall() {
    setMsg(null);
    // normalize: people paste "+91 88803 33777" / "+1 (469) 468-1474" — strip separators
    const num = to.trim().replace(/[\s\-().]/g, '');
    if (!/^\+\d{8,15}$/.test(num)) {
      setMsg({ ok: false, text: 'Enter the number with country code, e.g. +91 88803 33777 or +1 469 468 1474 (spaces are fine).' });
      return;
    }
    setPlacing(true);
    try {
      const { prompt, greeting } = buildPrompts();
      const r = await fetch(`${GW}/v1/calls`, {
        method: 'POST',
        headers: AUTH,
        body: JSON.stringify({ to: num, agent_prompt: prompt, greeting_prompt: greeting, scenario,
                               voice: voice || undefined, max_duration_s: maxMin * 60 }),
      });
      const d = await r.json();
      if (r.ok) {
        setMsg({ ok: true, text: `Calling ${num}… the agent will greet when they answer.` });
        setOpen(d.call_id);
        loadCalls();
      } else {
        setMsg({ ok: false, text: d.detail || 'Call failed — is the telephony profile running?' });
      }
    } catch {
      setMsg({ ok: false, text: 'Telephony service unreachable. Start it with: docker compose --profile telephony up -d' });
    } finally {
      setPlacing(false);
    }
  }

  async function hangup(id) {
    try {
      await fetch(`${GW}/v1/calls/${id}/hangup`, { method: 'POST', headers: AUTH });
      loadCalls();
    } catch { /* ignore */ }
  }

  function toggle(id) {
    const next = open === id ? null : id;
    setOpen(next);
    if (next && !transcripts[next]) loadTranscript(next);
  }

  const fmtTime = (ts) => (ts ? new Date(ts * 1000).toLocaleString() : '—');
  const fmtDur = (s) => (s == null ? '—' : `${Math.floor(s / 60)}m ${s % 60}s`);

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <header>
        <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-white/40">Telephony</p>
        <h1 className="text-balance text-3xl font-bold tracking-tight">Phone Calls</h1>
        <p className="mt-2 max-w-2xl text-sm text-white/60">
          The agent dials a real number over the Telnyx trunk, speaks with our Kokoro voice,
          transcribes with Whisper, and saves the full conversation below.
        </p>
      </header>

      {/* LIVE CALL banner — always visible while a call is running */}
      {activeCall ? (
        <div
          className={`flex flex-wrap items-center justify-between gap-3 rounded-2xl border px-5 py-4 backdrop-blur-xl ${
            activeCall.status === 'answered'
              ? 'border-[#3fb950]/50 bg-[#3fb950]/[0.08]'
              : 'border-[#e3b341]/50 bg-[#e3b341]/[0.08]'
          }`}
        >
          <span className="flex items-center gap-3">
            <span className="relative flex h-3 w-3">
              <span
                className={`absolute inline-flex h-full w-full animate-ping rounded-full ${
                  activeCall.status === 'answered' ? 'bg-[#3fb950]/60' : 'bg-[#e3b341]/60'
                }`}
              />
              <span
                className={`relative inline-flex h-3 w-3 rounded-full ${
                  activeCall.status === 'answered' ? 'bg-[#3fb950]' : 'bg-[#e3b341]'
                }`}
              />
            </span>
            <span className="text-sm font-semibold">
              {activeCall.status === 'answered' ? 'LIVE CALL' : 'DIALING…'}
            </span>
            <span className="font-mono text-sm text-white/80">{activeCall.to}</span>
            <span className="tabular-nums text-sm text-white/60">
              {(() => {
                const s = Math.max(0, Math.floor(nowTs - (activeCall.started || nowTs)));
                return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
              })()}
            </span>
          </span>
          <button
            onClick={() => hangup(activeCall.call_id)}
            className="inline-flex items-center gap-2 rounded-full bg-[#e5484d] px-5 py-2 text-sm font-semibold text-white transition-colors hover:bg-[#e5484d]/85"
          >
            <PhoneOff aria-hidden="true" className="h-4 w-4" /> End call
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2.5 rounded-2xl border border-white/10 bg-white/[0.03] px-5 py-3 backdrop-blur-xl">
          <span className="h-2.5 w-2.5 rounded-full bg-white/25" />
          <span className="text-sm text-white/55">No call in progress</span>
        </div>
      )}

      {/* place a call */}
      <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl">
        <h2 className="mb-4 text-xs font-semibold uppercase tracking-[0.12em] text-white/50">Make a call</h2>

        <label className="mb-1 block text-xs uppercase tracking-wide text-white/50">Phone number (E.164)</label>
        <input
          value={to}
          onChange={(e) => setTo(e.target.value)}
          placeholder="+919876543210"
          className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 font-mono text-sm text-white placeholder-white/30 outline-none focus-visible:ring-2 focus-visible:ring-white/30"
        />

        <p className="mb-2 mt-5 text-xs uppercase tracking-wide text-white/50">What should the agent talk about?</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {SCENARIOS.map((s) => (
            <button
              key={s.id}
              type="button"
              aria-pressed={scenario === s.id}
              onClick={() => setScenario(s.id)}
              className={`rounded-xl border p-4 text-left transition-colors ${
                scenario === s.id
                  ? 'border-white/40 bg-white/[0.06] ring-1 ring-white/20'
                  : 'border-white/10 hover:border-white/30'
              }`}
            >
              <p className="text-sm font-semibold">{s.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-white/50">{s.desc}</p>
            </button>
          ))}
        </div>

        {scenario === 'custom' && (
          <>
            <label className="mb-1 mt-4 block text-xs uppercase tracking-wide text-white/50">
              Custom topic — what is this call about?
            </label>
            <textarea
              value={customTopic}
              onChange={(e) => setCustomTopic(e.target.value)}
              rows={2}
              placeholder="e.g. following up on their demo request for our voice AI product"
              className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white placeholder-white/30 outline-none focus-visible:ring-2 focus-visible:ring-white/30"
            />
          </>
        )}

        <label className="mb-1 mt-4 block text-xs uppercase tracking-wide text-white/50">
          Agent voice
        </label>
        <select
          value={voice}
          onChange={(e) => setVoice(e.target.value)}
          className="w-full rounded-xl border border-white/10 bg-black px-4 py-3 text-sm text-white outline-none focus-visible:ring-2 focus-visible:ring-white/30"
        >
          <option value="">Platform default (live Voice Studio voice)</option>
          {voices.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name} — {v.accent} {v.gender}{v.featured ? ' ★' : ''} ({v.tag})
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-white/40">
          Preview any voice on the <a href="/voices" className="underline decoration-white/30 hover:decoration-white">Voices</a> page before choosing.
        </p>

        <label className="mb-1 mt-4 block text-xs uppercase tracking-wide text-white/50">
          Extra context (optional — name, company, details the agent should know)
        </label>
        <input
          value={extraContext}
          onChange={(e) => setExtraContext(e.target.value)}
          placeholder="e.g. the person's name is Ravi; role is Senior React Developer"
          className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white placeholder-white/30 outline-none focus-visible:ring-2 focus-visible:ring-white/30"
        />

        <p className="mb-2 mt-5 text-xs uppercase tracking-wide text-white/50">
          Max call duration (auto hang-up — cost control)
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {[2, 5, 10].map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={maxMin === m}
              onClick={() => setMaxMin(m)}
              className={`rounded-full border px-4 py-1.5 text-sm transition-colors ${
                maxMin === m
                  ? 'border-white/40 bg-white/10 font-semibold text-white'
                  : 'border-white/10 text-white/55 hover:border-white/30 hover:text-white'
              }`}
            >
              {m} min
            </button>
          ))}
          <span className="text-xs text-white/40">
            call ends automatically at {maxMin} min — raise the limit later when we go to production
          </span>
        </div>

        <div className="mt-5 flex items-center gap-3">
          <button
            onClick={placeCall}
            disabled={placing}
            className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-2.5 text-sm font-semibold text-black transition-colors hover:bg-white/90 disabled:opacity-50"
          >
            {placing ? <Loader2 aria-hidden="true" className="h-4 w-4 animate-spin" /> : <Phone aria-hidden="true" className="h-4 w-4" />}
            {placing ? 'Dialing…' : 'Call now'}
          </button>
          {msg && (
            <p className={`text-sm ${msg.ok ? 'text-[#3fb950]' : 'text-[#e5484d]'}`}>{msg.text}</p>
          )}
        </div>
        <p className="mt-3 text-xs text-white/40">
          The agent introduces itself as an AI at the start of every call (required for compliance).
          Calls are billed by Telnyx per minute from your balance.
        </p>
      </section>

      {/* call history */}
      <section className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-white/50">
            Calls & transcripts
          </h2>
          <button
            onClick={loadCalls}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-3.5 py-1.5 text-xs text-white/70 transition-colors hover:border-white/30 hover:text-white"
          >
            <RefreshCw aria-hidden="true" className="h-3 w-3" /> Refresh
          </button>
        </div>

        {calls.length === 0 ? (
          <p className="py-8 text-center text-sm text-white/40">
            No calls yet — place your first call above.
          </p>
        ) : (
          <ul className="divide-y divide-white/5">
            {calls.map((c) => (
              <li key={c.call_id}>
                <button
                  onClick={() => toggle(c.call_id)}
                  className="flex w-full flex-wrap items-center justify-between gap-3 py-3 text-left"
                >
                  <span className="flex items-center gap-3">
                    <StatusPill status={c.status} />
                    <span className="font-mono text-sm text-white">{c.to}</span>
                    <span className="text-xs text-white/40">{c.scenario || '—'}</span>
                  </span>
                  <span className="flex items-center gap-3 text-xs tabular-nums text-white/55">
                    {fmtTime(c.started)} · {fmtDur(c.duration_s)} · {c.turns} lines
                    {open === c.call_id ? (
                      <ChevronUp aria-hidden="true" className="h-4 w-4" />
                    ) : (
                      <ChevronDown aria-hidden="true" className="h-4 w-4" />
                    )}
                  </span>
                </button>

                {open === c.call_id && (
                  <div className="mb-3 rounded-xl border border-white/10 bg-black/40 p-4">
                    {(c.status === 'dialing' || c.status === 'answered') && (
                      <button
                        onClick={() => hangup(c.call_id)}
                        className="mb-3 inline-flex items-center gap-1.5 rounded-full border border-[#e5484d]/40 px-3.5 py-1.5 text-xs font-semibold text-[#e5484d] transition-colors hover:bg-[#e5484d]/10"
                      >
                        <PhoneOff aria-hidden="true" className="h-3 w-3" /> Hang up
                      </button>
                    )}
                    {(transcripts[c.call_id] || []).length === 0 ? (
                      <p className="text-sm text-white/40">
                        {c.status === 'ended' ? 'No speech was captured on this call.' : 'Transcript appears here live as they talk…'}
                      </p>
                    ) : (
                      <div className="max-h-80 space-y-2 overflow-y-auto text-sm leading-relaxed">
                        {(transcripts[c.call_id] || []).map((line, i) => (
                          <p key={i} className={line.role === 'agent' ? 'text-[#dfe7ff]' : 'text-[#8fe3a8]'}>
                            <span className="mr-2 text-[10px] uppercase tracking-wide text-white/35">
                              {line.role === 'agent' ? 'Agent' : 'Caller'} · {line.t}s
                            </span>
                            {line.text}
                          </p>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
