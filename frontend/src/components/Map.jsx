import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

const STATUS_COLORS = {
  active: '#00e5ff',
  dark: '#555577',
  suspicious: '#ff3355',
}

const SUSPICIOUS_PORTS = [
  // Russian oil export ports
  { name: 'Novorossiysk', lat: 44.7167, lon: 37.7833, category: 'russian' },
  { name: 'Primorsk', lat: 60.3667, lon: 28.6333, category: 'russian' },
  { name: 'Ust-Luga', lat: 59.6833, lon: 28.4000, category: 'russian' },
  { name: 'Kozmino', lat: 42.7833, lon: 133.0500, category: 'russian' },
  { name: 'Murmansk', lat: 68.9667, lon: 33.0500, category: 'russian' },
  { name: 'Vladivostok', lat: 43.1167, lon: 131.9000, category: 'russian' },
  // Iranian sanctioned ports
  { name: 'Kharg Island', lat: 29.2333, lon: 50.3167, category: 'iranian' },
  { name: 'Bandar Abbas', lat: 27.1833, lon: 56.2833, category: 'iranian' },
  { name: 'Bandar Imam Khomeini', lat: 30.4333, lon: 49.0667, category: 'iranian' },
  // Venezuelan sanctioned ports
  { name: 'Jose Terminal', lat: 10.2000, lon: -64.7167, category: 'venezuelan' },
  { name: 'Puerto La Cruz', lat: 10.2167, lon: -64.6333, category: 'venezuelan' },
  { name: 'Amuay Bay', lat: 11.7500, lon: -70.2167, category: 'venezuelan' },
  // North Korean sanctioned ports
  { name: 'Nampo', lat: 38.7333, lon: 125.4000, category: 'northkorean' },
  { name: 'Wonsan', lat: 39.1500, lon: 127.4500, category: 'northkorean' },
  { name: 'Chongjin', lat: 41.7833, lon: 129.8167, category: 'northkorean' },
]

const STS_ZONES = [
  { name: 'Ceuta', lat: 35.8900, lon: -5.3000, radiusKm: 50 },
  { name: 'Kalamata', lat: 36.9500, lon: 22.1100, radiusKm: 50 },
  { name: 'Laconia', lat: 36.5000, lon: 22.9000, radiusKm: 50 },
  { name: 'Cape Town STS', lat: -34.0000, lon: 18.0000, radiusKm: 100 },
  { name: 'Johor STS', lat: 1.3000, lon: 104.1000, radiusKm: 50 },
  { name: 'Fujairah STS', lat: 25.1200, lon: 56.3300, radiusKm: 50 },
  { name: 'Singapore STS', lat: 1.2000, lon: 103.8000, radiusKm: 50 },
  { name: 'Lomé STS', lat: 6.1333, lon: 1.2500, radiusKm: 50 },
]

function circlePolygon(lon, lat, radius, n = 64) {
  const coords = []
  for (let i = 0; i <= n; i++) {
    const angle = (i / n) * 2 * Math.PI
    coords.push([
      lon + (radius * Math.cos(angle)) / Math.cos((lat * Math.PI) / 180),
      lat + radius * Math.sin(angle),
    ])
  }
  return [coords]
}

function getZoneGeo(name, hz, overrides) {
  const ov = overrides?.[name]
  if (ov) return ov
  return {
    centerLon: (hz.min_lon + hz.max_lon) / 2,
    centerLat: (hz.min_lat + hz.max_lat) / 2,
    radius: Math.max((hz.max_lon - hz.min_lon) / 2, (hz.max_lat - hz.min_lat) / 2),
  }
}

function buildHotzoneFeatures(hotzones, overrides) {
  return Object.entries(hotzones).map(([name, hz]) => {
    const geo = getZoneGeo(name, hz, overrides)
    return {
      type: 'Feature',
      properties: { name, color: hz.color },
      geometry: { type: 'Polygon', coordinates: circlePolygon(geo.centerLon, geo.centerLat, geo.radius) },
    }
  })
}

