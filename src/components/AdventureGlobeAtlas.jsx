import React, { useEffect, useMemo, useRef, useState } from 'react';
import * as am5 from '@amcharts/amcharts5';
import * as am5map from '@amcharts/amcharts5/map';
import am5themes_Animated from '@amcharts/amcharts5/themes/Animated';
import am5geodata_worldLow from '@amcharts/amcharts5-geodata/worldLow';

function supportsAmChartsCanvas() {
  try {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext && canvas.getContext('2d');
    return Boolean(context && typeof context.createImageData === 'function');
  } catch (_error) {
    return false;
  }
}

function safePoint(point) {
  const lat = Number(point?.lat);
  const lon = Number(point?.lon);
  if (![lat, lon].every(Number.isFinite)) return null;
  return {
    id: String(point.id || `${point.kind || 'point'}-${lat.toFixed(3)}-${lon.toFixed(3)}`),
    name: String(point.name || point.type || 'Adventure point'),
    kind: String(point.kind || 'event'),
    lat,
    lon,
    size: Math.max(5, Math.min(18, Number(point.size || 9) / 3)),
    value: Math.max(20, Math.min(450, Number(point.count || 1) * 45)),
    notes: String(point.notes || point.type || '')
  };
}

function atlasTrailFlows(points) {
  const home = points.find(point => point.kind === 'home') || points[0];
  if (!home) return [];
  return points
    .filter(point => point !== home && Number.isFinite(point.lat) && Number.isFinite(point.lon))
    .map((point, index) => ({
      id: `home-to-${point.id || index}`,
      name: `${home.name || 'Home-Base'} → ${point.name || 'Trailhead'}`,
      homeName: home.name || 'Home-Base',
      targetName: point.name || 'Trailhead',
      value: point.value || 45,
      geometry: {
        type: 'LineString',
        coordinates: [[home.lon, home.lat], [point.lon, point.lat]]
      }
    }));
}

