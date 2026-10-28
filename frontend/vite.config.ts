import { defineConfig } from 'vite';

// O app vive em /map/ (a raiz do EC2 e de outro app); a API em /map/api.
// Em dev, /map/api vai para o backend (fmsnav serve, porta 8001).
export default defineConfig({
  base: '/map/',
  server: {
    port: 5173,
    proxy: {
      '/map/api': process.env.FMSNAV_API ?? 'http://127.0.0.1:8001',
    },
  },
});
