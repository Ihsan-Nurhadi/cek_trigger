import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/sites': 'http://localhost:8000',
      '/notifications': 'http://localhost:8000',
      '/stream': 'http://localhost:8000',
      '/logs-history': 'http://localhost:8000',
      '/logs-json': 'http://localhost:8000',
      '/download': 'http://localhost:8000',
      '/media': 'http://localhost:8000',
    }
  }
})
