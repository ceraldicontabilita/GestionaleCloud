// Stesso contratto di build per Menu e Lotti: URL dedicati, React della miniapp,
// moduli condivisi e solo variabili pubbliche nel bundle del browser.
import path from 'node:path';

export function miniAppConfig({ root, base, mode, loadEnv, transformWithEsbuild, react }) {
  const env = loadEnv(mode, root, ['REACT_APP_']);
  const publicEnv = {
    ...env, NODE_ENV: mode === 'production' ? 'production' : 'development',
    PUBLIC_URL: base.replace(/\/$/, ''),
    REACT_APP_LOTTI_BACKEND_URL: env.REACT_APP_LOTTI_BACKEND_URL || '/lotti',
    REACT_APP_MENU_BACKEND_URL: env.REACT_APP_MENU_BACKEND_URL || '/menu',
  };
  return {
    root, base,
    plugins: [
      { name: 'jsx-in-existing-js', enforce: 'pre', async transform(code, id) {
        const normalizedId = path.normalize(id);
        const normalizedSrc = path.normalize(path.join(root, 'src'));
        if (normalizedId.startsWith(normalizedSrc) && /\.js$/.test(normalizedId)) {
          return transformWithEsbuild(code, id, { loader: 'jsx', jsx: 'automatic' });
        }
      } },
      react(),
    ],
    define: { 'process.env': JSON.stringify(publicEnv) },
    resolve: { alias: { '@': path.join(root, 'src') }, dedupe: ['react', 'react-dom'] },
    optimizeDeps: { esbuildOptions: { loader: { '.js': 'jsx' } } },
    build: { outDir: 'build', emptyOutDir: true, chunkSizeWarningLimit: 1500 },
    server: { fs: { allow: [path.resolve(root, '..')] }, proxy: {
      [`${base.replace(/\/$/, '')}/api`]: { target: 'http://localhost:8000', changeOrigin: true },
    } },
  };
}
