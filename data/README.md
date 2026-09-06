# Terrain data

Place the licensed Copernicus DEM GeoTIFF for Macau in this directory as
`dem.tif`. The file is intentionally not included in Git because it is a
large external dataset and its redistribution terms must be followed.

The backend reads the file at startup and reports the result at `/health`.
You can use another path by setting the `DEM_PATH` environment variable.