export default function Map({ ships, hotzones, incidents, selectedShip, onSelectShip, editZones, zoneOverrides, onZoneChange, onDeleteZone, onAddZone, gfwPath, unmatchedPoints, onTrackByMmsi, demoMode, connected, onSwitchMode, onToggleEditZones, mobilePanelOpen, onToggleMobilePanel }) {
  const mapContainer = useRef(null)
  const map = useRef(null)
  const shipsData = useRef({})
  const incidentMarkers = useRef({})
  const resizeMarkers = useRef({})
  const deleteMarkers = useRef({})
  const isDraggingMarker = useRef(null)

  // Refs to avoid stale closures in Mapbox event handlers
  const editZonesRef = useRef(editZones)
  const zoneOverridesRef = useRef(zoneOverrides)
  const onZoneChangeRef = useRef(onZoneChange)
  const hotzonesRef = useRef(hotzones)
  const addingZoneRef = useRef(false)
  const onAddZoneRef = useRef(onAddZone)

  useEffect(() => { editZonesRef.current = editZones }, [editZones])
  useEffect(() => { zoneOverridesRef.current = zoneOverrides }, [zoneOverrides])
  useEffect(() => { onZoneChangeRef.current = onZoneChange }, [onZoneChange])
  useEffect(() => { hotzonesRef.current = hotzones }, [hotzones])
  useEffect(() => { onAddZoneRef.current = onAddZone }, [onAddZone])

  const [mapReady, setMapReady] = useState(false)
  const [noToken, setNoToken] = useState(false)
  const [typeFilter, setTypeFilter] = useState('all')
  const [addingZone, setAddingZone] = useState(false)
  const [legendExpanded, setLegendExpanded] = useState(false)
  const [filterOpen, setFilterOpen] = useState(false)
  const [typeExpanded, setTypeExpanded] = useState(false)
  useEffect(() => { addingZoneRef.current = addingZone }, [addingZone])

  // ── Cursor when adding zone ───────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !map.current) return
    map.current.getCanvas().style.cursor = addingZone ? 'crosshair' : ''
  }, [addingZone, mapReady])

  // ── Init map ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!MAPBOX_TOKEN) { setNoToken(true); return }

    mapboxgl.accessToken = MAPBOX_TOKEN

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: [45, 25],
      zoom: 2.2,
      projection: 'globe',
      attributionControl: false,
    })

    map.current.on('load', () => {
      map.current.setFog({
        color: 'rgb(4, 10, 26)',
        'high-color': 'rgb(8, 20, 50)',
        'horizon-blend': 0.02,
        'star-intensity': 0.8,
      })

      addHotzoneLayers()

      // ── STS (Ship-to-Ship) Transfer Zones ──
      const stsFeatures = STS_ZONES.map(z => ({
        type: 'Feature',
        properties: { name: z.name },
        geometry: { type: 'Polygon', coordinates: circlePolygon(z.lon, z.lat, z.radiusKm / 111) },
      }))
      map.current.addSource('sts-zones', { type: 'geojson', data: { type: 'FeatureCollection', features: stsFeatures } })
      map.current.addLayer({ id: 'sts-zones-fill', type: 'fill', source: 'sts-zones', paint: { 'fill-color': '#a855f7', 'fill-opacity': 0.07 } })
      map.current.addLayer({ id: 'sts-zones-border', type: 'line', source: 'sts-zones', paint: { 'line-color': '#a855f7', 'line-width': 1.2, 'line-opacity': 0.65, 'line-dasharray': [3, 4] } })
      map.current.addLayer({
        id: 'sts-zones-label', type: 'symbol', source: 'sts-zones',
        layout: { 'text-field': ['get', 'name'], 'text-size': 9, 'text-anchor': 'center', 'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'] },
        paint: { 'text-color': 'rgba(168,85,247,0.8)', 'text-halo-color': '#000', 'text-halo-width': 1 },
      })

      // ── Suspicious / Sanctioned Ports ──
      const portFeatures = SUSPICIOUS_PORTS.map(p => ({
        type: 'Feature',
        properties: { name: p.name, category: p.category, label: p.name },
        geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      }))
      map.current.addSource('suspicious-ports', { type: 'geojson', data: { type: 'FeatureCollection', features: portFeatures } })
      map.current.addLayer({
        id: 'suspicious-ports-dot', type: 'circle', source: 'suspicious-ports',
        paint: {
          'circle-radius': 5,
          'circle-color': ['match', ['get', 'category'], 'russian', '#f59e0b', 'iranian', '#ff3355', 'venezuelan', '#f97316', 'northkorean', '#ef4444', '#ff3355'],
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#000',
          'circle-opacity': 0.9,
        },
      })
      map.current.addLayer({
        id: 'suspicious-ports-label', type: 'symbol', source: 'suspicious-ports',
        layout: { 'text-field': ['get', 'name'], 'text-size': 9, 'text-offset': [0, 1.2], 'text-anchor': 'top', 'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'] },
        paint: { 'text-color': 'rgba(255,255,255,0.75)', 'text-halo-color': '#000', 'text-halo-width': 1.5 },
      })

      // ── Ship trail layer ──
      map.current.addSource('ship-trails', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.current.addLayer({
        id: 'ship-trails',
        type: 'line',
        source: 'ship-trails',
        paint: { 'line-color': ['get', 'color'], 'line-width': 1.5, 'line-opacity': 0.5 },
      })

      // ── GFW 1-year path (investigated vessel) ──
      map.current.addSource('gfw-path', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.current.addLayer({
        id: 'gfw-path',
        type: 'line',
        source: 'gfw-path',
        paint: { 'line-color': '#00e5ff', 'line-width': 2, 'line-opacity': 0.7 },
      })

      // ── Historical unmatched detections for investigated MMSI ──
      map.current.addSource('unmatched-points', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.current.addLayer({
        id: 'unmatched-points',
        type: 'circle',
        source: 'unmatched-points',
        paint: {
          'circle-radius': 2.5,
          'circle-color': '#ff9500',
          'circle-opacity': 0.75,
          'circle-stroke-width': 0.6,
          'circle-stroke-color': '#1a1a1a',
          'circle-stroke-opacity': 0.8,
        },
      })

      // ── Dark event markers (last known position before going dark) ──
      map.current.addSource('dark-events', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.current.addLayer({
        id: 'dark-events-ring',
        type: 'circle',
        source: 'dark-events',
        paint: {
          'circle-radius': 7,
          'circle-color': 'transparent',
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ff3355',
          'circle-stroke-opacity': 0.85,
          'circle-opacity': 0,
        },
      })
      map.current.addLayer({
        id: 'dark-events-dot',
        type: 'circle',
        source: 'dark-events',
        paint: {
          'circle-radius': 3,
          'circle-color': '#ff3355',
          'circle-opacity': 0.9,
          'circle-stroke-width': 0,
        },
      })

      // ── Ship arrow icon ──
      const sz = 24
      const cv = document.createElement('canvas')
      cv.width = sz; cv.height = sz
      const cx = cv.getContext('2d')
      cx.fillStyle = 'white'
      cx.beginPath()
      cx.moveTo(sz / 2, 1)
      cx.lineTo(sz - 3, sz - 3)
      cx.lineTo(sz / 2, sz * 0.62)
      cx.lineTo(3, sz - 3)
      cx.closePath()
      cx.fill()
      map.current.addImage('ship-arrow', cx.getImageData(0, 0, sz, sz), { sdf: true })

      // ── Ship positions ──
      map.current.addSource('ships', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.current.addLayer({
        id: 'ships-selected',
        type: 'circle',
        source: 'ships',
        filter: ['==', ['get', 'mmsi'], -1],
        paint: {
          'circle-radius': 10,
          'circle-color': 'transparent',
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-opacity': 0.7,
        },
      })
      map.current.addLayer({
        id: 'ships',
        type: 'symbol',
        source: 'ships',
        layout: {
          'icon-image': 'ship-arrow',
          'icon-rotate': ['get', 'cog'],
          'icon-rotation-alignment': 'map',
          'icon-allow-overlap': true,
          'icon-ignore-placement': true,
          'icon-size': 0.7,
        },
        paint: {
          'icon-color': ['match', ['get', 'status'], 'suspicious', '#ff3355', 'dark', '#444444', '#ffffff'],
          'icon-opacity': ['match', ['get', 'status'], 'dark', 0.35, 1.0],
        },
      })

      map.current.on('click', 'ships', (e) => {
        if (e.features.length > 0) {
          const mmsi = e.features[0].properties.mmsi
          onSelectShip(shipsData.current[mmsi] || null)
        }
      })
      map.current.on('mouseenter', 'ships', () => {
        if (addingZoneRef.current) return
        map.current.getCanvas().style.cursor = 'pointer'
      })
      map.current.on('mouseleave', 'ships', () => {
        if (addingZoneRef.current) return
        map.current.getCanvas().style.cursor = ''
      })

      // ── Zone drag-to-move ──
      let dragging = null

      map.current.on('mousedown', 'hotzone-fill', (e) => {
        if (!editZonesRef.current) return
        e.preventDefault()
        map.current.dragPan.disable()
        const name = e.features[0].properties.name
        const hz = hotzonesRef.current[name]
        if (!hz) return
        const geo = getZoneGeo(name, hz, zoneOverridesRef.current)
        dragging = { name, startLng: e.lngLat.lng, startLat: e.lngLat.lat, startCenter: { ...geo } }
      })

      map.current.on('mousemove', (e) => {
        if (!dragging) return
        onZoneChangeRef.current(dragging.name, {
          centerLon: dragging.startCenter.centerLon + (e.lngLat.lng - dragging.startLng),
          centerLat: dragging.startCenter.centerLat + (e.lngLat.lat - dragging.startLat),
          radius: dragging.startCenter.radius,
        })
      })

      map.current.on('mouseup', () => {
        if (dragging) { dragging = null; map.current.dragPan.enable() }
      })

      map.current.on('mouseenter', 'hotzone-fill', () => {
        if (addingZoneRef.current) return
        if (editZonesRef.current) map.current.getCanvas().style.cursor = 'move'
      })
      map.current.on('mouseleave', 'hotzone-fill', () => {
        if (addingZoneRef.current) return
        if (!dragging) map.current.getCanvas().style.cursor = ''
      })

      // ── Click to place new zone ──
      map.current.on('click', (e) => {
        if (!addingZoneRef.current) return
        onAddZoneRef.current?.({ centerLon: e.lngLat.lng, centerLat: e.lngLat.lat })
        addingZoneRef.current = false
        setAddingZone(false)
      })

      setMapReady(true)
    })

    return () => {
      Object.values(incidentMarkers.current).forEach(m => m.remove())
      Object.values(resizeMarkers.current).forEach(m => m.remove())
      map.current?.remove()
    }
  }, [])

  function addHotzoneLayers() {
    const features = buildHotzoneFeatures(hotzonesRef.current, zoneOverridesRef.current)
    if (features.length === 0) return
    map.current.addSource('hotzones', { type: 'geojson', data: { type: 'FeatureCollection', features } })
    map.current.addLayer({ id: 'hotzone-fill', type: 'fill', source: 'hotzones', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.08 } })
    map.current.addLayer({ id: 'hotzone-border', type: 'line', source: 'hotzones', paint: { 'line-color': ['get', 'color'], 'line-width': 1.5, 'line-opacity': 0.7, 'line-dasharray': [4, 3] } })
  }

  // ── Update hotzone source when data or overrides change ───────────────────
  useEffect(() => {
    if (!mapReady || !map.current) return
    const src = map.current.getSource('hotzones')
    if (!src) {
      if (Object.keys(hotzones).length === 0) return
      const features = buildHotzoneFeatures(hotzones, zoneOverrides)
      map.current.addSource('hotzones', { type: 'geojson', data: { type: 'FeatureCollection', features } })
      map.current.addLayer({ id: 'hotzone-fill', type: 'fill', source: 'hotzones', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.08 } })
      map.current.addLayer({ id: 'hotzone-border', type: 'line', source: 'hotzones', paint: { 'line-color': ['get', 'color'], 'line-width': 1.5, 'line-opacity': 0.7, 'line-dasharray': [4, 3] } })
    } else {
      src.setData({ type: 'FeatureCollection', features: buildHotzoneFeatures(hotzones, zoneOverrides) })
    }
  }, [mapReady, hotzones, zoneOverrides])

  // ── Create / destroy resize + delete handles when edit mode toggles ────────
  useEffect(() => {
    if (!mapReady) return
    Object.values(resizeMarkers.current).forEach(m => m.remove())
    Object.values(deleteMarkers.current).forEach(m => m.remove())
    resizeMarkers.current = {}
    deleteMarkers.current = {}
    if (!editZones) return

    Object.entries(hotzones).forEach(([name, hz]) => {
      const geo = getZoneGeo(name, hz, zoneOverridesRef.current)

      // Resize handle
      const el = document.createElement('div')
      el.style.cssText = 'width:10px;height:10px;background:white;border-radius:50%;cursor:ew-resize;border:1px solid rgba(0,0,0,0.4);box-shadow:0 0 0 1px rgba(255,255,255,0.3);'
      const edgeLon = geo.centerLon + geo.radius / Math.cos((geo.centerLat * Math.PI) / 180)
      const marker = new mapboxgl.Marker({ element: el, draggable: true })
        .setLngLat([edgeLon, geo.centerLat])
        .addTo(map.current)
      marker.on('dragstart', () => { isDraggingMarker.current = name })
      marker.on('drag', () => {
        const lngLat = marker.getLngLat()
        const cur = getZoneGeo(name, hotzonesRef.current[name], zoneOverridesRef.current)
        const newRadius = Math.max(0.5, Math.abs(lngLat.lng - cur.centerLon) * Math.cos((cur.centerLat * Math.PI) / 180))
        onZoneChangeRef.current(name, { ...cur, radius: newRadius })
      })
      marker.on('dragend', () => { isDraggingMarker.current = null })
      resizeMarkers.current[name] = marker

      // Delete button
      const delEl = document.createElement('div')
      delEl.textContent = '✕'
      delEl.style.cssText = 'width:18px;height:18px;background:#ff3355;color:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:10px;font-weight:700;line-height:18px;text-align:center;box-shadow:0 0 0 1px rgba(255,255,255,0.2);user-select:none;'
      delEl.onclick = () => onDeleteZone?.(name)
      const delMarker = new mapboxgl.Marker({ element: delEl, anchor: 'center' })
        .setLngLat([geo.centerLon, geo.centerLat])
        .addTo(map.current)
      deleteMarkers.current[name] = delMarker
    })
  }, [editZones, mapReady, hotzones, onDeleteZone])

  // ── Sync resize + delete handle positions when overrides change ───────────
  useEffect(() => {
    if (!mapReady || !editZones) return
    Object.entries(hotzones).forEach(([name, hz]) => {
      if (isDraggingMarker.current === name) return
      const geo = getZoneGeo(name, hz, zoneOverrides)
      const resizeMarker = resizeMarkers.current[name]
      if (resizeMarker) {
        const edgeLon = geo.centerLon + geo.radius / Math.cos((geo.centerLat * Math.PI) / 180)
        resizeMarker.setLngLat([edgeLon, geo.centerLat])
      }
      const delMarker = deleteMarkers.current[name]
      if (delMarker) delMarker.setLngLat([geo.centerLon, geo.centerLat])
    })
  }, [zoneOverrides, editZones, mapReady, hotzones])

  // ── Update ship positions + trails ────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !map.current) return
    ships.forEach(s => { shipsData.current[s.mmsi] = s })

    const visibleShips = typeFilter === 'all' ? ships
      : ships.filter(s => s.type === typeFilter)

    const shipFeatures = visibleShips.map(ship => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [ship.lon, ship.lat] },
      properties: { mmsi: ship.mmsi, name: ship.name, status: ship.status, in_hotzone: ship.in_hotzone, cog: ship.cog ?? 0 },
    }))

    const trailFeatures = visibleShips
      .filter(s => s.trail && s.trail.length > 1)
      .map(ship => ({
        type: 'Feature',
        properties: { color: ship.status === 'dark' ? '#333' : ship.status === 'suspicious' ? '#ff3355' : 'rgba(255,255,255,0.25)' },
        geometry: { type: 'LineString', coordinates: ship.trail },
      }))

    if (map.current.getSource('ships')) {
      map.current.getSource('ships').setData({ type: 'FeatureCollection', features: shipFeatures })
    }
    if (map.current.getSource('ship-trails')) {
      map.current.getSource('ship-trails').setData({ type: 'FeatureCollection', features: trailFeatures })
    }
  }, [ships, mapReady, typeFilter])

  // ── Dark event rings — SAR detections for the selected MMSI (no AIS match) ──
  useEffect(() => {
    if (!mapReady || !map.current) return
    const src = map.current.getSource('dark-events')
    if (!src) return
    if (!unmatchedPoints?.points?.length || unmatchedPoints.error) {
      src.setData({ type: 'FeatureCollection', features: [] })
      return
    }
    const features = unmatchedPoints.points
      .filter(p => Number.isFinite(Number(p.lon)) && Number.isFinite(Number(p.lat)))
      .map(p => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [Number(p.lon), Number(p.lat)] },
        properties: { timestamp: p.timestamp || '' },
      }))
    src.setData({ type: 'FeatureCollection', features })
  }, [unmatchedPoints, mapReady])

  // ── Update GFW 1-year path ────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !map.current) return
    const src = map.current.getSource('gfw-path')
    if (!src) return

    if (!gfwPath?.path?.length || gfwPath.error) {
      src.setData({ type: 'FeatureCollection', features: [] })
      return
    }

    // Use path_segments when available (avoids drawing across large voyage gaps)
    const segments = gfwPath.path_segments || [gfwPath.path]
    const features = segments
      .filter((seg) => seg && seg.length >= 2)
      .map((seg) => ({
        type: 'Feature',
        properties: {},
        geometry: {
          type: 'LineString',
          coordinates: seg.map((p) => [p.lon, p.lat]),
        },
      }))
    src.setData({ type: 'FeatureCollection', features })

    const allCoords = gfwPath.path.map((p) => [p.lon, p.lat])
    if (allCoords.length >= 2) {
      const bbox = [
        [Math.min(...allCoords.map((c) => c[0])), Math.min(...allCoords.map((c) => c[1]))],
        [Math.max(...allCoords.map((c) => c[0])), Math.max(...allCoords.map((c) => c[1]))],
      ]
      map.current.fitBounds(bbox, { padding: 80, maxZoom: 8, duration: 1200 })
    }
  }, [gfwPath, mapReady])

  // ── Update unmatched historical points ────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !map.current) return
    const src = map.current.getSource('unmatched-points')
    if (!src) return

    if (!unmatchedPoints?.points?.length || unmatchedPoints.error) {
      src.setData({ type: 'FeatureCollection', features: [] })
      return
    }

    const features = unmatchedPoints.points
      .filter((p) => Number.isFinite(Number(p.lon)) && Number.isFinite(Number(p.lat)))
      .map((p) => ({
        type: 'Feature',
        properties: {
          timestamp: p.timestamp || '',
        },
        geometry: {
          type: 'Point',
          coordinates: [Number(p.lon), Number(p.lat)],
        },
      }))

    src.setData({ type: 'FeatureCollection', features })
  }, [unmatchedPoints, mapReady])

  // ── Update selection ring ─────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !map.current) return
    if (map.current.getLayer('ships-selected')) {
      map.current.setFilter('ships-selected', ['==', ['get', 'mmsi'], selectedShip?.mmsi ?? -1])
    }
  }, [selectedShip, mapReady])

  // ── Update incident markers ───────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !map.current) return

    const activeIds = new Set(incidents.map(i => i.id))
    for (const id of Object.keys(incidentMarkers.current)) {
      if (!activeIds.has(id)) { incidentMarkers.current[id].remove(); delete incidentMarkers.current[id] }
    }

    incidents.forEach(incident => {
      if (incidentMarkers.current[incident.id]) return
      const el = document.createElement('div')
      el.className = `incident-marker ${incident.severity === 'high' ? 'high' : ''}`
      el.title = `Incident: ${incident.type}`

      const popup = new mapboxgl.Popup({ offset: 14, closeButton: false })
        .setHTML(`
          <div style="font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif;font-size:11px;color:#fff;background:#080808;padding:10px 12px;border:1px solid rgba(255,255,255,0.1);min-width:180px">
            <div style="font-size:9px;letter-spacing:2px;color:${incident.severity === 'high' ? '#ff3355' : '#ff9500'};font-weight:600;margin-bottom:6px">
              ${incident.type === 'ais_dropout' ? 'AIS DROPOUT' : 'SHIP PROXIMITY'}
            </div>
            <div style="font-weight:500;margin-bottom:4px">${incident.ship_name || 'Unknown'}</div>
            <div style="color:#666;font-size:10px">${incident.region}</div>
            ${incident.confidence_score ? `<div style="color:#aaa;font-size:10px;margin-top:2px">Confidence: ${incident.confidence_score}%</div>` : ''}
            ${incident.duration_minutes ? `<div style="color:#666;font-size:10px">Duration: ${incident.duration_minutes}m</div>` : ''}
          </div>
        `)

      const marker = new mapboxgl.Marker({ element: el, anchor: 'center' })
        .setLngLat([incident.lon, incident.lat])
        .setPopup(popup)
        .addTo(map.current)

      incidentMarkers.current[incident.id] = marker
    })
  }, [incidents, mapReady])

  // ── Fly to selected ship ──────────────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !selectedShip || !map.current) return
    const currentZoom = map.current.getZoom()
    map.current.flyTo({ center: [selectedShip.lon, selectedShip.lat], zoom: Math.max(currentZoom, 7), duration: 1200 })
  }, [selectedShip, mapReady])

  if (noToken) {
    return (
      <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 16, background: 'var(--bg)' }}>
        <div style={{ color: 'var(--warning)', fontSize: 14, fontWeight: 600 }}>No Mapbox Token</div>
        <div style={{ color: 'var(--text2)', fontSize: 12, textAlign: 'center', maxWidth: 340, lineHeight: 1.6 }}>
          Add <code style={{ color: 'var(--accent)' }}>VITE_MAPBOX_TOKEN=your_token</code> to
          <code style={{ color: 'var(--accent)' }}> frontend/.env</code>.
        </div>
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />

      {/* Type filter bar — desktop only */}
      <div style={styles.filterBar} className="map-desktop-only">
        <div style={{ display: 'flex', gap: 4 }}>
          {['all', 'tanker', 'cargo', 'fishing'].map(t => (
            <button key={t} onClick={() => setTypeFilter(t)} style={{
              ...styles.filterBtn,
              ...(typeFilter === t ? styles.filterBtnActive : {}),
            }}>
              {t.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      {/* ── Mobile overlays ─────────────────────────────────────────── */}

      {/* Mobile: Demo / Live toggle — top-left */}
      <div className="map-mobile-only" style={{ position: 'absolute', top: 16, left: 16, zIndex: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8,
          background: 'rgba(8,8,8,0.9)', backdropFilter: 'blur(10px)',
          border: '1px solid rgba(255,255,255,0.1)', padding: '6px 12px' }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
            background: !connected ? 'var(--danger)' : demoMode ? 'var(--danger)' : 'var(--green)',
            animation: 'pulse-dot 2s infinite' }} />
          <span style={{ fontSize: 10, color: 'var(--text3)', letterSpacing: 1.5 }}>
            {!connected ? 'OFFLINE' : demoMode ? 'DEMO' : 'LIVE'}
          </span>
          {connected && onSwitchMode && (
            <button onClick={() => onSwitchMode(!demoMode)} style={{
              background: 'transparent', border: '1px solid rgba(255,255,255,0.2)',
              color: 'var(--text3)', fontSize: 9, letterSpacing: 1.5, fontFamily: 'inherit',
              padding: '2px 8px', cursor: 'pointer',
            }}>
              {demoMode ? 'LIVE' : 'DEMO'}
            </button>
          )}
        </div>
      </div>

      {/* Mobile: FILTER + panel toggle — top-right */}
      <div className="map-mobile-only" style={{ position: 'absolute', top: 16, right: 16, zIndex: 300, display: 'flex', alignItems: 'flex-start', gap: 6 }}>
        {/* FILTER with dropdown */}
        <div style={{ position: 'relative' }}>
          <button onClick={() => { setFilterOpen(v => !v); if (filterOpen) setTypeExpanded(false) }}
            style={{ ...styles.filterBtn, ...( filterOpen ? styles.filterBtnActive : {}), display: 'flex', alignItems: 'center', gap: 6 }}>
            FILTER <span style={{ fontSize: 8 }}>{filterOpen ? '▲' : '▼'}</span>
          </button>
          {filterOpen && (
            <div style={{ position: 'absolute', top: '100%', right: 0, marginTop: 2,
              background: 'rgba(8,8,8,0.97)', backdropFilter: 'blur(12px)',
              border: '1px solid rgba(255,255,255,0.1)', minWidth: 130,
              display: 'flex', flexDirection: 'column' }}>
              {/* TYPE row */}
              <button onClick={() => setTypeExpanded(v => !v)} style={{
                background: 'transparent', border: 'none', borderBottom: '1px solid rgba(255,255,255,0.06)',
                color: typeExpanded ? 'var(--text)' : 'var(--text3)', fontSize: 9, letterSpacing: 2,
                fontFamily: 'inherit', padding: '10px 14px', cursor: 'pointer',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              }}>
                TYPE <span style={{ fontSize: 8 }}>{typeExpanded ? '▲' : '▶'}</span>
              </button>
              {typeExpanded && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3, padding: '8px 10px',
                  borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                  {['all', 'tanker', 'cargo', 'fishing'].map(t => (
                    <button key={t} onClick={() => setTypeFilter(t)} style={{
                      ...styles.filterBtn, padding: '4px 9px',
                      ...(typeFilter === t ? styles.filterBtnActive : {}),
                    }}>
                      {t.toUpperCase()}
                    </button>
                  ))}
                </div>
              )}
              {/* EDIT ZONES row */}
              <button onClick={() => { onToggleEditZones?.(); setFilterOpen(false) }} style={{
                background: editZones ? 'rgba(255,255,255,0.05)' : 'transparent',
                border: 'none', color: editZones ? 'var(--text)' : 'var(--text3)',
                fontSize: 9, letterSpacing: 2, fontFamily: 'inherit',
                padding: '10px 14px', cursor: 'pointer', textAlign: 'left',
              }}>
                {editZones ? '✓ ' : ''}EDIT ZONES
              </button>
            </div>
          )}
        </div>
        {/* ≡ Panel toggle */}
        <button
          onClick={onToggleMobilePanel}
          style={{ ...styles.filterBtn, ...(mobilePanelOpen ? styles.filterBtnActive : {}),
            width: 36, display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 18, padding: '4px 0', letterSpacing: 0 }}>
          ≡
        </button>
      </div>

      {/* Ship tooltip */}
      {selectedShip && (
        <div style={styles.shipTooltip} className="animate-sweep-in">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
            <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text)' }}>{selectedShip.name}</span>
            <span style={{ color: 'var(--text3)', cursor: 'pointer', fontSize: 12, lineHeight: 1 }}
              onClick={() => onSelectShip(null)}>✕</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
            <span style={{ color: 'var(--text3)', fontSize: 9, letterSpacing: 1.5 }}>MMSI</span>
            <span
              onClick={() => onTrackByMmsi?.(selectedShip.mmsi)}
              style={{ color: 'var(--accent)', fontSize: 10, cursor: 'pointer', textDecoration: 'underline', textDecorationStyle: 'dotted' }}
              title="Click to track this vessel"
            >{selectedShip.mmsi}</span>
          </div>
          <Row label="STATUS" value={selectedShip.status.toUpperCase()} valueColor={STATUS_COLORS[selectedShip.status]} />
          <Row label="TYPE" value={(selectedShip.type || 'unknown').toUpperCase()} />
          <Row label="POSITION" value={`${selectedShip.lat.toFixed(4)}°, ${selectedShip.lon.toFixed(4)}°`} />
          <Row label="SPEED" value={`${selectedShip.sog} kn`} />
          <Row label="COURSE" value={`${selectedShip.cog}°`} />
          {selectedShip.in_hotzone && <Row label="HOTZONE" value={selectedShip.in_hotzone} valueColor="var(--warning)" />}
          <button
            onClick={() => onTrackByMmsi?.(selectedShip.mmsi)}
            style={{
              marginTop: 10, width: '100%',
              background: '#fff', color: '#000', border: 'none',
              fontSize: 9, letterSpacing: 2, fontWeight: 700, fontFamily: 'inherit',
              padding: '6px 0', cursor: 'pointer',
            }}
          >
            TRACK SHIP
          </button>
        </div>
      )}

      {/* Edit mode hint + add zone button */}
      {editZones && (
        <div style={{ ...styles.editHint, display: 'flex', alignItems: 'center', gap: 16 }}>
          <span>DRAG TO MOVE &nbsp;·&nbsp; HANDLE TO RESIZE</span>
          <button
            onClick={() => {
              const next = !addingZone
              addingZoneRef.current = next
              setAddingZone(next)
              if (map.current) map.current.getCanvas().style.cursor = next ? 'crosshair' : ''
            }}
            style={{
              background: addingZone ? '#fff' : 'transparent',
              color: addingZone ? '#000' : 'var(--text3)',
              border: '1px solid',
              borderColor: addingZone ? '#fff' : 'rgba(255,255,255,0.3)',
              fontSize: 9, letterSpacing: 2, fontFamily: 'inherit', fontWeight: 600,
              padding: '3px 10px', cursor: 'pointer', transition: 'all 0.15s',
            }}
          >
            {addingZone ? 'CLICK MAP TO PLACE' : '+ ADD ZONE'}
          </button>
        </div>
      )}

      {/* Legend — desktop */}
      <div style={styles.legend} className="map-desktop-only">
        <LegendItem arrow color="#fff" label="Live Position" />
        <LegendItem line color="#4a9eff" label="Activity within last 12 months" />
        <LegendItem ring color="var(--danger)" label="Historically went dark" />
        <LegendItem dashed color="#ff6b00" label="High Risk Areas" />
        <LegendItem dashed color="#a855f7" label="STS Transfer Zones" />
        <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', margin: '6px 0 4px' }} />
        <LegendItem dot color="#f59e0b" label="Russian Oil Ports" />
        <LegendItem dot color="#ff3355" label="Iranian / NK Ports" />
        <LegendItem dot color="#f97316" label="Venezuelan Ports" />
      </div>

      {/* Legend — mobile (collapsible) */}
      <div className="map-mobile-only" style={{ position: 'absolute', bottom: 24, left: 16, zIndex: 10,
        background: 'rgba(8,8,8,0.9)', backdropFilter: 'blur(10px)',
        border: '1px solid rgba(255,255,255,0.08)' }}>
        <button onClick={() => setLegendExpanded(v => !v)} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          gap: 20, width: '100%', padding: '8px 12px',
          background: 'none', border: 'none', color: 'var(--text3)',
          fontSize: 9, letterSpacing: 2, fontFamily: 'inherit', cursor: 'pointer',
        }}>
          LEGEND <span style={{ fontSize: 8 }}>{legendExpanded ? '▲' : '▼'}</span>
        </button>
        {legendExpanded && (
          <div style={{ padding: '2px 12px 10px' }}>
            <LegendItem arrow color="#fff" label="Live Position" />
            <LegendItem line color="#4a9eff" label="Activity within last 12 months" />
            <LegendItem ring color="var(--danger)" label="Historically went dark" />
            <LegendItem dashed color="#ff6b00" label="High Risk Areas" />
            <LegendItem dashed color="#a855f7" label="STS Transfer Zones" />
            <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', margin: '6px 0 4px' }} />
            <LegendItem dot color="#f59e0b" label="Russian Oil Ports" />
            <LegendItem dot color="#ff3355" label="Iranian / NK Ports" />
            <LegendItem dot color="#f97316" label="Venezuelan Ports" />
          </div>
        )}
      </div>
    </div>
  )
}

