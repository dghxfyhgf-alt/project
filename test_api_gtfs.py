import requests
import json

# Test /route/plan with real GTFS
resp = requests.post('http://127.0.0.1:8000/route/plan', json={
    'start_lat': 22.218, 'start_lon': 113.550,
    'end_lat': 22.155, 'end_lon': 113.570,
    'prefer_bus': True, 'max_walk_km': 0
}, timeout=30)
print('=== /route/plan ===')
print(f'Status: {resp.status_code}')
data = resp.json()
print(f'Success: {data.get("success")}')
if data.get('success'):
    props = data['geojson']['properties']
    print(f'Walk: {props["walk_distance"]}m, Bus: {props["bus_distance"]}m, Transfers: {props["num_transfers"]}')

# Test /ai/parse_intent
resp2 = requests.post('http://127.0.0.1:8000/ai/parse_intent', json={
    'text': '从关闸坐公车去氹仔码头，不要走路'
}, timeout=30)
print('\n=== /ai/parse_intent ===')
print(f'Status: {resp2.status_code}')
print(json.dumps(resp2.json(), indent=2, ensure_ascii=False))