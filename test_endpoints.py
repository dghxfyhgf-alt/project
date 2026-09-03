import requests
import json

# Test geocode search
print("=== Testing /geocode/search ===")
try:
    r = requests.get('http://127.0.0.1:8000/geocode/search?q=議事亭前地&limit=5', timeout=10)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    else:
        print(r.text)
except Exception as e:
    print(f'Error: {e}')

# Test reverse geocode
print("\n=== Testing /geocode/reverse ===")
try:
    r = requests.get('http://127.0.0.1:8000/geocode/reverse?lat=22.192&lon=113.539', timeout=10)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    else:
        print(r.text)
except Exception as e:
    print(f'Error: {e}')

# Test route plan
print("\n=== Testing /route/plan ===")
try:
    r = requests.post('http://127.0.0.1:8000/route/plan', json={
        'start_lat': 22.192, 'start_lon': 113.539,
        'end_lat': 22.188, 'end_lon': 113.535,
        'prefer_bus': False
    }, timeout=30)
    print(f'Status: {r.status_code}')
    if r.status_code == 200:
        data = r.json()
        print(f'Success: {data.get("success")}')
        if data.get('success'):
            props = data['geojson']['properties']
            print(f'Walk: {props["walk_distance"]}m, Bus: {props["bus_distance"]}m, Transfers: {props["num_transfers"]}')
    else:
        print(r.text)
except Exception as e:
    print(f'Error: {e}')