function Row({ label, value, valueColor }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
      <span style={{ color: 'var(--text3)', fontSize: 9, letterSpacing: 1.5 }}>{label}</span>
      <span style={{ color: valueColor || 'var(--text2)', fontSize: 10 }}>{value}</span>
    </div>
  )
}

function LegendItem({ color, label, ring, arrow, line, dashed, dot }) {
  let icon
  if (arrow) {
    icon = (
      <svg width="10" height="10" viewBox="0 0 24 24" style={{ flexShrink: 0 }}>
        <polygon points="12,1 21,21 12,14.88 3,21" fill={color} transform="rotate(90, 12, 12)" />
      </svg>
    )
  } else if (dashed) {
    icon = <div style={{ width: 14, height: 1, borderTop: `2px dashed ${color}`, opacity: 0.85, flexShrink: 0 }} />
  } else if (line) {
    icon = <div style={{ width: 14, height: 2, background: color, borderRadius: 1 }} />
  } else if (ring) {
    icon = (
      <div style={{ width: 10, height: 10, borderRadius: '50%', border: `1.5px solid ${color}`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ width: 3, height: 3, borderRadius: '50%', background: color }} />
      </div>
    )
  } else if (dot) {
    icon = <div style={{ width: 8, height: 8, borderRadius: '50%', background: color, border: '1.5px solid #000', flexShrink: 0 }} />
  } else {
    icon = <div style={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
      {icon}
      <span style={{ fontSize: 9, color: 'var(--text3)', letterSpacing: 0.5 }}>{label}</span>
    </div>
  )
}

const styles = {
  filterBar: {
    position: 'absolute', top: 16, right: 16,
    display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0, zIndex: 10,
  },
  filterBtn: {
    padding: '5px 10px',
    background: 'rgba(8,8,8,0.9)', backdropFilter: 'blur(10px)',
    border: '1px solid rgba(255,255,255,0.08)',
    color: 'var(--text3)', fontSize: 9, letterSpacing: 1.5,
    cursor: 'pointer', fontFamily: 'inherit',
    transition: 'color 0.15s, border-color 0.15s',
  },
  filterBtnActive: {
    color: 'var(--text)', borderColor: 'rgba(255,255,255,0.3)',
  },
  shipTooltip: {
    position: 'absolute', top: 50, left: 16,
    background: 'rgba(8,8,8,0.95)', backdropFilter: 'blur(12px)',
    border: '1px solid rgba(255,255,255,0.1)', padding: '12px 14px',
    minWidth: 210, zIndex: 10,
  },
  editHint: {
    position: 'absolute', top: 16, left: '50%', transform: 'translateX(-50%)',
    background: 'rgba(8,8,8,0.9)', border: '1px solid rgba(255,255,255,0.12)',
    padding: '6px 14px', fontSize: 9, color: 'var(--text3)', letterSpacing: 2,
    zIndex: 10, pointerEvents: 'none',
  },
  legend: {
    position: 'absolute', bottom: 32, left: 16,
    background: 'rgba(8,8,8,0.9)', backdropFilter: 'blur(10px)',
    border: '1px solid rgba(255,255,255,0.08)', padding: '10px 14px',
    zIndex: 10,
  },
}
