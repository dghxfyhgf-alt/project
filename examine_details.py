import geopandas as gpd
import pandas as pd
import os

base_dir = r"C:\Users\ASUS\Downloads\ExportShapeFile_Extracted\ExportShapeFile20260824"

# Check CRS conversion
bus_pole = gpd.read_file(os.path.join(base_dir, "BUS_POLE.shp"))
route_network = gpd.read_file(os.path.join(base_dir, "ROUTE_NETWORK.shp"))
bus_route_seq = pd.read_excel(os.path.join(base_dir, "BUS_ROUTE_SEQ.xls"))

# Convert to WGS84
bus_pole_wgs = bus_pole.to_crs(epsg=4326)
route_network_wgs = route_network.to_crs(epsg=4326)

print("BUS_POLE in WGS84:")
print(bus_pole_wgs[['POLE_ID', 'P_NAME', 'P_NAME_EN', 'ROUTE_NOS', 'geometry']].head(10))
print(f"\nBounds: {bus_pole_wgs.total_bounds}")

print("\nROUTE_NETWORK in WGS84:")
print(route_network_wgs[['NETWORK_ID', 'ROUTE_NOS', 'geometry']].head(5))
print(f"\nBounds: {route_network_wgs.total_bounds}")

# Examine route sequence details
print("\n" + "=" * 80)
print("BUS_ROUTE_SEQ - Detailed Analysis")
print("=" * 80)
print(f"Columns: {list(bus_route_seq.columns)}")
print(f"\nDIRECTION values: {bus_route_seq['DIRECTION'].unique()}")
print(f"ROUTE_NO unique count: {bus_route_seq['ROUTE_NO'].nunique()}")
print(f"ROUTE_ID unique count: {bus_route_seq['ROUTE_ID'].nunique()}")

# Sample route 1
route_1 = bus_route_seq[bus_route_seq['ROUTE_NO'] == '1'].sort_values('SEQ')
print(f"\nRoute 1 (first 20 stops):")
print(route_1[['SEQ', 'POLE_ID', 'SID', 'DIRECTION', 'NAME']].head(20))

# Check for each route, the direction values
for route_no in ['1', '1A', '10', '3', '26', '101', '102', 'AP1']:
    r = bus_route_seq[bus_route_seq['ROUTE_NO'] == route_no]
    if len(r) > 0:
        print(f"\nRoute {route_no}: {len(r)} stops, directions: {r['DIRECTION'].unique()}, seq range: {r['SEQ'].min()}-{r['SEQ'].max()}")

# Check BUS_POLE route parsing
print("\n" + "=" * 80)
print("BUS_POLE ROUTE_NOS parsing")
print("=" * 80)
bus_pole['route_list'] = bus_pole['ROUTE_NOS'].str.split(',')
print(f"Sample route lists:")
for idx, row in bus_pole.head(10).iterrows():
    print(f"  POLE_ID {row['POLE_ID']}: {row['route_list']}")

# Check ROUTE_NETWORK route parsing
print("\n" + "=" * 80)
print("ROUTE_NETWORK ROUTE_NOS parsing")
print("=" * 80)
route_network['route_list'] = route_network['ROUTE_NOS'].str.split(',')
print(f"Sample route lists:")
for idx, row in route_network.head(10).iterrows():
    print(f"  NETWORK_ID {row['NETWORK_ID']}: {row['route_list']}")

# How many unique route numbers in ROUTE_NOS across all network segments
all_routes = set()
for rl in route_network['route_list']:
    all_routes.update(rl)
print(f"\nTotal unique route numbers in ROUTE_NETWORK: {len(all_routes)}")
print(f"Routes: {sorted(all_routes)[:50]}...")

# Check ROUTE_ID mapping in BUS_ROUTE_SEQ
print("\n" + "=" * 80)
print("ROUTE_NO to ROUTE_ID mapping")
print("=" * 80)
route_mapping = bus_route_seq[['ROUTE_NO', 'ROUTE_ID']].drop_duplicates()
print(route_mapping.head(20))

# Check if BUS_POLE POLE_ID matches BUS_ROUTE_SEQ POLE_ID
print("\n" + "=" * 80)
print("POLE_ID matching")
print("=" * 80)
pole_ids_bus = set(bus_pole['POLE_ID'].unique())
pole_ids_seq = set(bus_route_seq['POLE_ID'].dropna().astype(int).unique())
print(f"BUS_POLE unique POLE_IDs: {len(pole_ids_bus)}")
print(f"BUS_ROUTE_SEQ unique POLE_IDs: {len(pole_ids_seq)}")
print(f"Intersection: {len(pole_ids_bus & pole_ids_seq)}")
print(f"In BUS_POLE but not in SEQ: {len(pole_ids_bus - pole_ids_seq)}")
print(f"In SEQ but not in BUS_POLE: {len(pole_ids_seq - pole_ids_bus)}")

# Check NETWORK_ID matching
print("\n" + "=" * 80)
print("NETWORK_ID matching")
print("=" * 80)
net_ids_route = set(route_network['NETWORK_ID'].unique())
net_ids_seq = set(bus_route_seq['NETWORK_ID'].dropna().astype(int).unique())
print(f"ROUTE_NETWORK unique NETWORK_IDs: {len(net_ids_route)}")
print(f"BUS_ROUTE_SEQ unique NETWORK_IDs: {len(net_ids_seq)}")
print(f"Intersection: {len(net_ids_route & net_ids_seq)}")