# Macau Adaptive Travel Navigation System

A Python (FastAPI) + Flutter adaptive travel navigation system for Macau with:
- Natural language intent parsing (Qwen3 API compatible)
- Multi-modal routing (walking + bus)
- Terrain & stairs avoidance
- Dynamic re-routing based on GPS deviation & weather

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI application with REST endpoints
│   ├── graph_builder.py     # OSMnx graph loading and offline fallback graph
│   ├── router.py            # Adaptive shortest-path routing
│   ├── test_system.py       # Backend smoke tests
│   └── requirements.txt     # Backend dependencies
├── frontend/
│   ├── pubspec.yaml         # Flutter dependencies
│   └── lib/main.dart        # Flutter map, route and chat interface
```

## Backend API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/route/plan` | POST | Plan route with preferences |
| `/weather/current` | GET | Current SMG weather and rain/bus recommendation |
| `/ai/parse_intent` | POST | Parse natural language to structured params |
| `/route/update` | POST | Dynamic re-routing for GPS deviation/weather |
| `/geocode/search` | GET | Nominatim place search proxy |
| `/geocode/reverse` | GET | Nominatim reverse geocoding proxy |

### Route Plan Request
```json
{
  "start_lat": 22.192,
  "start_lon": 113.539,
  "end_lat": 22.188,
  "end_lon": 113.535,
  "avoid_stairs": true,
  "max_slope": 15,
  "max_walk_km": 2.0,
  "prefer_bus": false,
  "wheelchair": false
}
```

### Intent Parsing Request
```json
{
  "text": "我想看地質但不想爬坡"
}
```

Response:
```json
{
  "tags": ["geology"],
  "avoid_stairs": true,
  "max_slope": 10,
  "max_walk_km": null,
  "prefer_bus": false,
  "wheelchair": false,
  "poi_category": "geology"
}
```

## Running the Backend

```bash
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`. The supported entry
points are `uvicorn main:app` from the repository root and
`uvicorn backend.main:app` from the repository root.

### Weather and rain-aware routing

Weather is read from the official Macau Meteorological and Geophysical Bureau
(SMG) XML feeds: current conditions from
`https://xml.smg.gov.mo/p_actual_brief.xml` and forecasts from
`https://xml.smg.gov.mo/p_forecast.xml`. `GET /weather/current` returns
`available`, `raining`, `rain_forecast`, and a human-readable
`recommendation`. When rain is observed or forecast, route planning includes
the same recommendation in `weather` and
`geojson.properties.weather_recommendation`: **do not walk; take the bus
instead**. The app does not silently change the user's bus preference, and
unavailable or dry weather leaves existing route behavior unchanged. Invalid
XML, timeouts, and feed failures return an unavailable weather result rather
than failing route planning.

If `data/macau_network.graphml` is unavailable, the backend automatically uses
a small offline fallback graph so that the API and frontend can still be
developed and tested. Generate the real Macau graph with:

```bash
python map_downloader.py
```

## Running the Frontend

```bash
cd frontend
flutter pub get
flutter run -d windows
```

The repository includes the generated `frontend/windows` desktop runner. On
Windows, double-click `start_backend.bat` to check the Flutter/Visual Studio
desktop prerequisites, start the backend in a separate console, and launch
`flutter run -d windows`. The launcher reports the exact missing prerequisite
if Flutter is not on `PATH`, no Windows Flutter device is available, or Python
is unavailable. A Windows Flutter device requires Visual Studio's **Desktop
development with C++** workload and a Windows SDK; verify with `flutter
doctor -v`.

The frontend uses `http://10.0.2.2:8000` for Android emulator localhost and
`http://127.0.0.1:8000` for Windows and other desktop targets.

## Key Features Implemented

### Phase 1: Data & Graph Foundation ✓
- OSMnx downloads Macau road network (30k+ nodes, 87k+ edges)
- Synthetic DEM elevation data with slope calculation
- Synthetic bus routes (10 stops, 5 routes)
- Multi-modal graph with transfer penalties

### Phase 2: Core Routing API ✓
- A* algorithm with customizable cost functions
- Stairs avoidance (slope > 20% or highway=steps)
- Max slope constraint
- Wheelchair accessible mode (max 8% slope)
- Bus preference with transfer penalty
- GeoJSON output with walk/bus segments

### Phase 3: LLM Intent Parsing ✓
- Keyword-based parsing (Qwen3 Function Calling compatible)
- Supports: avoid stairs, wheelchair, bus preference, max walk distance, slope limits
- POI category detection (geology, history, food, shopping, nature)

### Phase 4: Dynamic Re-routing & Flutter UI ✓
- `/route/update` endpoint for GPS deviation & weather alerts
- Flutter map with `flutter_map` & OpenStreetMap tiles
- Chat interface with suggestion chips
- Real-time route display with markers

## Testing

```bash
python -m pytest backend
```

## Configuration

- Macau bounding box: (22.25, 22.05, 113.65, 113.45)
- Default walking speed: 5 km/h
- Default bus speed: 25 km/h
- Transfer penalty: 300 seconds
- Graph cached in `data/cache/`

## Extending

### Add Real DEM Data
Place GeoTIFF in `data/dem.tif` and update `load_dem_data()` in `graph_builder.py`

### Add Real Bus Data
Replace `_generate_synthetic_bus_data()` with GTFS parser

### Integrate Qwen3 API
Replace `parse_user_intent()` in `main.py` with actual Qwen3 Function Calling

### Add Weather/Crowd Data
The SMG weather integration lives in `backend/weather.py`; extend its parser
and keep feed failures non-fatal when adding other official data sources.

## Releases

There is currently no checked-in GitHub Actions release workflow. Releases use
the existing semantic version tags (latest `v1.2.0`) and GitHub CLI:

```bash
git tag v1.3.0
git push origin v1.3.0
gh release create v1.3.0 --generate-notes
```