'use client';

import Link from 'next/link';

const VARIANTS = {
  primary:
    'group relative overflow-hidden bg-white text-black shadow-[0_0_24px_rgba(255,255,255,0.15)] hover:shadow-[0_0_40px_rgba(255,255,255,0.25)]',
  outline:
    'border border-white/15 bg-white/5 text-white backdrop-blur-xl hover:border-white/30 hover:bg-white/10',
  ghost: 'text-white/60 hover:text-white',
};

/**
 * Pill button/link. `variant`: primary (solid white + shimmer sweep) | outline (glass) | ghost.
 * External links (e.g. static .html tools) render a plain <a>; internal routes use next/link.
 */
export default function Button({ href, external = false, variant = 'primary', className = '', children }) {
  const cls = [
    'inline-flex items-center justify-center gap-2 rounded-full px-6 py-3 text-sm font-medium',
    'transition-all duration-300',
    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black',
    VARIANTS[variant] || VARIANTS.primary,
    className,
  ].join(' ');

  const inner = (
    <>
      {variant === 'primary' && (
        <span aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden rounded-full">
          <span className="absolute top-0 left-[-60%] h-full w-1/3 -skew-x-[20deg] bg-gradient-to-r from-transparent via-black/10 to-transparent transition-[left] duration-700 ease-out group-hover:left-[130%] motion-reduce:hidden" />
        </span>
      )}
      <span className="relative z-10 inline-flex items-center gap-2">{children}</span>
    </>
  );

  if (external) {
    return (
      <a href={href} className={cls}>
        {inner}
      </a>
    );
  }
  return (
    <Link href={href} className={cls}>
      {inner}
    </Link>
  );
}
