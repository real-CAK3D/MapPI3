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

function countryIdForPoint(point) {
  const { lat, lon } = point;
  if (lat >= 24 && lat <= 72 && lon >= -170 && lon <= -52) return lon < -141 ? 'US' : 'US';
  if (lat >= 42 && lat <= 84 && lon >= -141 && lon <= -52) return 'CA';
  if (lat >= 14 && lat <= 33 && lon >= -118 && lon <= -86) return 'MX';
  if (lat >= 49 && lat <= 61 && lon >= -8 && lon <= 2) return 'GB';
  if (lat >= 41 && lat <= 51 && lon >= -5 && lon <= 9) return 'FR';
  if (lat >= 47 && lat <= 55 && lon >= 5 && lon <= 16) return 'DE';
  if (lat >= 35 && lat <= 47 && lon >= 6 && lon <= 19) return 'IT';
  if (lat >= 30 && lat <= 46 && lon >= 129 && lon <= 146) return 'JP';
  return lon < -30 ? 'US' : lon < 60 ? 'DE' : 'JP';
}

function atlasSankeyData(points) {
  const home = points.find(point => point.kind === 'home') || points[0];
  const travel = points.filter(point => point !== home);
  if (!home || !travel.length) {
    return [
      { sourceId: 'US', targetId: 'CA', value: 120 },
      { sourceId: 'US', targetId: 'JP', value: 80 },
      { sourceId: 'DE', targetId: 'FR', value: 90 }
    ];
  }
  const homeCountry = countryIdForPoint(home);
  const seen = new Map();
  travel.forEach((point) => {
    const country = countryIdForPoint(point);
    const key = `${homeCountry}-${country}`;
    const current = seen.get(key) || { sourceId: homeCountry, targetId: country, value: 0 };
    current.value += point.value;
    seen.set(key, current);
  });
  const rows = Array.from(seen.values()).filter(row => row.sourceId !== row.targetId);
  return rows.length ? rows : [{ sourceId: 'US', targetId: 'CA', value: 120 }, { sourceId: 'US', targetId: 'JP', value: 80 }];
}

