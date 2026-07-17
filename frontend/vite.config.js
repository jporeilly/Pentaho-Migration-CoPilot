import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev server proxies API calls to the FastAPI backend (scripts/dev.ps1 run).
const backend = 'http://127.0.0.1:8321'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/convert': backend,
      '/parse': backend,
      '/sample': backend,
      '/health': backend,
      '/changelog': backend,
      '/settings': backend,
      '/translate': backend,
      '/translate/start': backend,
      '/translate/status': backend,
      '/sandbox': backend,
      '/diff': backend,
      '/project': backend,
      '/best-practices': backend,
      '/brief': backend,
    },
  },
  build: { outDir: 'dist' },
})
