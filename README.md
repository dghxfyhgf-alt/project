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
| `/ai/parse_intent` | POST | Parse natural language to structured params |
| `/route/update` | POST | Dynamic re-routing for GPS deviation/weather |
| `/geocode/search` | GET | Nominatim place search proxy |
| `/geocode/reverse` | GET | Nominatim reverse geocoding proxy |
| `/bus/routes` | GET | DSAT public bus route metadata proxy |
| `/bus/stops` | GET | Local supplied bus stop names and codes |
| `/cultural-places` | GET | HOT/OpenStreetMap cultural places map layer |
| `/ai/plan_tour` | POST | Generate an LLM-assisted, confirmation-required tour plan |
| `/tour/route` | POST | Validate each confirmed multi-stop tour leg with the OSM router |

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

If `data/macau_network.graphml` is unavailable, the backend reads the PBF file
configured by `OSM_PBF_PATH` and caches it as GraphML. The Windows launcher
automatically uses `%USERPROFILE%\Downloads\macau-260904.osm.pbf` when present.
If neither file is available, the backend uses a small offline fallback graph
so that the API and frontend can still be developed and tested. Generate the
real Macau graph with:

```bash
python map_downloader.py
```

### DEM terrain support

Place a local GeoTIFF DEM at `data/dem.tif`, or set the `DEM_PATH`
environment variable to another GeoTIFF path. On startup, the backend samples
the DEM along each road edge and adds elevation gain/loss, average slope,
maximum slope, and stair metadata to the graph. OSM's `highway=steps` tag is
treated as stairs independently of DEM coverage.

Route profiles are `normal`, `avoid_stairs`, `luggage`, `stroller`, and
`wheelchair`. For example:

```json
{
  "start_lat": 22.192,
  "start_lon": 113.539,
  "end_lat": 22.188,
  "end_lon": 113.535,
  "profile": "wheelchair"
}
```

`GET /health` reports whether the configured DEM was loaded through the
`dem_loaded` field. Without a DEM, the API remains usable but does not claim
that its slope values are measured terrain values.

The recommended data flow is:

1. The CASEarth dataset `67bfc5e083917d6a7fa5b8ea` exposes `aomen.tif`
   through its file list API. The file download requires a CASEarth account.
2. Set `CASEARTH_USERNAME` or pass `--username` and run
   `python download_dem.py`; the script saves the GeoTIFF as `data/dem.tif`.
3. Run `python map_downloader.py` to create the OSM walking graph.
4. Start the API and confirm `/health` reports `dem_loaded: true`.

The downloader does not store passwords or tokens. If CASEarth requires an
authenticated browser session beyond the username parameter, download
`aomen.tif` through the portal and copy it to `data/dem.tif` instead.

OSM attributes such as `highway=steps`, `incline`, `surface`, and walking
path types are normalized before routing. DEM provides elevation and slope;
OSM remains the authoritative source for explicit stairs.

### DSAT bus data

The DSAT Macau bus website exposes route and station data through its web
client. The backend provides `/bus/routes` as a small public-data adapter.
The adapter does not bypass DSAT HUID/token checks, CAPTCHA, login, or other
access controls. If DSAT returns a non-`000` status, the API reports that the
web session is required instead of using synthetic or stale bus data.
This endpoint is route metadata only; real walking + bus routing still
requires an authorized, stable timetable/GTFS feed.

The repository can also use a normalized local snapshot in `data/bus/`.
`/bus/routes` serves `routes.json` when present, and `/bus/stops` serves
`stops.json`. The snapshot contains route directions, ordered stop codes,
stop names, and captured bus information; it is not a live timetable or
vehicle-position service. The original updater script and token material are
not copied into the repository.

### Cultural places map layer

The HOT/OpenStreetMap cultural places snapshot is available independently at
`GET /cultural-places`. The Flutter map displays cultural place markers and
details for Chinese, English, Portuguese, category, opening hours, website,
operator, and inside-Macau/nearby status. This feature does not require AI or
bus data. The bundled Macau boundary is used for the area classification. The
snapshot is licensed under ODbL; see `data/README.md`.

### AI tour planning

`POST /ai/plan_tour` accepts a natural-language purpose such as
`我想看历史建筑和美食，下午有六小时`. When configured, it calls an
OpenAI-compatible chat-completions endpoint and asks the model to select only
IDs from the approved Macau POI catalog. Coordinates and route geometry never
come from the model: the backend resolves IDs, applies Pydantic validation, and
the confirmation step validates every leg with the OSM route engine. If the
provider is unavailable, the deterministic local planner is used and the
response includes a warning.

Configure a provider with environment variables (the API key is never returned
by the backend):

```powershell
$env:LLM_API_KEY = "your-api-key"
$env:LLM_BASE_URL = "https://api.openai.com/v1" # or another compatible endpoint
$env:LLM_MODEL = "gpt-4o-mini"
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The provider must support JSON output via `response_format.type=json_object`.
`LLM_TIMEOUT_SECONDS` optionally controls the request timeout (default 20
seconds).

### Routing algorithm

The route engine uses a bidirectional genetic search. A bidirectional graph
search first creates a valid seed path from both endpoints; the genetic phase
then evolves valid path chromosomes using terrain-aware fitness, crossover at
shared nodes, and mutation through alternative graph edges. Invalid paths,
stairs, and slopes that violate the selected profile are rejected. This
replaces the previous direct NetworkX shortest-path call while preserving
deterministic results through a fixed random seed.

Route requests are projected to the nearest walkable OSM road edge before
searching, rather than being reduced directly to the nearest graph node.
Disconnected OSM components are reduced to the largest walkable component at
load time. If no connected path exists, the API returns a specific
connectivity error instead of a misleading zero-length route.

### One-click desktop test (Windows)

Double-click `run_desktop_test.bat` in the repository root. It starts the
backend, waits for `/health`, and opens the Flutter Windows desktop app. The
script can generate the Flutter Windows runner if it is missing. Python,
Flutter, and Visual Studio C++ desktop tooling must be installed.

After the first build, the launcher opens the existing Release executable
without running `flutter pub get` or rebuilding it. It also reuses an already
healthy backend instead of starting a duplicate process.

The Flutter API URL is configurable with `API_BASE_URL`. Desktop uses
`http://127.0.0.1:8000`; Android Emulator should use
`http://10.0.2.2:8000`.

### Terrain visualization

The Flutter map provides an in-app terrain overlay rendered from the local
DEM through `GET /terrain/overlay.png`. It does not require QGIS to be
installed. The overlay can be toggled from the map controls and does not
upload DEM data.

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
Implement scheduled fetcher in `main.py` startup and integrate with `/route/update`