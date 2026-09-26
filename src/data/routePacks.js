import routePacks from './routePacks.json';

export const mapRoutePackToCard = (pack) => ({
  id: pack.id,
  schemaVersion: pack.schemaVersion,
  name: pack.name,
  place: pack.place,
  region: pack.region,
  // Keep the pack's numeric fields as well as the display strings; navigation, weather and
  // stats code read distanceMiles/elevationGainFt and got 0 when only the card fields existed.
  distanceMiles: pack.distanceMiles,
  elevationGainFt: pack.elevationGainFt,
  estimatedTime: pack.estimatedTime,
  miles: pack.distanceMiles,
  time: pack.estimatedTime,
  gain: `${pack.elevationGainFt.toLocaleString()} ft`,
  tags: pack.tags,
  difficulty: pack.difficulty,
  status: pack.status,
  size: `${pack.storageEstimateMb} MB`,
  storageEstimateMb: pack.storageEstimateMb,
  routeType: pack.routeType,
  duplicateOf: pack.duplicateOf,
  mountainArea: pack.mountainArea,
  catalogCategory: pack.catalogCategory,
  landType: pack.landType,
  sync: pack.sync,
  offline: pack.offline,
  weather: pack.weather,
  geometry: pack.geometry,
  geometryQuality: pack.geometryQuality || pack.geometry?.source || 'seed-planning',
  statsCheck: pack.statsCheck,
  color: pack.color,
  segments: pack.segments,
  markerDensity: pack.markerDensity,
  mapPreviewPath: pack.mapPreviewPath,
  waypoints: pack.waypoints,
  pois: pack.pois
});

export const seedRoutePacks = routePacks;
export const seedRoutes = routePacks.map(mapRoutePackToCard);
export const primaryRoutePack = routePacks.find(pack => pack.id === 'me-speck-pond-route26-at') || routePacks[0];
export const primaryWaypoints = primaryRoutePack.waypoints;
export const primaryMapPreviewPath = primaryRoutePack.mapPreviewPath;
