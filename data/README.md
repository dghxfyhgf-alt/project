# Terrain data

Place the licensed Copernicus DEM GeoTIFF for Macau in this directory as
`dem.tif`. The file is intentionally not included in Git because it is a
large external dataset and its redistribution terms must be followed.

The backend reads the file at startup and reports the result at `/health`.
You can use another path by setting the `DEM_PATH` environment variable.

The local `dem.tif` used for testing may be downloaded from NextGIS Data.
Check the accompanying dataset license before redistributing it. The current
Macau package is derived from Copernicus WorldDEM-30 and includes attribution
requirements; keep the source README and license with the downloaded data.

## Cultural places

`cultural_places.json` is a normalized snapshot of the HOT/OpenStreetMap
`cultural_places` GeoPackage. It contains representative coordinates for
points and polygons plus multilingual names, category tags, opening hours,
websites, and operators. The snapshot date is 2026-08-07 and the data is
provided under ODbL; retain OpenStreetMap attribution when redistributing it.

The backend serves this layer at `/cultural-places` without requiring AI or bus
data. `macau_boundary.geojson` is included from the accompanying NextGIS order
boundary export and is used for the inside/nearby classification. Set
`MACAU_BOUNDARY_PATH` to another official GeoJSON file if you need to replace
it.
