import { useEffect, useRef, useState } from 'react'
import mapboxgl from 'mapbox-gl'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

const STATUS_COLORS = {
  active: '#00e5ff',
  dark: '#555577',
  suspicious: '#ff3355',
}

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

export default function Map({ ships, hotzones, incidents, selectedShip, onSelectShip, editZones, zoneOverrides, onZoneChange, gfwPath, unmatchedPoints, mmsiInput, onTrackShip }) {
  const mapContainer = useRef(null)
  const map = useRef(null)
  const shipsData = useRef({})
  const incidentMarkers = useRef({})
  const resizeMarkers = useRef({})
  const isDraggingMarker = useRef(null)

  // Refs to avoid stale closures in Mapbox event handlers
  const editZonesRef = useRef(editZones)
  const zoneOverridesRef = useRef(zoneOverrides)
  const onZoneChangeRef = useRef(onZoneChange)
  const hotzonesRef = useRef(hotzones)

  useEffect(() => { editZonesRef.current = editZones }, [editZones])
  useEffect(() => { zoneOverridesRef.current = zoneOverrides }, [zoneOverrides])
  useEffect(() => { onZoneChangeRef.current = onZoneChange }, [onZoneChange])
  useEffect(() => { hotzonesRef.current = hotzones }, [hotzones])

  const [mapReady, setMapReady] = useState(false)
  const [noToken, setNoToken] = useState(false)
  const [typeFilter, setTypeFilter] = useState('all')

  // ── Init map ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!MAPBOX_TOKEN) { setNoToken(true); return }

    mapboxgl.accessToken = MAPBOX_TOKEN

    map.current = new mapboxgl.Map({
      container: mapContainer.current,
      style: 'mapbox://styles/mapbox/dark-v11',
      center: [45, 25],
      zoom: 3.5,
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
      map.current.on('mouseenter', 'ships', () => { map.current.getCanvas().style.cursor = 'pointer' })
      map.current.on('mouseleave', 'ships', () => { map.current.getCanvas().style.cursor = '' })

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
        if (editZonesRef.current) map.current.getCanvas().style.cursor = 'move'
      })
      map.current.on('mouseleave', 'hotzone-fill', () => {
        if (!dragging) map.current.getCanvas().style.cursor = ''
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
    map.current.addLayer({ id: 'hotzone-fill', type: 'fill', source: 'hotzones', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.05 } })
    map.current.addLayer({ id: 'hotzone-border', type: 'line', source: 'hotzones', paint: { 'line-color': ['get', 'color'], 'line-width': 0.8, 'line-opacity': 0.45, 'line-dasharray': [4, 3] } })
  }

  // ── Update hotzone source when data or overrides change ───────────────────
  useEffect(() => {
    if (!mapReady || !map.current) return
    const src = map.current.getSource('hotzones')
    if (!src) {
      if (Object.keys(hotzones).length === 0) return
      const features = buildHotzoneFeatures(hotzones, zoneOverrides)
      map.current.addSource('hotzones', { type: 'geojson', data: { type: 'FeatureCollection', features } })
      map.current.addLayer({ id: 'hotzone-fill', type: 'fill', source: 'hotzones', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.05 } })
      map.current.addLayer({ id: 'hotzone-border', type: 'line', source: 'hotzones', paint: { 'line-color': ['get', 'color'], 'line-width': 0.8, 'line-opacity': 0.45, 'line-dasharray': [4, 3] } })
    } else {
      src.setData({ type: 'FeatureCollection', features: buildHotzoneFeatures(hotzones, zoneOverrides) })
    }
  }, [mapReady, hotzones, zoneOverrides])

  // ── Create / destroy resize handles when edit mode toggles ────────────────
  useEffect(() => {
    if (!mapReady) return
    Object.values(resizeMarkers.current).forEach(m => m.remove())
    resizeMarkers.current = {}
    if (!editZones) return

    Object.entries(hotzones).forEach(([name, hz]) => {
      const el = document.createElement('div')
      el.style.cssText = 'width:10px;height:10px;background:white;border-radius:50%;cursor:ew-resize;border:1px solid rgba(0,0,0,0.4);box-shadow:0 0 0 1px rgba(255,255,255,0.3);'

      const geo = getZoneGeo(name, hz, zoneOverridesRef.current)
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
    })
  }, [editZones, mapReady, hotzones])

  // ── Sync resize handle positions when overrides change ────────────────────
  useEffect(() => {
    if (!mapReady || !editZones) return
    Object.entries(hotzones).forEach(([name, hz]) => {
      if (isDraggingMarker.current === name) return
      const marker = resizeMarkers.current[name]
      if (!marker) return
      const geo = getZoneGeo(name, hz, zoneOverrides)
      const edgeLon = geo.centerLon + geo.radius / Math.cos((geo.centerLat * Math.PI) / 180)
      marker.setLngLat([edgeLon, geo.centerLat])
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

      {/* Type filter bar + Track Ship */}
      <div style={styles.filterBar}>
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
        <button
          onClick={() => onTrackShip?.()}
          disabled={!mmsiInput?.trim()}
          style={{
            ...styles.filterBtn,
            marginTop: 6,
            opacity: mmsiInput?.trim() ? 1 : 0.5,
            cursor: mmsiInput?.trim() ? 'pointer' : 'not-allowed',
          }}
          title="Show 1-year path (enter MMSI first)"
        >
          TRACK SHIP
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
          <Row label="MMSI" value={selectedShip.mmsi} />
          <Row label="STATUS" value={selectedShip.status.toUpperCase()} valueColor={STATUS_COLORS[selectedShip.status]} />
          <Row label="TYPE" value={(selectedShip.type || 'unknown').toUpperCase()} />
          <Row label="POSITION" value={`${selectedShip.lat.toFixed(4)}°, ${selectedShip.lon.toFixed(4)}°`} />
          <Row label="SPEED" value={`${selectedShip.sog} kn`} />
          <Row label="COURSE" value={`${selectedShip.cog}°`} />
          {selectedShip.in_hotzone && <Row label="HOTZONE" value={selectedShip.in_hotzone} valueColor="var(--warning)" />}
        </div>
      )}

      {/* Edit mode hint */}
      {editZones && (
        <div style={styles.editHint}>
          DRAG ZONE TO MOVE &nbsp;·&nbsp; DRAG HANDLE TO RESIZE
        </div>
      )}

      {/* Legend */}
      <div style={styles.legend}>
        <LegendItem color="var(--accent)" label="Active" />
        <LegendItem color="var(--danger)" label="Suspicious" />
        <LegendItem color="#444" label="Dark" />
        <div style={{ borderTop: '1px solid var(--border)', marginTop: 8, paddingTop: 8 }}>
          <LegendItem color="var(--danger)" dashed label="Hormuz" />
          <LegendItem color="var(--warning)" dashed label="Black Sea / Red Sea" />
        </div>
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

function LegendItem({ color, label, dashed }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
      {dashed
        ? <div style={{ width: 14, height: 1, borderTop: `1px dashed ${color}`, opacity: 0.7 }} />
        : <div style={{ width: 6, height: 6, borderRadius: '50%', background: color }} />
      }
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
