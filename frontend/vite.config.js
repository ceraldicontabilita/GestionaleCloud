import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    allowedHosts: true,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8001',
        changeOrigin: true,
      },
      '/health': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8001',
        changeOrigin: true,
      },
      '/docs': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8001',
        changeOrigin: true,
      },
      '/redoc': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8001',
        changeOrigin: true,
      },
      '/openapi.json': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8001',
        changeOrigin: true,
      }
    }
  }
})
