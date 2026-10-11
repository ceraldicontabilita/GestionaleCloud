import { defineConfig, loadEnv, transformWithEsbuild } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';
import { miniAppConfig } from '../frontend_shared/viteMiniApp.mjs';
const root = fileURLToPath(new URL('.', import.meta.url));
export default defineConfig(({ mode }) => miniAppConfig({
  root, base: '/menu/', mode, loadEnv, transformWithEsbuild, react,
}));
