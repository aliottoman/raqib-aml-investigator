import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev: proxy API + WS to FastAPI (port 8117) so everything runs on one origin.
// Prod: the backend serves web/dist directly — no proxy involved.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    environmentOptions: {
      jsdom: {
        url: 'http://localhost/overview',
      },
    },
    setupFiles: './src/__tests__/setup.js',
  },
  server: {
    port: 5178,
    proxy: {
      '/api': 'http://127.0.0.1:8117',
      '/ws': { target: 'ws://127.0.0.1:8117', ws: true },
    },
  },
})