function createCodePenGlobe(container, points) {
  const root = am5.Root.new(container);

  const coffeeTheme = am5.Theme.new(root);
  coffeeTheme.rule('InterfaceColors').setAll({
    primaryButton: am5.color(0x8b5e3c),
    primaryButtonHover: am5.color(0x5c3a1e),
    primaryButtonDown: am5.color(0x3c1e0e),
    primaryButtonActive: am5.color(0xc4956a),
    primaryButtonText: am5.color(0xf5ece0),
    secondaryButton: am5.color(0xe8d5b7),
    secondaryButtonHover: am5.color(0xd4c4a8),
    secondaryButtonDown: am5.color(0xc4956a),
    secondaryButtonText: am5.color(0x3c1e0e),
    background: am5.color(0xe8d5b7),
    text: am5.color(0x3c1e0e)
  });

  root.setThemes([am5themes_Animated.new(root), coffeeTheme]);

  root.container.set('background', am5.Rectangle.new(root, {
    fill: am5.color(0xf0e6d6),
    fillPattern: am5.GrainPattern.new(root, {
      density: 0.4,
      maxOpacity: 0.07,
      colors: [am5.color(0x000000)]
    })
  }));

  const espresso = am5.color(0x3c1e0e);
  const darkRoast = am5.color(0x5c3a1e);
  const mediumRoast = am5.color(0x8b5e3c);
  const lightRoast = am5.color(0xc4956a);
  const crema = am5.color(0xe8d5b7);
  const cream = am5.color(0xf5ece0);

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
    fill: am5.color(0xede4d4),
    fillOpacity: 1,
    strokeOpacity: 0
  });
  bgSeries.data.push({ geometry: am5map.getGeoRectangle(90, 180, -90, -180) });

  const graticuleSeries = chart.series.push(am5map.GraticuleSeries.new(root, {}));
  graticuleSeries.mapLines.template.setAll({
    stroke: mediumRoast,
    strokeOpacity: 0.15,
    strokeWidth: 0.5
  });

  const polygonSeries = chart.series.push(am5map.MapPolygonSeries.new(root, {
    geoJSON: am5geodata_worldLow
  }));
  polygonSeries.mapPolygons.template.setAll({
    fill: cream,
    stroke: lightRoast,
    strokeWidth: 0.5,
    strokeOpacity: 0.5
  });

  const producerIds = ['BR', 'VN', 'CO', 'ET', 'ID', 'HN'];
  const hubIds = ['DE', 'BE', 'IT', 'US'];
  const consumerIds = ['FR', 'PL', 'SE', 'RU', 'GB', 'NL', 'GR', 'AT', 'CA', 'JP'];

  polygonSeries.events.on('datavalidated', function () {
    am5.array.each(polygonSeries.dataItems, function (di) {
      const id = di.get('id');
      if (id && producerIds.includes(id)) {
        di.get('mapPolygon').setAll({ fill: am5.color(0x8fae7e) });
      } else if (id && hubIds.includes(id)) {
        di.get('mapPolygon').setAll({ fill: am5.color(0xc4a878) });
      } else if (id && consumerIds.includes(id)) {
        di.get('mapPolygon').setAll({ fill: am5.color(0xddc8a0) });
      }
    });
  });

  const sankeySeries = chart.series.push(am5map.MapSankeySeries.new(root, {
    polygonSeries,
    maxWidth: 2,
    controlPointDistance: 0.4,
    resolution: 60,
    nodePadding: 0.3
  }));

  sankeySeries.mapPolygons.template.setAll({
    fill: mediumRoast,
    fillOpacity: 0.65,
    strokeOpacity: 0,
    tooltipText: '{sourceNode.name} > {targetNode.name}\n{value} trail weight'
  });

  sankeySeries.nodes.mapPolygons.template.setAll({
    fill: espresso,
    stroke: crema,
    strokeWidth: 1.5,
    fillOpacity: 0.95,
    strokeOpacity: 1,
    tooltipText: '{name}\n{sum} atlas weight'
  });

  sankeySeries.bullets.push(function () {
    return am5.Bullet.new(root, {
      locationX: 0,
      autoRotate: true,
      sprite: am5.Graphics.new(root, {
        svgPath: 'M-4,-2.5 C-4,-5 -1.5,-6.5 1,-6.5 C3.5,-6.5 5,-4.5 5,-2 C5,1 3,3.5 0.5,5 C-0.5,5.7 -1.5,5.7 -2.5,5 C-5,3.5 -6,1 -4,-2.5 Z M-1,-5 C-1,-1 -1,2 -0.5,4.5',
        fill: espresso,
        stroke: darkRoast,
        strokeWidth: 0.5,
        centerX: am5.p50,
        centerY: am5.p50,
        scale: 0.35,
        visible: false
      })
    });
  });

  sankeySeries.data.setAll(atlasSankeyData(points));

  const countryNames = {
    BR: 'Brazil', VN: 'Vietnam', CO: 'Colombia', ET: 'Ethiopia',
    ID: 'Indonesia', HN: 'Honduras', DE: 'Germany', BE: 'Belgium',
    IT: 'Italy', US: 'United States / Home trails', FR: 'France', PL: 'Poland',
    SE: 'Sweden', RU: 'Russia', GB: 'United Kingdom', NL: 'Netherlands',
    GR: 'Greece', AT: 'Austria', CA: 'Canada', JP: 'Japan', MX: 'Mexico'
  };

  sankeySeries.events.on('datavalidated', function () {
    am5.array.each(sankeySeries.nodes.dataItems, function (di) {
      const id = di.get('id');
      if (id && countryNames[id]) di.set('name', countryNames[id]);
    });

    am5.array.each(sankeySeries.dataItems, function (dataItem) {
      const bullets = dataItem.bullets;
      if (bullets) {
        am5.array.each(bullets, function (bullet) {
          const randomDur = 3000 + Math.random() * 3000;
          const delay = Math.random() * randomDur;
          setTimeout(function () {
            if (root.isDisposed()) return;
            const sprite = bullet.get('sprite');
            if (sprite) sprite.set('visible', true);
            bullet.animate({
              key: 'locationX',
              from: 0,
              to: 1,
              duration: randomDur,
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
        fill: isHome ? am5.color(0x3c1e0e) : am5.color(0x8b5e3c),
        stroke: isHome ? am5.color(0xf5ece0) : am5.color(0xe8d5b7),
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
    fill: espresso,
    x: am5.p50,
    centerX: am5.p50
  }));

  titleCont.children.push(am5.Label.new(root, {
    text: '(One summary point per hike / trail / place)',
    fontSize: 11,
    fill: mediumRoast,
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
    fill: espresso,
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
      if (switchButton.get('active')) zoomToMap();
      else zoomToGlobe();
      chart.seriesContainer.animate({ key: 'opacity', to: 1, duration: fadeDuration });
    }, duration);
  });

  switchCont.children.push(am5.Label.new(root, {
    centerY: am5.p50,
    text: 'Map',
    fill: espresso,
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
  const normalizedPoints = useMemo(() => (points || []).map(safePoint).filter(Boolean), [points]);

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
      rootRef.current = createCodePenGlobe(chartRef.current, normalizedPoints);
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

  return <div className="adventure-globe-codepen-card"><div ref={chartRef} id="chartdiv" className="adventure-globe-codepen-chart" />{status !== 'ready' ? <div className="adventure-globe-codepen-status">{status}</div> : null}</div>;
}
