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
      } catch (_) { }
    }, 20000);
    server.httpServer?.on('close', () => clearInterval(iv));
  }
};

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
    hmr: false,
    ws: false,
    proxy: {
      '/api': {
        target: process.env.VITE_BACKEND_URL || 'http://localhost:8001',
        changeOrigin: true,
        ws: true,  // Abilita proxy WebSocket per /api/ws/*
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
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    // Le pagine ERP montano tabelle e contesti articolati: troppi worker jsdom
    // saturano la macchina CI e producono timeout casuali su test che, isolati,
    // passano. Due worker mantengono la suite parallela ma deterministica.
    maxWorkers: 2,
  },
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        // Separa i vendor stabili in chunk propri: cambiano di rado, quindi
        // restano in cache del browser quando cambia il codice dell'app
        // (l'utente non riscarica React/router/query/grafici ad ogni deploy).
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'query-vendor': ['@tanstack/react-query'],
          'charts-vendor': ['recharts'],
        },
      },
    },
  },
})
