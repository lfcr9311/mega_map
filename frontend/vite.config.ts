import { defineConfig } from 'vite';

// Em dev, /api vai para o backend (fmsnav serve, porta 8001).
export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      '/api': process.env.FMSNAV_API ?? 'http://127.0.0.1:8001',
    },
  },
});
