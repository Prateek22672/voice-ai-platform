'use client';

// Where to reach a backend service from the browser.
// - Direct access (localhost or IP:3000)  -> call the service's own port, e.g. http://IP:8001
// - Behind the reverse proxy / Cloudflare Tunnel (a real domain on 80/443, no :3000)
//     -> call SAME ORIGIN; the tunnel routes the path to the right service.
export function apiBase(port) {
  if (typeof window === 'undefined') return `http://localhost:${port}`;
  const p = window.location.port;
  if (p === '' || p === '80' || p === '443') return window.location.origin; // proxied → same origin
  return `${window.location.protocol}//${window.location.hostname}:${port}`;
}

export function wsBase() {
  if (typeof window === 'undefined') return 'ws://localhost:8000';
  const p = window.location.port;
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  if (p === '' || p === '80' || p === '443') return `${proto}://${window.location.host}`;
  return `${proto}://${window.location.hostname}:8000`;
}
