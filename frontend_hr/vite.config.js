import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dentro GestionaleCloud l'app e' servita dal sotto-percorso /hr/ (sotto-app
// FastAPI montata a /hr: API a /hr/api/..., bundle a /hr/assets/...).
export default defineConfig({
  base: '/hr/',
  plugins: [react()],
  server: {
    proxy: {
      '/hr/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      }
    }
  },
  build: {
    outDir: 'dist',
  }
})
