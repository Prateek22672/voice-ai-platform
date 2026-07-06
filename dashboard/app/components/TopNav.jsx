'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { AudioLines, ArrowRight } from 'lucide-react';

const LINKS = [
  { href: '/', label: 'Overview' },
  { href: '/architecture', label: 'Architecture' },
  { href: '/voices', label: 'Voices' },
  { href: '/insights', label: 'Insights' },
  { href: '/admin', label: 'Admin' },
];

function Pills({ pathname, className = '' }) {
  return (
    <div
      className={`flex items-center gap-1 rounded-full border border-white/10 bg-white/5 p-1 backdrop-blur-xl ${className}`}
    >
      {LINKS.map((l) => {
        const active = pathname === l.href;
        return (
          <Link
            key={l.href}
            href={l.href}
            aria-current={active ? 'page' : undefined}
            className={`whitespace-nowrap rounded-full px-4 py-1.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 ${
              active
                ? 'bg-white/10 font-medium text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]'
                : 'text-white/60 hover:text-white'
            }`}
          >
            {l.label}
          </Link>
        );
      })}
    </div>
  );
}

export default function TopNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 border-b border-white/5 bg-black/50 backdrop-blur-xl">
      <nav
        aria-label="Main navigation"
        className="relative mx-auto flex h-16 max-w-6xl items-center justify-between px-4 md:px-6"
      >
        <Link
          href="/"
          className="flex items-center gap-2.5 text-[15px] font-semibold tracking-tight text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 rounded-md"
        >
          <span className="flex h-7 w-7 items-center justify-center rounded-full border border-white/15 bg-white/5">
            <AudioLines aria-hidden="true" className="h-3.5 w-3.5 text-white" strokeWidth={1.75} />
          </span>
          Voice AI Platform
        </Link>

        {/* Center pill group — desktop */}
        <div className="absolute left-1/2 top-1/2 hidden -translate-x-1/2 -translate-y-1/2 md:block">
          <Pills pathname={pathname} />
        </div>

        <div className="flex items-center gap-2">
          <a
            href="/voice-enroll.html"
            className="hidden rounded-full px-4 py-2 text-sm text-white/60 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 sm:block"
          >
            Train a Voice
          </a>
          <a
            href="/voice-client.html"
            className="group relative inline-flex items-center gap-1.5 overflow-hidden rounded-full bg-white px-4 py-2 text-sm font-medium text-black transition-all duration-300 hover:shadow-[0_0_28px_rgba(255,255,255,0.25)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black"
          >
            <span
              aria-hidden="true"
              className="pointer-events-none absolute top-0 left-[-60%] h-full w-1/3 -skew-x-[20deg] bg-gradient-to-r from-transparent via-black/10 to-transparent transition-[left] duration-700 ease-out group-hover:left-[130%] motion-reduce:hidden"
            />
            <span className="relative">Talk to Agent</span>
            <ArrowRight
              aria-hidden="true"
              className="relative h-3.5 w-3.5 transition-transform duration-300 group-hover:translate-x-0.5"
              strokeWidth={2}
            />
          </a>
        </div>
      </nav>

      {/* Mobile: pills collapse into a horizontally scrollable row */}
      <div className="overflow-x-auto px-4 pb-3 md:hidden [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
        <Pills pathname={pathname} className="w-max" />
      </div>
    </header>
  );
}
