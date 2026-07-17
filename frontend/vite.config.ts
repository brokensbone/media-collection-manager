/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev-only: `npm run dev` serves the SPA on :5173 and proxies the API's routes to a running
// backend (default the local-deploy container on :8000, override with API_ORIGIN) so the UI
// can be iterated with hot reload instead of rebuilding the deploy image. Ignored by `build`.
const API_ORIGIN = process.env.API_ORIGIN ?? 'http://localhost:8000'
const API_PREFIXES = [
  '/auth',
  '/art',
  '/albums',
  '/acquire',
  '/decide',
  '/releases',
  '/imports',
  '/dashboard',
  '/health',
  '/metrics',
]

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: Object.fromEntries(API_PREFIXES.map((p) => [p, API_ORIGIN])),
  },
  test: {
    environment: 'jsdom',
    globals: false,
  },
})
