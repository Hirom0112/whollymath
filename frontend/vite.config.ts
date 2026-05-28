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
    proxy: {
      '/health': API_TARGET,
      '/routing-choices': API_TARGET,
      '/session': API_TARGET,
      '/turn': API_TARGET,
      '/eval': API_TARGET,
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
  },
});
