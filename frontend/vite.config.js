import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      // Use explicit IPv4 — Node 17+ resolves "localhost" to IPv6 ::1 first,
      // but uvicorn binds IPv4 127.0.0.1, which caused proxy 500s.
      '/api': 'http://127.0.0.1:8001'
    }
  }
})
