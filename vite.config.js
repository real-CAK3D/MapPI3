import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Dev/preview on a PC forwards /api to a live Pi (e.g. over its hotspot) so sensors, GPS and
// Whisplay state are real while iterating on the UI. Override with MAPPI3_PI_URL.
const piApi = process.env.MAPPI3_PI_URL || 'http://10.42.0.1:5050';
const proxy = { '/api': { target: piApi, changeOrigin: true } };

export default defineConfig({
  plugins: [react()],
  // MapLibre's 3D worker is bundled as an ES module worker (see src/station/TerrainViews.jsx).
  worker: { format: 'es' },
  // In dev, load MapLibre as-is so it finds maplibre-gl-worker.mjs beside itself.
  optimizeDeps: { exclude: ['maplibre-gl'] },
  server: {
    host: '0.0.0.0',
    proxy,
    allowedHosts: [
      'mappi3-cak3d.loca.lt',
      'localhost',
      '127.0.0.1',
      '150.136.165.61',
      '100.82.165.23',
      'terminal-vnic.tailac984b.ts.net'
    ]
  },
  preview: {
    host: '0.0.0.0',
    proxy,
    allowedHosts: [
      'mappi3-cak3d.loca.lt',
      'localhost',
      '127.0.0.1',
      '150.136.165.61',
      '100.82.165.23',
      'terminal-vnic.tailac984b.ts.net'
    ]
  }
});
