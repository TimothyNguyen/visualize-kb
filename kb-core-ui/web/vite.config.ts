/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: process.env.VITE_HOST ?? '127.0.0.1',
    port: Number(process.env.VITE_PORT ?? 5173),
    strictPort: true,
    proxy: {
      '/api/copilotkit': process.env.VITE_COPILOTKIT_PROXY ?? 'http://127.0.0.1:3001',
      '/api/rag': process.env.VITE_KB_CORE_UI_PROXY ?? 'http://127.0.0.1:8080',
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // 'forks' (default) hangs waiting on worker IPC in some sandboxed shells.
    pool: 'threads',
  },
})
