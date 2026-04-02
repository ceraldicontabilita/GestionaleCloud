import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Plugin keepalive: invia WebSocket ping ogni 20s
// per evitare che il proxy Kubernetes (timeout 30s) chiuda la connessione
const wsKeepalivePlugin = {
  name: 'ws-keepalive',
  configureServer(server) {
    const iv = setInterval(() => {
      try {
        server.ws.clients.forEach(client => {
          if (client.readyState === 1) client.ping();
        });
      } catch (_) {}
    }, 20000);
    server.httpServer?.on('close', () => clearInterval(iv));
  }
};

export default defineConfig({
  plugins: [react(), wsKeepalivePlugin],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 3000,
    allowedHosts: true,
    hmr: false,
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
