/// <reference types="vitest/config" />
import type { IncomingMessage } from 'node:http';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The local FastAPI turn-loop server (uvicorn app.api.app:app, CLAUDE.md §10).
const API_TARGET = 'http://localhost:8000';

// The turn-loop API paths proxied to FastAPI in dev so the browser sees a single origin (no CORS;
// the client uses relative paths in src/api). '/units' is listed before '/unit' so the list
// endpoint isn't shadowed by the detail prefix.
const PROXIED_PATHS = [
  '/health',
  '/routing-choices',
  '/session',
  '/turn',
  '/eval',
  '/course',
  '/units',
  '/unit',
  '/me',
  '/events',
  // Cached mascot-voice mp3s, served as static files off the backend (Slice AR.3). A
  // SpokenAudio.audio_url ('/tts/audio/<sha>.mp3') resolves through this single-origin proxy in
  // dev; in production CloudFront serves the same path. Off the turn loop (a static GET).
  '/tts',
  '/hw',
  // Teacher dashboard: roster + per-student drill-in + assign-next-unit (TCH.B8).
  '/teacher',
  // Parent/child auth (Slice auth/parent-child): '/parent/me', '/parent/signup',
  // '/parent/children', ... and the '/child' login endpoints. NOTE the TRAILING SLASH on
  // '/parent/': it must NOT be a bare '/parent', or the prefix would also swallow the static
  // asset '/parent-cosmos.jpg' (the parent sign-in starfield) — proxying it to FastAPI, where
  // it 404s, leaving the left panel a flat navy fallback. With the slash, only the API
  // sub-paths proxy; the image (and the bare '/parent' SPA route) are served by Vite.
  '/parent/',
  '/child',
];

// SPA fallback for the paths that collide with a client-side react-router route (/units, /unit,
// /teacher, /eval, /hw, /parent all exist as both an API prefix AND an App.tsx <Route>). A real
// browser navigation to one of those — a deep-link, a refresh, a typed URL — would otherwise be
// proxied to FastAPI and 404/return JSON instead of booting the SPA. We distinguish by the Accept
// header: a top-level document request sends `Accept: text/html`, while the app's own fetch() calls
// (src/api getJson/postJson) send `Accept: */*`. So API calls proxy as before, but an HTML GET
// navigation falls through to index.html and lets react-router render the route. (This supersedes
// the earlier per-path trailing-slash workaround — it also covers '/units' and '/unit/:slug',
// whose API and SPA paths overlap exactly and so cannot be split by a trailing slash.)
const spaFallback = (req: IncomingMessage): string | undefined =>
  req.method === 'GET' && req.headers.accept?.includes('text/html') ? '/index.html' : undefined;

// Vite + React for the adaptive UI; Vitest configured for jsdom + RTL (TECH_STACK §2, CLAUDE.md §6).
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind to the LAN (0.0.0.0) so a phone on the same wifi can open the homework scan page by
    // QR (PROJECT.md §3.4 two-star model). Harmless for desktop dev. In production the phone hits
    // the public HTTPS URL directly, so none of this matters there.
    host: true,
    proxy: Object.fromEntries(
      PROXIED_PATHS.map((path) => [path, { target: API_TARGET, bypass: spaFallback }]),
    ),
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
});
