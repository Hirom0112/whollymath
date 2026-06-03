/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// The local FastAPI turn-loop server (uvicorn app.api.app:app, CLAUDE.md §10).
const API_TARGET = 'http://localhost:8000';

// Vite + React for the adaptive UI; Vitest configured for jsdom + RTL (TECH_STACK §2, CLAUDE.md §6).
// In dev, the turn-loop API paths are proxied to the FastAPI server so the browser
// sees a single origin (no CORS to manage); the client uses relative paths (src/api).
export default defineConfig({
  plugins: [react()],
  server: {
    // Bind to the LAN (0.0.0.0) so a phone on the same wifi can open the homework scan page by
    // QR (PROJECT.md §3.4 two-star model). Harmless for desktop dev. In production the phone hits
    // the public HTTPS URL directly, so none of this matters there.
    host: true,
    proxy: {
      '/health': API_TARGET,
      '/routing-choices': API_TARGET,
      '/session': API_TARGET,
      '/turn': API_TARGET,
      '/eval': API_TARGET,
      '/course': API_TARGET,
      // '/units' listed before '/unit' so the list endpoint isn't shadowed by the detail prefix.
      '/units': API_TARGET,
      '/unit': API_TARGET,
      '/me': API_TARGET,
      '/events': API_TARGET,
      // Cached mascot-voice mp3s, served as static files off the backend (Slice AR.3). A
      // SpokenAudio.audio_url ('/tts/audio/<sha>.mp3') resolves through this single-origin proxy in
      // dev; in production CloudFront serves the same path. Off the turn loop (a static GET).
      '/tts': API_TARGET,
      '/hw': API_TARGET,
      // Teacher dashboard: roster + per-student drill-in + assign-next-unit (TCH.B8).
      '/teacher': API_TARGET,
      // Parent/child auth (Slice auth/parent-child). The trailing slash proxies only the API
      // SUB-paths ('/parent/me', '/parent/signup', '/parent/children', ...) to FastAPI, while the
      // bare '/parent' SPA route is left for Vite to serve index.html (so the parent page still
      // deep-links in dev). '/child' has no SPA route, so child login proxies wholesale.
      '/parent/': API_TARGET,
      '/child': API_TARGET,
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
});
