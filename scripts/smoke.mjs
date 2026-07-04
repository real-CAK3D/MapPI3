import { readdirSync, readFileSync, existsSync } from 'node:fs';
if (!existsSync('dist/index.html')) { console.error('Missing dist/index.html'); process.exit(1); }
if (!existsSync('dist/assets')) { console.error('Missing dist/assets'); process.exit(1); }
const html = readFileSync('dist/index.html', 'utf8');
const assets = readdirSync('dist/assets');
if (!html.includes('/assets/') || !assets.some(a => a.endsWith('.js'))) { console.error('Build output missing app assets'); process.exit(1); }
console.log('MapPi3 smoke check passed: dist exists and index references app assets.');