function createCodePenGlobe(container, points, onModeChange) {
  const root = am5.Root.new(container);

  const trailTheme = am5.Theme.new(root);
  trailTheme.rule('InterfaceColors').setAll({
    primaryButton: am5.color(0x9ce36c),
    primaryButtonHover: am5.color(0x6fb34c),
    primaryButtonDown: am5.color(0x385f25),
    primaryButtonActive: am5.color(0xf2d25c),
    primaryButtonText: am5.color(0x071108),
    secondaryButton: am5.color(0xf4e08a),
    secondaryButtonHover: am5.color(0xdac95f),
    secondaryButtonDown: am5.color(0xa4b657),
    secondaryButtonText: am5.color(0x102014),
    background: am5.color(0x143019),
    text: am5.color(0xf7ffe6)
  });

  root.setThemes([am5themes_Animated.new(root), trailTheme]);

  root.container.set('background', am5.Rectangle.new(root, {
    fill: am5.color(0x102014),
    fillPattern: am5.GrainPattern.new(root, {
      density: 0.35,
      maxOpacity: 0.08,
      colors: [am5.color(0xf2d25c)]
    })
  }));

  const forestInk = am5.color(0x071108);
  const deepPine = am5.color(0x102014);
  const trailGreen = am5.color(0x58a94b);
  const leafGlow = am5.color(0x9ce36c);
  const trailGold = am5.color(0xf2d25c);
  const paleTrail = am5.color(0xf7ffe6);

  const chart = root.container.children.push(am5map.MapChart.new(root, {
    panX: 'rotateX',
    panY: 'rotateY',
    projection: am5map.geoOrthographic(),
    rotationX: -15,
    rotationY: -20,
    minZoomLevel: 0.5,
    zoomLevel: 0.9
  }));

  const bgSeries = chart.series.push(am5map.MapPolygonSeries.new(root, {}));
  bgSeries.mapPolygons.template.setAll({
    fill: am5.color(0x16361d),
    fillOpacity: 1,
    strokeOpacity: 0
  });
  bgSeries.data.push({ geometry: am5map.getGeoRectangle(90, 180, -90, -180) });

  const graticuleSeries = chart.series.push(am5map.GraticuleSeries.new(root, {}));
  graticuleSeries.mapLines.template.setAll({
    stroke: leafGlow,
    strokeOpacity: 0.15,
    strokeWidth: 0.5
  });

  const polygonSeries = chart.series.push(am5map.MapPolygonSeries.new(root, {
    geoJSON: am5geodata_worldLow
  }));
  polygonSeries.mapPolygons.template.setAll({
    fill: am5.color(0xddea96),
    stroke: trailGreen,
    strokeWidth: 0.5,
    strokeOpacity: 0.5
  });

  const activeCountryIds = new Set(['US']);
  points.forEach((point) => {
    if (point.lat >= 24 && point.lat <= 72 && point.lon >= -170 && point.lon <= -52) activeCountryIds.add('US');
    else if (point.lat >= 14 && point.lat <= 33 && point.lon >= -118 && point.lon <= -86) activeCountryIds.add('MX');
    else if (point.lat >= 49 && point.lat <= 61 && point.lon >= -8 && point.lon <= 2) activeCountryIds.add('GB');
  });

  polygonSeries.events.on('datavalidated', function () {
    am5.array.each(polygonSeries.dataItems, function (di) {
      const id = di.get('id');
      if (id && activeCountryIds.has(id)) {
        di.get('mapPolygon').setAll({ fill: am5.color(0xa6bf66), stroke: trailGold, strokeOpacity: 0.8 });
      }
    });
  });

  const lineSeries = chart.series.push(am5map.MapLineSeries.new(root, {}));
  lineSeries.mapLines.template.setAll({
    stroke: trailGold,
    strokeOpacity: 0.82,
    strokeWidth: 2,
    tooltipText: '{name}',
    lineType: 'curved'
  });

  lineSeries.bullets.push(function () {
    return am5.Bullet.new(root, {
      locationX: 0,
      autoRotate: true,
      sprite: am5.Circle.new(root, {
        radius: 4,
        fill: trailGold,
        stroke: deepPine,
        strokeWidth: 1.4,
        visible: false
      })
    });
  });

  lineSeries.data.setAll(atlasTrailFlows(points));

  lineSeries.events.on('datavalidated', function () {
    am5.array.each(lineSeries.dataItems, function (dataItem, index) {
      const bullets = dataItem.bullets;
      if (bullets) {
        am5.array.each(bullets, function (bullet) {
          const durationMs = 3400 + (index % 4) * 650;
          const delay = (index % 5) * 420;
          setTimeout(function () {
            if (root.isDisposed()) return;
            const sprite = bullet.get('sprite');
            if (sprite) sprite.set('visible', true);
            bullet.animate({
              key: 'locationX',
              from: 0,
              to: 1,
              duration: durationMs,
              easing: am5.ease.linear,
              loops: Infinity
            });
          }, delay);
        });
      }
    });
  });

  const pointSeries = chart.series.push(am5map.MapPointSeries.new(root, {
    latitudeField: 'lat',
    longitudeField: 'lon'
  }));
  pointSeries.bullets.push(function (_root, _series, dataItem) {
    const data = dataItem.dataContext || {};
    const isHome = data.kind === 'home';
    return am5.Bullet.new(root, {
      sprite: am5.Circle.new(root, {
        radius: isHome ? 8 : 5,
        fill: isHome ? trailGold : leafGlow,
        stroke: isHome ? paleTrail : deepPine,
        strokeWidth: isHome ? 3 : 2,
        tooltipText: '{name}\n{notes}'
      })
    });
  });
  pointSeries.data.setAll(points.map(point => ({ ...point, geometry: { type:'Point', coordinates:[point.lon, point.lat] } })));

  const titleCont = chart.children.push(am5.Container.new(root, {
    layout: root.verticalLayout,
    x: am5.p50,
    centerX: am5.p50,
    y: am5.p100,
    centerY: am5.p100,
    position: 'absolute',
    paddingBottom: 16
  }));

  titleCont.children.push(am5.Label.new(root, {
    text: 'MapPI3 Adventure Globe',
    fontSize: 18,
    fontWeight: '600',
    fill: trailGold,
    x: am5.p50,
    centerX: am5.p50
  }));

  titleCont.children.push(am5.Label.new(root, {
    text: '(Home-Base → chosen trail locations)',
    fontSize: 11,
    fill: leafGlow,
    x: am5.p50,
    centerX: am5.p50
  }));

  const switchCont = chart.children.push(am5.Container.new(root, {
    layout: root.horizontalLayout,
    x: 20,
    y: 40
  }));

  switchCont.children.push(am5.Label.new(root, {
    centerY: am5.p50,
    text: 'Globe',
    fill: trailGold,
    fontSize: 13
  }));

  const switchButton = switchCont.children.push(am5.Button.new(root, {
    themeTags: ['switch'],
    centerY: am5.p50,
    icon: am5.Circle.new(root, {
      themeTags: ['icon']
    })
  }));

  const easing = am5.ease.inOut(am5.ease.cubic);
  const duration = 1500;
  const fadeDuration = 300;

  function zoomToGlobe() {
    chart.set('projection', am5map.geoOrthographic());
    chart.set('panX', 'rotateX');
    chart.set('panY', 'rotateY');
    chart.animate({ key: 'rotationX', to: -15, duration, easing });
    chart.animate({ key: 'rotationY', to: -20, duration, easing });
    bgSeries.mapPolygons.template.set('fillOpacity', 1);
    chart.set('minZoomLevel', 0.9);
    chart.animate({ key: 'zoomLevel', to: 0.9, duration, easing });
  }

  function zoomToMap() {
    chart.set('projection', am5map.geoMercator());
    chart.set('panX', 'translateX');
    chart.set('panY', 'translateY');
    chart.animate({ key: 'rotationX', to: 0, duration, easing });
    chart.animate({ key: 'rotationY', to: 0, duration, easing });
    bgSeries.mapPolygons.template.set('fillOpacity', 0);
    chart.set('minZoomLevel', 1);
    chart.animate({ key: 'zoomLevel', to: 1.7, duration, easing });
  }

  switchButton.on('active', function () {
    chart.goHome(duration);
    setTimeout(function () {
      if (!root.isDisposed()) chart.seriesContainer.animate({ key: 'opacity', to: 0, duration: fadeDuration });
    }, duration - fadeDuration);
    setTimeout(function () {
      if (root.isDisposed()) return;
      if (switchButton.get('active')) { zoomToMap(); if (onModeChange) onModeChange('detail'); }
      else { zoomToGlobe(); if (onModeChange) onModeChange('globe'); }
      chart.seriesContainer.animate({ key: 'opacity', to: 1, duration: fadeDuration });
    }, duration);
  });

  switchCont.children.push(am5.Label.new(root, {
    centerY: am5.p50,
    text: 'Map',
    fill: trailGold,
    fontSize: 13
  }));

  const zoomControl = chart.set('zoomControl', am5map.ZoomControl.new(root, {}));
  zoomControl.homeButton.set('visible', true);

  let rotationAnimation = chart.animate({
    key: 'rotationX',
    from: -15,
    to: -15 + 360,
    duration: 120000,
    loops: Infinity,
    easing: am5.ease.linear
  });

  chart.chartContainer.events.on('pointerdown', function () {
    if (rotationAnimation) {
      rotationAnimation.stop();
      rotationAnimation = null;
    }
  });

  chart.appear(1000, 100);
  return root;
}

