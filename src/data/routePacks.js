import routePacks from './routePacks.json';

export const mapRoutePackToCard = (pack) => ({
  id: pack.id,
  schemaVersion: pack.schemaVersion,
  name: pack.name,
  place: pack.place,
  miles: pack.distanceMiles,
  time: pack.estimatedTime,
  gain: `${pack.elevationGainFt.toLocaleString()} ft`,
  tags: pack.tags,
  difficulty: pack.difficulty,
  status: pack.status,
  size: `${pack.storageEstimateMb} MB`,
  storageEstimateMb: pack.storageEstimateMb,
  routeType: pack.routeType,
  sync: pack.sync,
  offline: pack.offline,
  geometry: pack.geometry,
  mapPreviewPath: pack.mapPreviewPath,
  waypoints: pack.waypoints,
  pois: pack.pois
});

export const seedRoutePacks = routePacks;
export const seedRoutes = routePacks.map(mapRoutePackToCard);
export const primaryRoutePack = routePacks[0];
export const primaryWaypoints = primaryRoutePack.waypoints;
export const primaryMapPreviewPath = primaryRoutePack.mapPreviewPath;
