import requests
import json

# Test /route/plan
resp = requests.post('http://127.0.0.1:8000/route/plan', json={
    'start_lat': 22.192,
    'start_lon': 113.539,
    'end_lat': 22.188,
    'end_lon': 113.535,
    'avoid_stairs': True,
    'max_slope': 15,
    'prefer_bus': False
}, timeout=30)
print('=== /route/plan ===')
print(f'Status: {resp.status_code}')
data = resp.json()
print(f'Success: {data.get("success")}')
if data.get('success'):
    props = data['geojson']['properties']
    print(f'Distance: {props["total_distance"]}m')
    print(f'Time: {props["total_time"]:.0f}s')
    print(f'Walk: {props["walk_distance"]}m, Bus: {props["bus_distance"]}m')
    print(f'Transfers: {props["num_transfers"]}')
    print(f'Features: {len(data["geojson"]["features"])}')

# Test /ai/parse_intent
resp2 = requests.post('http://127.0.0.1:8000/ai/parse_intent', json={
    'text': '我想去看地質但不想走太累，最多步行2公里'
}, timeout=30)
print('\n=== /ai/parse_intent ===')
print(f'Status: {resp2.status_code}')
print(json.dumps(resp2.json(), indent=2, ensure_ascii=False))