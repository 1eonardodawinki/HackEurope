# GFW Track Microservice

Standalone FastAPI service (port **8001**) that fetches a vessel's historical positions
from the Global Fishing Watch API.  
**Does not modify the main HackEurope app at all.**

## How it works

1. Resolve MMSI → GFW `vessel_id`  (1 API call to `/vessels/search`)
2. Fetch port-visit, fishing, and encounter events filtered to **that one vessel**  
   (3 API calls to `/events?vessels[0]=vessel_id`)
3. Sort chronologically, dedupe, return JSON

No regional scanning. No "all ships in area" queries.

## Start

```bash
cd track-service
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn main:app --port 8001
```

## Endpoint

```
GET http://localhost:8001/track?mmsi=229594000
GET http://localhost:8001/track?mmsi=229594000&start=2025-01-01&end=2025-07-01
```

**Response:**
```json
{
  "mmsi": "229594000",
  "name": "YM AMAZON",
  "flag": "MLT",
  "ship_type": "CARGO",
  "time_range": "2025-01-01 to 2025-07-01",
  "point_count": 24,
  "points": [
    { "lat": 38.25, "lon": 21.71, "timestamp": "2025-01-04T07:24:46.000Z" },
    ...
  ]
}
```

## Frontend integration

```js
const res = await fetch(
  `http://localhost:8001/track?mmsi=${mmsi}&start=2025-01-01&end=2025-07-01`
);
const data = await res.json();

// GeoJSON coordinates = [lon, lat]
const coords = data.points.map(p => [p.lon, p.lat]);
map.getSource('track').setData({
  type: 'FeatureCollection',
  features: [{ type: 'Feature', geometry: { type: 'LineString', coordinates: coords } }]
});
```
