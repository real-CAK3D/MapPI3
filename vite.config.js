import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    allowedHosts: [
      'mappi3-cak3d.loca.lt',
      'localhost',
      '127.0.0.1',
      '150.136.165.61',
      '100.82.165.23'
    ]
  },
  preview: {
    host: '0.0.0.0',
    allowedHosts: [
      'mappi3-cak3d.loca.lt',
      'localhost',
      '127.0.0.1',
      '150.136.165.61',
      '100.82.165.23'
    ]
  }
});
