#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const TILE_SIZE = 256;
const BYTES_PER_PIXEL_RGB565 = 2;
const BYTES_PER_TILE_RGB565 = TILE_SIZE * TILE_SIZE * BYTES_PER_PIXEL_RGB565;
const WEB_MERCATOR_LAT_LIMIT = 85.05112878;

function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 1) {
    const raw = argv[i];
    if (!raw.startsWith('--')) continue;
    const key = raw.slice(2);
    const next = argv[i + 1];
    if (next && !next.startsWith('--')) {
      args[key] = next;
      i += 1;
    } else {
      args[key] = true;
    }
  }
  return args;
}

function numArg(args, key, fallback = null) {
  const value = args[key];
  if (value === undefined || value === null || value === '') return fallback;
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) throw new Error(`--${key} must be a number`);
  return parsed;
}

function strArg(args, key, fallback = '') {
  const value = args[key];
  return value === undefined || value === null || value === '' ? fallback : String(value);
}

function lonToTile(lon, z) {
  return Math.floor(((lon + 180) / 360) * (2 ** z));
}

function latToTile(lat, z) {
  const clamped = Math.max(-WEB_MERCATOR_LAT_LIMIT, Math.min(WEB_MERCATOR_LAT_LIMIT, lat));
  const latRad = clamped * Math.PI / 180;
  return Math.floor((1 - Math.asinh(Math.tan(latRad)) / Math.PI) / 2 * (2 ** z));
}

function clampTile(value, z) {
  const max = (2 ** z) - 1;
  return Math.max(0, Math.min(max, value));
}

function round(value, places = 6) {
  const n = 10 ** places;
  return Math.round(value * n) / n;
}

function gib(bytes) {
  return bytes / (1024 ** 3);
}

function estimateBbox(lat, lon, radiusMiles) {
  const radiusKm = radiusMiles * 1.609344;
  const latDelta = radiusKm / 111.32;
  const lonDelta = radiusKm / (111.32 * Math.cos(lat * Math.PI / 180));
  return {
    lat_min: Math.max(-WEB_MERCATOR_LAT_LIMIT, lat - latDelta),
    lat_max: Math.min(WEB_MERCATOR_LAT_LIMIT, lat + latDelta),
    lon_min: lon - lonDelta,
    lon_max: lon + lonDelta,
  };
}

function zoomLevelPlan(bbox, z) {
  const xs = [clampTile(lonToTile(bbox.lon_min, z), z), clampTile(lonToTile(bbox.lon_max, z), z)].sort((a, b) => a - b);
  const ys = [clampTile(latToTile(bbox.lat_max, z), z), clampTile(latToTile(bbox.lat_min, z), z)].sort((a, b) => a - b);
  const tiles = (xs[1] - xs[0] + 1) * (ys[1] - ys[0] + 1);
  const raw_rgb565_bytes = tiles * BYTES_PER_TILE_RGB565;
  return {
    z,
    x_min: xs[0],
    x_max: xs[1],
    y_min: ys[0],
    y_max: ys[1],
    tiles,
    raw_rgb565_bytes,
    raw_rgb565_gib: Number(gib(raw_rgb565_bytes).toFixed(3)),
  };
}

function cumulative(levels, maxZoom) {
  const kept = levels.filter(level => level.z <= maxZoom);
  const tiles = kept.reduce((sum, level) => sum + level.tiles, 0);
  const raw_rgb565_bytes = kept.reduce((sum, level) => sum + level.raw_rgb565_bytes, 0);
  return { max_zoom: maxZoom, tiles, raw_rgb565_bytes, raw_rgb565_gib: Number(gib(raw_rgb565_bytes).toFixed(3)) };
}

const args = parseArgs(process.argv.slice(2));
const lat = numArg(args, 'lat');
const lon = numArg(args, 'lon');
if (lat === null || lon === null) throw new Error('Required: --lat <decimal> --lon <decimal>');
const radiusMiles = numArg(args, 'radius-miles', 150);
const minZoom = numArg(args, 'min-zoom', 0);
const maxZoom = numArg(args, 'max-zoom', 14);
const blanketMaxZoom = numArg(args, 'blanket-max-zoom', 12);
const budgetGiB = numArg(args, 'budget-gib', 4);
const theme = strArg(args, 'theme', 'topo-night');
const name = strArg(args, 'name', `MapPI3 ${radiusMiles}mi ${theme}`);
const id = strArg(args, 'id', name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''));
const outPath = strArg(args, 'out', '');
const source = strArg(args, 'source', 'planner-only-no-download');

