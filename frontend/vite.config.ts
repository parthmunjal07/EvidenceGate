import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../evidencegate/api/static',
    emptyOutDir: true,
    sourcemap: false,
    assetsDir: 'assets',
  },
  server: {
    proxy: {
      '/health': 'http://127.0.0.1:8000', '/runtime': 'http://127.0.0.1:8000',
      '/results': 'http://127.0.0.1:8000', '/alerts': 'http://127.0.0.1:8000',
      '/events': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/replay': 'http://127.0.0.1:8000',
    },
  },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], clearMocks: true },
});
