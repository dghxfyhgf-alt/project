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
│   ├── graph_builder.py     # OSMnx graph construction with elevation & bus data
│   ├── router.py            # A* routing with adaptive cost functions
│   ├── test_system.py       # Integration tests
│   └── requirements.txt     # Python dependencies
├── frontend/
│   ├── pubspec.yaml         # Flutter dependencies
│   └── lib/
│       └── main.dart        # Flutter UI with map & chat interface
```

## Backend API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/route/plan` | POST | Plan route with preferences |
| `/ai/parse_intent` | POST | Parse natural language to structured params |
| `/route/update` | POST | Dynamic re-routing for GPS deviation/weather |

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
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`

## Running the Frontend

```bash
cd frontend
flutter pub get
flutter run
```

Note: The frontend connects to `http://10.0.2.2:8000` (Android emulator localhost). Change `_apiBaseUrl` in `main.dart` for other platforms.

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
cd backend
python test_system.py
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
Implement scheduled fetcher in `main.py` startup and integrate with `/route/update`