if (radiusMiles <= 0) throw new Error('--radius-miles must be positive');
if (minZoom < 0 || maxZoom < minZoom) throw new Error('zoom range must satisfy 0 <= min <= max');
if (blanketMaxZoom < minZoom || blanketMaxZoom > maxZoom) throw new Error('--blanket-max-zoom must be inside min/max zoom range');

const bbox = estimateBbox(lat, lon, radiusMiles);
const levels = [];
for (let z = minZoom; z <= maxZoom; z += 1) levels.push(zoomLevelPlan(bbox, z));
const cumulativeByMaxZoom = [];
for (let z = minZoom; z <= maxZoom; z += 1) cumulativeByMaxZoom.push(cumulative(levels, z));
const blanket = cumulative(levels, blanketMaxZoom);
const nextLevel = levels.find(level => level.z === blanketMaxZoom + 1) || null;
const warningLevels = cumulativeByMaxZoom.filter(row => row.raw_rgb565_gib > budgetGiB).map(row => row.max_zoom);

const plan = {
  schema: 'mappi3.map-pack-plan.v1',
  id,
  name,
  created_at: new Date().toISOString(),
  planner: 'scripts/plan-map-pack.mjs',
  mode: 'dry-run-size-plan-no-tile-download',
  source,
  theme,
  center: { lat: round(lat, 9), lon: round(lon, 9) },
  radius_miles: radiusMiles,
  bbox: Object.fromEntries(Object.entries(bbox).map(([key, value]) => [key, round(value, 9)])),
  tile_format: {
    tile_size: TILE_SIZE,
    output_pixel_format: 'RGB565 little-endian planned',
    bytes_per_tile: BYTES_PER_TILE_RGB565,
    fixed_grid_offset_formula: 'offset = ((y - y_min) * width_tiles + (x - x_min)) * 131072 within the zoom pack',
    note: 'This plan does not download or convert map tiles. It is the storage guardrail before building a microSD RGB565 pack.',
  },
  zoom_policy: {
    min_zoom: minZoom,
    max_zoom_estimated: maxZoom,
    blanket_max_zoom: blanketMaxZoom,
    budget_gib: budgetGiB,
    recommendation: warningLevels.length
      ? `Keep blanket coverage at z0-z${blanketMaxZoom}; z0-z${warningLevels[0]} exceeds the ${budgetGiB} GiB raw RGB565 budget for this radius.`
      : `z0-z${blanketMaxZoom} is inside the ${budgetGiB} GiB raw RGB565 budget.`,
    high_zoom_policy: 'Use higher zooms only for selected trail corridors, parks, towns, or custom route buffers; do not blanket-cache high zooms for the whole radius.',
  },
  levels,
  cumulative_by_max_zoom: cumulativeByMaxZoom,
  selected_blanket: blanket,
  next_zoom_level: nextLevel,
  generated_files: [],
  safety: {
    no_internet_required_after_pack_build: true,
    no_phone_required_for_pi_native_renderer: true,
    browser_leaflet_requires_png_webp_or_runtime_rgb565_canvas_conversion: true,
    navigation_warning: 'MapPI3 assists navigation; carry real map/compass/emergency tools.',
  },
};

const summary = [
  `${plan.name}`,
  `center ${plan.center.lat}, ${plan.center.lon} · radius ${plan.radius_miles} mi · theme ${plan.theme}`,
  `blanket z0-z${blanketMaxZoom}: ${blanket.tiles} tiles · ${blanket.raw_rgb565_gib} GiB raw RGB565`,
  nextLevel ? `next z${nextLevel.z} alone: ${nextLevel.tiles} tiles · ${nextLevel.raw_rgb565_gib} GiB` : '',
  plan.zoom_policy.recommendation,
].filter(Boolean).join('\n');

if (outPath) {
  const resolved = path.resolve(outPath);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  fs.writeFileSync(resolved, `${JSON.stringify(plan, null, 2)}\n`);
  console.log(`${summary}\nwrote ${resolved}`);
} else {
  console.log(JSON.stringify(plan, null, 2));
}
