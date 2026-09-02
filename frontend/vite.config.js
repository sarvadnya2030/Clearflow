import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3001,
    proxy: {
      '/mcp': {
        target: 'http://localhost:8087',
        changeOrigin: true,
      },
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
      },
      '/es': {
        target: 'http://localhost:9200',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/es/, ''),
      },
      '/health/8080': { target: 'http://localhost:8080', changeOrigin: true, rewrite: (p) => p.replace(/^\/health\/\d+/, '') },
      '/health/8081': { target: 'http://localhost:8081', changeOrigin: true, rewrite: (p) => p.replace(/^\/health\/\d+/, '') },
      '/health/8082': { target: 'http://localhost:8082', changeOrigin: true, rewrite: (p) => p.replace(/^\/health\/\d+/, '') },
      '/health/8083': { target: 'http://localhost:8083', changeOrigin: true, rewrite: (p) => p.replace(/^\/health\/\d+/, '') },
      '/health/8084': { target: 'http://localhost:8084', changeOrigin: true, rewrite: (p) => p.replace(/^\/health\/\d+/, '') },
      '/health/8085': { target: 'http://localhost:8085', changeOrigin: true, rewrite: (p) => p.replace(/^\/health\/\d+/, '') },
      '/health/8086': { target: 'http://localhost:8086', changeOrigin: true, rewrite: (p) => p.replace(/^\/health\/\d+/, '') },
      '/health/8087': { target: 'http://localhost:8087', changeOrigin: true, rewrite: (p) => p.replace(/^\/health\/\d+/, '') },
    },
  },
});