export default function AdventureGlobeAtlas({ points = [] }) {
  const chartRef = useRef(null);
  const rootRef = useRef(null);
  const [status, setStatus] = useState('loading globe');
  const [atlasMode, setAtlasMode] = useState('globe');
  const [selectedPointId, setSelectedPointId] = useState('');
  const normalizedPoints = useMemo(() => (points || []).map(safePoint).filter(Boolean), [points]);

  useEffect(() => {
    if (!selectedPointId && normalizedPoints.length) setSelectedPointId((normalizedPoints.find(point => point.kind !== 'home') || normalizedPoints[0]).id);
  }, [normalizedPoints, selectedPointId]);

  useEffect(() => {
    let cancelled = false;
    if (!chartRef.current) return undefined;
    setStatus('loading amCharts globe');
    if (!supportsAmChartsCanvas()) {
      setStatus('amCharts globe waits for a real browser canvas');
      return undefined;
    }
    try {
      if (rootRef.current) rootRef.current.dispose();
      rootRef.current = createCodePenGlobe(chartRef.current, normalizedPoints, setAtlasMode);
      setStatus('ready');
    } catch (error) {
      if (!cancelled) setStatus(error?.message || 'amCharts globe failed to load');
    }
    return () => {
      cancelled = true;
      if (rootRef.current) {
        rootRef.current.dispose();
        rootRef.current = null;
      }
    };
  }, [normalizedPoints]);

  const homePoint = normalizedPoints.find(point => point.kind === 'home') || normalizedPoints[0];
  const trailPoints = normalizedPoints.filter(point => point.kind !== 'home');
  const selectedPoint = normalizedPoints.find(point => point.id === selectedPointId) || trailPoints[0] || homePoint;
  const detailPoints = [homePoint, selectedPoint].filter(Boolean);
  const routeSvgPoints = detailPoints.length >= 2 ? detailPoints.map((point, index) => {
    const lonRange = Math.max(0.01, Math.abs(detailPoints[1].lon - detailPoints[0].lon));
    const latRange = Math.max(0.01, Math.abs(detailPoints[1].lat - detailPoints[0].lat));
    const minLon = Math.min(...detailPoints.map(p => p.lon));
    const maxLat = Math.max(...detailPoints.map(p => p.lat));
    const x = 18 + ((point.lon - minLon) / lonRange) * 64;
    const y = 18 + ((maxLat - point.lat) / latRange) * 44 + (index ? 8 : -8);
    return [Math.max(10, Math.min(90, x)), Math.max(10, Math.min(82, y))];
  }) : [];
  const routePath = routeSvgPoints.length >= 2 ? `M ${routeSvgPoints[0][0]} ${routeSvgPoints[0][1]} C 42 15, 58 82, ${routeSvgPoints[1][0]} ${routeSvgPoints[1][1]}` : '';

  return <div className={`adventure-globe-codepen-card atlas-${atlasMode}`}>
    <div className="atlas-mode-toolbar" aria-label="Adventure atlas mode">
      <button className={atlasMode === 'globe' ? 'active' : ''} onClick={() => setAtlasMode('globe')}>Globe flow</button>
      <button className={atlasMode === 'detail' ? 'active' : ''} onClick={() => setAtlasMode('detail')}>Trail detail</button>
    </div>
    <div ref={chartRef} id="chartdiv" className="adventure-globe-codepen-chart" />
    {atlasMode === 'detail' && selectedPoint ? <div className="atlas-trail-detail-panel">
      <div className="section-head compact"><div><h3>Trail detail preview</h3><p className="muted">Offline/Pi-safe pseudo-3D route focus using MapPI3 points, not online ArcGIS runtime.</p></div><span className="pill">detail mode</span></div>
      <label className="field-line"><span>Focus hike</span><select value={selectedPoint.id} onChange={event => setSelectedPointId(event.target.value)}>{trailPoints.map(point => <option key={point.id} value={point.id}>{point.name}</option>)}</select></label>
      <div className="atlas-terrain-card">
        <svg viewBox="0 0 100 100" role="img" aria-label="3D style route corridor preview"><defs><linearGradient id="mappi3Ridge" x1="0" x2="1" y1="0" y2="1"><stop offset="0" stopColor="#214f2a"/><stop offset="0.55" stopColor="#6f8f3a"/><stop offset="1" stopColor="#d5b65c"/></linearGradient></defs><path d="M0 76 C20 58 32 66 45 48 C60 28 76 45 100 22 L100 100 L0 100 Z" fill="url(#mappi3Ridge)" opacity="0.92"/><path d="M0 88 C18 76 34 82 52 66 C70 49 84 57 100 42" fill="none" stroke="rgba(255,255,255,.2)" strokeWidth="1"/><path d={routePath} fill="none" stroke="#f2d25c" strokeWidth="4" strokeLinecap="round" strokeDasharray="5 4"/><circle cx={routeSvgPoints[0]?.[0] || 18} cy={routeSvgPoints[0]?.[1] || 24} r="4" fill="#fff8bd"/><circle cx={routeSvgPoints[1]?.[0] || 82} cy={routeSvgPoints[1]?.[1] || 72} r="4" fill="#9ce36c"/></svg>
        <div><strong>{selectedPoint.name}</strong><span>{selectedPoint.notes || selectedPoint.kind}</span><small>{selectedPoint.lat.toFixed(5)}, {selectedPoint.lon.toFixed(5)} · map-pack/detail-ready corridor</small></div>
      </div>
      <div className="atlas-detail-chips"><span>shaded corridor</span><span>offline geometry</span><span>field-readable markers</span><span>future elevation pack</span></div>
    </div> : null}
    {status !== 'ready' ? <div className="adventure-globe-codepen-status">{status}</div> : null}
  </div>;
}
