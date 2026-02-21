import { useEffect, useRef, useState, useCallback } from 'react'
import mapboxgl from 'mapbox-gl'

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN || ''

const STATUS_COLORS = {
  active: '#00e5ff',
  dark: '#555577',
  suspicious: '#ff3355',
}

export default function Map({ ships, hotzones, incidents, selectedShip, onSelectShip }) {
  const mapContainer = useRef(null)
  const map = useRef(null)
  const shipsData = useRef({})        // mmsi → full ship object (for click lookup)
  const incidentMarkers = useRef({})  // id → mapboxgl.Marker
  const [mapReady, setMapReady] = useState(false)
  const [noToken, setNoToken] = useState(false)

  // ── Init map ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!MAPBOX_TOKEN) {
      setNoToken(true)
      return
    }

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
      // ── Atmosphere / globe style ──
      map.current.setFog({
        color: 'rgb(4, 10, 26)',
        'high-color': 'rgb(8, 20, 50)',
        'horizon-blend': 0.02,
        'star-intensity': 0.8,
      })

      // ── Hotzone polygons ──
      addHotzoneLayers()

      // ── Ship trail layer (GeoJSON lines) ──
      map.current.addSource('ship-trails', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })
      map.current.addLayer({
        id: 'ship-trails',
        type: 'line',
        source: 'ship-trails',
        paint: {
          'line-color': ['get', 'color'],
          'line-width': 1.5,
          'line-opacity': 0.5,
        },
      })

      // ── Ship positions (native GL circle layer — always geo-anchored) ──
      map.current.addSource('ships', {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      // Outer glow ring
      map.current.addLayer({
        id: 'ships-glow',
        type: 'circle',
        source: 'ships',
        filter: ['!=', ['get', 'status'], 'dark'],
        paint: {
          'circle-radius': 10,
          'circle-color': 'transparent',
          'circle-stroke-width': 1,
          'circle-stroke-color': [
            'match', ['get', 'status'],
            'suspicious', '#ff3355',
            '#00e5ff',
          ],
          'circle-stroke-opacity': 0.3,
        },
      })

      // Main ship dot
      map.current.addLayer({
        id: 'ships',
        type: 'circle',
        source: 'ships',
        paint: {
          'circle-radius': 5,
          'circle-color': [
            'match', ['get', 'status'],
            'active', '#00e5ff',
            'dark', '#555577',
            'suspicious', '#ff3355',
            '#00e5ff',
          ],
          'circle-opacity': ['match', ['get', 'status'], 'dark', 0.5, 1.0],
          'circle-stroke-width': 1,
          'circle-stroke-color': [
            'match', ['get', 'status'],
            'active', 'rgba(0,229,255,0.5)',
            'suspicious', 'rgba(255,51,85,0.5)',
            'transparent',
          ],
        },
      })

      // Selection ring (filtered to selected ship via setFilter)
      map.current.addLayer({
        id: 'ships-selected',
        type: 'circle',
        source: 'ships',
        filter: ['==', ['get', 'mmsi'], -1],
        paint: {
          'circle-radius': 9,
          'circle-color': 'transparent',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#ffffff',
          'circle-stroke-opacity': 0.9,
        },
      })

      // Click to select ship
      map.current.on('click', 'ships', (e) => {
        if (e.features.length > 0) {
          const mmsi = e.features[0].properties.mmsi
          onSelectShip(shipsData.current[mmsi] || null)
        }
      })
      map.current.on('mouseenter', 'ships', () => {
        map.current.getCanvas().style.cursor = 'pointer'
      })
      map.current.on('mouseleave', 'ships', () => {
        map.current.getCanvas().style.cursor = ''
      })

      setMapReady(true)
    })

    return () => {
      Object.values(incidentMarkers.current).forEach(m => m.remove())
      map.current?.remove()
    }
  }, [])

  function addHotzoneLayers() {
    const features = Object.entries(hotzones).map(([name, hz]) => ({
      type: 'Feature',
      properties: { name, color: hz.color },
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [hz.min_lon, hz.min_lat],
          [hz.max_lon, hz.min_lat],
          [hz.max_lon, hz.max_lat],
          [hz.min_lon, hz.max_lat],
          [hz.min_lon, hz.min_lat],
        ]],
      },
    }))

    if (features.length === 0) return

    map.current.addSource('hotzones', {
      type: 'geojson',
      data: { type: 'FeatureCollection', features },
    })
    map.current.addLayer({
      id: 'hotzone-fill',
      type: 'fill',
      source: 'hotzones',
      paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.08 },
    })
    map.current.addLayer({
      id: 'hotzone-border',
      type: 'line',
      source: 'hotzones',
      paint: {
        'line-color': ['get', 'color'],
        'line-width': 1.5,
        'line-opacity': 0.6,
        'line-dasharray': [4, 3],
      },
    })
  }

  // ── Update hotzones when data arrives ─────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !map.current || Object.keys(hotzones).length === 0) return
    if (map.current.getSource('hotzones')) return  // already added

    const features = Object.entries(hotzones).map(([name, hz]) => ({
      type: 'Feature',
      properties: { name, color: hz.color },
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [hz.min_lon, hz.min_lat],
          [hz.max_lon, hz.min_lat],
          [hz.max_lon, hz.max_lat],
          [hz.min_lon, hz.max_lat],
          [hz.min_lon, hz.min_lat],
        ]],
      },
    }))

    map.current.addSource('hotzones', { type: 'geojson', data: { type: 'FeatureCollection', features } })
    map.current.addLayer({ id: 'hotzone-fill', type: 'fill', source: 'hotzones', paint: { 'fill-color': ['get', 'color'], 'fill-opacity': 0.08 } })
    map.current.addLayer({ id: 'hotzone-border', type: 'line', source: 'hotzones', paint: { 'line-color': ['get', 'color'], 'line-width': 1.5, 'line-opacity': 0.6, 'line-dasharray': [4, 3] } })
  }, [mapReady, hotzones])

  // ── Update ship positions + trails ────────────────────────────────────────
  useEffect(() => {
    if (!mapReady || !map.current) return

    // Keep full ship data for click lookup
    ships.forEach(s => { shipsData.current[s.mmsi] = s })

    const shipFeatures = ships.map(ship => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [ship.lon, ship.lat] },
      properties: {
        mmsi: ship.mmsi,
        name: ship.name,
        status: ship.status,
        in_hotzone: ship.in_hotzone,
      },
    }))

    const trailFeatures = ships
      .filter(s => s.trail && s.trail.length > 1)
      .map(ship => ({
        type: 'Feature',
        properties: { color: ship.status === 'dark' ? '#444' : (STATUS_COLORS[ship.status] || STATUS_COLORS.active) },
        geometry: { type: 'LineString', coordinates: ship.trail },
      }))

    if (map.current.getSource('ships')) {
      map.current.getSource('ships').setData({ type: 'FeatureCollection', features: shipFeatures })
    }
    if (map.current.getSource('ship-trails')) {
      map.current.getSource('ship-trails').setData({ type: 'FeatureCollection', features: trailFeatures })
    }
  }, [ships, mapReady])

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
      if (!activeIds.has(id)) {
        incidentMarkers.current[id].remove()
        delete incidentMarkers.current[id]
      }
    }

    incidents.forEach(incident => {
      if (incidentMarkers.current[incident.id]) return

      const el = document.createElement('div')
      el.className = `incident-marker ${incident.severity === 'high' ? 'high' : ''}`
      el.title = `Incident: ${incident.type}`

      const popup = new mapboxgl.Popup({ offset: 15, closeButton: false })
        .setHTML(`
          <div style="font-family:monospace;font-size:11px;color:#c8ddf0;background:#0c1526;padding:8px;border:1px solid #1a2f52;border-radius:4px;min-width:180px">
            <div style="color:${incident.severity === 'high' ? '#ff3355' : '#ff9500'};font-weight:bold;margin-bottom:4px">
              ⚠ ${incident.type === 'ais_dropout' ? 'AIS DROPOUT' : 'SHIP PROXIMITY'}
            </div>
            <div><b>${incident.ship_name || 'Unknown'}</b></div>
            <div style="color:#7a99bb">Region: ${incident.region}</div>
            ${incident.confidence_score ? `<div style="color:#00e5ff">Confidence: ${incident.confidence_score}%</div>` : ''}
            ${incident.duration_minutes ? `<div>Duration: ${incident.duration_minutes}m</div>` : ''}
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
    map.current.flyTo({ center: [selectedShip.lon, selectedShip.lat], zoom: 7, duration: 1200 })
  }, [selectedShip, mapReady])

  if (noToken) {
    return (
      <div style={{ width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 16, background: 'var(--bg)' }}>
        <div style={{ fontSize: 32 }}>🗺️</div>
        <div style={{ color: 'var(--warning)', fontSize: 14, fontWeight: 600 }}>No Mapbox Token</div>
        <div style={{ color: 'var(--text2)', fontSize: 12, textAlign: 'center', maxWidth: 340, lineHeight: 1.6 }}>
          Add <code style={{ color: 'var(--accent)' }}>VITE_MAPBOX_TOKEN=your_token</code> to
          <code style={{ color: 'var(--accent)' }}> frontend/.env</code>.<br />
          Get a free token at <span style={{ color: 'var(--accent2)' }}>mapbox.com</span>
        </div>
      </div>
    )
  }

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div ref={mapContainer} style={{ width: '100%', height: '100%' }} />

      {/* Ship tooltip overlay */}
      {selectedShip && (
        <div style={styles.shipTooltip} className="animate-sweep-in">
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
            <span style={{ color: 'var(--accent)', fontWeight: 700 }}>{selectedShip.name}</span>
            <span style={{ color: 'var(--text3)', cursor: 'pointer', fontSize: 14 }}
              onClick={() => onSelectShip(null)}>✕</span>
          </div>
          <Row label="MMSI" value={selectedShip.mmsi} />
          <Row label="Status" value={selectedShip.status.toUpperCase()}
            valueColor={STATUS_COLORS[selectedShip.status]} />
          <Row label="Position" value={`${selectedShip.lat.toFixed(4)}°N, ${selectedShip.lon.toFixed(4)}°E`} />
          <Row label="Speed" value={`${selectedShip.sog} kn`} />
          <Row label="Course" value={`${selectedShip.cog}°`} />
          {selectedShip.in_hotzone && (
            <Row label="Hotzone" value={selectedShip.in_hotzone} valueColor="var(--warning)" />
          )}
        </div>
      )}

      {/* Map legend */}
      <div style={styles.legend}>
        <LegendItem color="var(--accent)" label="Active vessel" />
        <LegendItem color="var(--danger)" label="Suspicious / proximity" />
        <LegendItem color="#555577" label="Dark (AIS off)" />
        <div style={{ borderTop: '1px solid var(--border)', marginTop: 6, paddingTop: 6 }}>
          <LegendItem color="var(--danger)" dashed label="Strait of Hormuz" />
          <LegendItem color="var(--warning)" dashed label="Black Sea / Red Sea" />
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, valueColor }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
      <span style={{ color: 'var(--text3)', fontSize: 10 }}>{label}</span>
      <span style={{ color: valueColor || 'var(--text)', fontSize: 11 }}>{value}</span>
    </div>
  )
}

function LegendItem({ color, label, dashed }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 4 }}>
      {dashed
        ? <div style={{ width: 16, height: 2, borderTop: `2px dashed ${color}` }} />
        : <div style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
      }
      <span style={{ fontSize: 10, color: 'var(--text2)' }}>{label}</span>
    </div>
  )
}

const styles = {
  shipTooltip: {
    position: 'absolute', top: 16, left: 16,
    background: 'rgba(7,13,26,0.92)', backdropFilter: 'blur(8px)',
    border: '1px solid var(--border2)', borderRadius: 6, padding: 12,
    minWidth: 220, zIndex: 10,
  },
  legend: {
    position: 'absolute', bottom: 32, left: 16,
    background: 'rgba(7,13,26,0.85)', backdropFilter: 'blur(6px)',
    border: '1px solid var(--border)', borderRadius: 6, padding: '10px 14px',
    zIndex: 10,
  },
}
