import httpx
import asyncio

async def test():
    headers = {'User-Agent': 'MacauNavigation/1.0 (Windows NT 10.0; Win64; x64) +https://github.com/macau-navigation'}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get('https://nominatim.openstreetmap.org/search', 
                                params={'q': '議事亭前地, 澳門', 'format': 'json', 'limit': 3},
                                headers=headers)
        print(f'Status: {resp.status_code}')
        if resp.status_code == 200:
            for r in resp.json():
                print(f'  {r["display_name"]} ({r["lat"]}, {r["lon"]})')

asyncio.run(test())