import { defineConfig } from 'vitest/config';
import { loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const apiTarget = loadEnv(mode, '.', 'VITE_').VITE_API_PROXY_TARGET ?? 'http://127.0.0.1:8000';
  return {
  plugins: [react()],
  build: {
    outDir: '../evidencegate/api/static',
    emptyOutDir: true,
    sourcemap: false,
    assetsDir: 'assets',
  },
  server: {
    proxy: {
      '/health': apiTarget, '/runtime': apiTarget, '/runtime/trace': apiTarget,
      '/results': apiTarget, '/alerts': apiTarget,
      '/family-evidence': apiTarget, '/investigations': apiTarget,
      '/events': { target: apiTarget, changeOrigin: true },
      '/replay': apiTarget,
    },
  },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], clearMocks: true },
  };
});
