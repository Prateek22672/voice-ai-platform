'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Play, Square, Loader2, Star, Check, Volume2 } from 'lucide-react';
import { apiBase } from '../lib/api';

const TTS = apiBase(8002);

const SAMPLES = [
  "Hi there — thanks for joining today. Let's start with a quick question about your experience.",
  "Your appointment is confirmed for tomorrow at 3 PM. Is there anything else I can help you with?",
  "Absolutely, I can walk you through that. It only takes a couple of minutes to set up.",
];

const GRADE_COLOR = (g) =>
  g.startsWith('A') ? 'text-emerald-300 border-emerald-400/30 bg-emerald-400/10'
  : g.startsWith('B') ? 'text-sky-300 border-sky-400/30 bg-sky-400/10'
  : 'text-white/60 border-white/15 bg-white/5';

function Segmented({ options, value, onChange }) {
  return (
    <div className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/5 p-1">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onChange(o)}
          className={`rounded-full px-3.5 py-1.5 text-sm transition-colors ${
            value === o ? 'bg-white/10 font-medium text-white' : 'text-white/55 hover:text-white'
          }`}
        >
          {o}
        </button>
      ))}
    </div>
  );
}

export default function VoiceStudio() {
  const [voices, setVoices] = useState([]);
  const [activeVoice, setActiveVoice] = useState(null);
  const [loadErr, setLoadErr] = useState('');
  const [text, setText] = useState(SAMPLES[0]);

  const [accent, setAccent] = useState('All');
  const [gender, setGender] = useState('All');

  const [playing, setPlaying] = useState(null); // voice id currently playing
  const [loadingId, setLoadingId] = useState(null); // voice id synthesizing
  const [settingId, setSettingId] = useState(null); // voice id being set live
  const audioRef = useRef(null);

  const load = useCallback(() => {
    fetch(`${TTS}/v1/tts/catalog`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((d) => {
        setVoices(d.voices || []);
        setActiveVoice(d.default || null);
        setLoadErr('');
      })
      .catch(() => setLoadErr('Could not reach the Text-to-Speech service.'));
  }, []);

  useEffect(() => {
    load();
    return () => {
      if (audioRef.current) audioRef.current.pause();
    };
  }, [load]);

  function stopAudio() {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    setPlaying(null);
  }

  async function preview(voice) {
    stopAudio();
    if (loadingId) return;
    setLoadingId(voice.id);
    try {
      const r = await fetch(`${TTS}/v1/tts/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice: voice.id, text }),
      });
      if (!r.ok) throw new Error('preview failed');
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => { setPlaying(null); URL.revokeObjectURL(url); };
      audio.onpause = () => setPlaying((p) => (p === voice.id ? null : p));
      setPlaying(voice.id);
      await audio.play();
    } catch {
      setLoadErr('Preview failed — is the TTS service running?');
    } finally {
      setLoadingId(null);
    }
  }

  async function setLive(voice) {
    let pw = typeof window !== 'undefined' ? localStorage.getItem('voiceadminpw') || '' : '';
    if (!pw) {
      pw = window.prompt('Admin password to set the live agent voice:') || '';
      if (!pw) return;
    }
    setSettingId(voice.id);
    try {
      const r = await fetch(`${TTS}/v1/tts/default_voice`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-Admin-Password': pw },
        body: JSON.stringify({ voice: voice.id }),
      });
      if (r.status === 401) {
        localStorage.removeItem('voiceadminpw');
        setLoadErr('Wrong admin password.');
        return;
      }
      if (!r.ok) throw new Error();
      localStorage.setItem('voiceadminpw', pw);
      const d = await r.json();
      setActiveVoice(d.voice);
      setLoadErr('');
    } catch {
      setLoadErr('Could not set the live voice.');
    } finally {
      setSettingId(null);
    }
  }

  const filtered = voices.filter(
    (v) => (accent === 'All' || v.accent === accent) && (gender === 'All' || v.gender === gender)
  );
  const activeMeta = voices.find((v) => v.id === activeVoice);

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      {/* Header */}
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">Voice Studio</h1>
        <p className="max-w-2xl text-sm leading-relaxed text-white/55">
          Every natural voice the platform can speak with. Type a line, preview any voice, and set
          the one your live agent uses — no redeploy needed.
        </p>
        {activeMeta && (
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-400/25 bg-emerald-400/10 px-4 py-1.5 text-sm text-emerald-200">
            <Volume2 aria-hidden="true" className="h-4 w-4" />
            Live agent voice: <b className="font-semibold">{activeMeta.name}</b>
            <span className="text-emerald-300/60">
              · {activeMeta.accent} {activeMeta.gender}
            </span>
          </div>
        )}
      </header>

      {loadErr && (
        <div className="rounded-xl border border-red-400/30 bg-red-400/10 px-4 py-3 text-sm text-red-200">
          {loadErr}
        </div>
      )}

      {/* Sample text + filters */}
      <section className="space-y-4 rounded-2xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur-xl">
        <label className="block text-[11px] uppercase tracking-widest text-white/40">
          Sample line to speak
        </label>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          maxLength={300}
          className="w-full resize-none rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-white outline-none focus:border-white/30"
        />
        <div className="flex flex-wrap items-center gap-2">
          {SAMPLES.map((s, i) => (
            <button
              key={i}
              onClick={() => setText(s)}
              className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/55 transition-colors hover:text-white"
            >
              Sample {i + 1}
            </button>
          ))}
          <span className="ml-auto flex flex-wrap items-center gap-2">
            <Segmented options={['All', 'American', 'British']} value={accent} onChange={setAccent} />
            <Segmented options={['All', 'Female', 'Male']} value={gender} onChange={setGender} />
          </span>
        </div>
      </section>

      {/* Voice grid */}
      <section>
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((v) => {
            const isActive = v.id === activeVoice;
            const isPlaying = playing === v.id;
            const isLoading = loadingId === v.id;
            return (
              <li
                key={v.id}
                className={`flex flex-col rounded-2xl border p-5 backdrop-blur-xl transition-colors ${
                  isActive
                    ? 'border-emerald-400/40 bg-emerald-400/[0.06]'
                    : 'border-white/10 bg-white/[0.03] hover:border-white/20'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <h3 className="text-lg font-medium tracking-tight">{v.name}</h3>
                      {v.featured && (
                        <Star aria-hidden="true" className="h-3.5 w-3.5 fill-amber-300 text-amber-300" />
                      )}
                    </div>
                    <p className="mt-0.5 text-xs text-white/45">
                      {v.accent} · {v.gender}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full border px-2 py-0.5 text-[11px] font-medium tabular-nums ${GRADE_COLOR(
                      v.grade
                    )}`}
                    title="Kokoro voice quality grade"
                  >
                    {v.grade}
                  </span>
                </div>

                <p className="mt-3 min-h-[2.5rem] text-sm leading-relaxed text-white/55">{v.tag}</p>

                <div className="mt-4 flex items-center gap-2">
                  <button
                    onClick={() => (isPlaying ? stopAudio() : preview(v))}
                    disabled={isLoading}
                    className="inline-flex items-center gap-1.5 rounded-full bg-white px-4 py-1.5 text-sm font-medium text-black transition-colors hover:bg-white/90 disabled:opacity-60"
                  >
                    {isLoading ? (
                      <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />
                    ) : isPlaying ? (
                      <Square aria-hidden="true" className="h-3.5 w-3.5 fill-black" />
                    ) : (
                      <Play aria-hidden="true" className="h-3.5 w-3.5 fill-black" />
                    )}
                    {isLoading ? 'Loading' : isPlaying ? 'Stop' : 'Preview'}
                  </button>

                  {isActive ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-400/30 px-3 py-1.5 text-sm text-emerald-300">
                      <Check aria-hidden="true" className="h-3.5 w-3.5" /> Live
                    </span>
                  ) : (
                    <button
                      onClick={() => setLive(v)}
                      disabled={settingId === v.id}
                      className="inline-flex items-center gap-1.5 rounded-full border border-white/15 px-3 py-1.5 text-sm text-white/70 transition-colors hover:border-white/35 hover:text-white disabled:opacity-60"
                    >
                      {settingId === v.id ? (
                        <Loader2 aria-hidden="true" className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Star aria-hidden="true" className="h-3.5 w-3.5" />
                      )}
                      Use for agent
                    </button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
        {filtered.length === 0 && !loadErr && (
          <p className="py-16 text-center text-sm text-white/40">No voices match this filter.</p>
        )}
      </section>
    </div>
  );
}
