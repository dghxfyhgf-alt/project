import geopandas as gpd
import pandas as pd
import os

base_dir = r"C:\Users\ASUS\Downloads\ExportShapeFile_Extracted\ExportShapeFile20260824"

print("=" * 80)
print("BUS_POLE.SHP (Bus Stops)")
print("=" * 80)
bus_pole = gpd.read_file(os.path.join(base_dir, "BUS_POLE.shp"))
print(f"CRS: {bus_pole.crs}")
print(f"Shape: {bus_pole.shape}")
print(f"Columns: {list(bus_pole.columns)}")
print(f"\nFirst 5 rows:")
print(bus_pole.head())
print(f"\nDtypes:")
print(bus_pole.dtypes)

print("\n" + "=" * 80)
print("ROUTE_NETWORK.SHP (Route Network)")
print("=" * 80)
route_network = gpd.read_file(os.path.join(base_dir, "ROUTE_NETWORK.shp"))
print(f"CRS: {route_network.crs}")
print(f"Shape: {route_network.shape}")
print(f"Columns: {list(route_network.columns)}")
print(f"\nFirst 5 rows:")
print(route_network.head())
print(f"\nDtypes:")
print(route_network.dtypes)

print("\n" + "=" * 80)
print("BUS_ROUTE_SEQ.xls (Route Sequence)")
print("=" * 80)
bus_route_seq = pd.read_excel(os.path.join(base_dir, "BUS_ROUTE_SEQ.xls"))
print(f"Shape: {bus_route_seq.shape}")
print(f"Columns: {list(bus_route_seq.columns)}")
print(f"\nFirst 10 rows:")
print(bus_route_seq.head(10))
print(f"\nDtypes:")
print(bus_route_seq.dtypes)

# Check unique routes
if 'ROUTE_ID' in bus_route_seq.columns or 'ROUTE' in bus_route_seq.columns:
    route_col = 'ROUTE_ID' if 'ROUTE_ID' in bus_route_seq.columns else 'ROUTE'
    print(f"\nUnique routes: {bus_route_seq[route_col].nunique()}")
    print(f"Routes: {sorted(bus_route_seq[route_col].unique())}")

# Check BUS_POLE routes field
print("\n" + "=" * 80)
print("BUS_POLE - Sample routes field")
print("=" * 80)
# Find route-related columns in bus_pole
route_cols = [c for c in bus_pole.columns if 'ROUTE' in c.upper() or 'LINE' in c.upper()]
print(f"Route-related columns: {route_cols}")
for col in route_cols:
    print(f"\n{col} sample values:")
    print(bus_pole[col].head(20).tolist())

# Check ROUTE_NETWORK route ID field
print("\n" + "=" * 80)
print("ROUTE_NETWORK - Route ID field")
print("=" * 80)
route_id_cols = [c for c in route_network.columns if 'ROUTE' in c.upper() or 'ID' in c.upper()]
print(f"Route ID columns: {route_id_cols}")
for col in route_id_cols:
    print(f"\n{col} unique values (first 20):")
    print(route_network[col].unique()[:20])
    print(f"Total unique: {route_network[col].nunique()}")