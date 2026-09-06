from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx

DATASET_ID = "67bfc5e083917d6a7fa5b8ea"
FILE_LIST_URL = "https://data.casearth.cn/api/dataset/getAllFileListBySdoId"
DOWNLOAD_URL = "https://data.casearth.cn/api/file/downloadOneFile"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "data" / "dem.tif"


def download_dem(output: Path, username: str) -> None:
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        response = client.get(FILE_LIST_URL, params={"sdoId": DATASET_ID})
        response.raise_for_status()
        payload = response.json()
        files = payload.get("data", [])
        dem_file = next((item for item in files if str(item.get("file_name", "")).lower().endswith((".tif", ".tiff"))), None)
        if dem_file is None:
            raise RuntimeError("CASEarth dataset does not contain a GeoTIFF file")

        file_id = dem_file.get("id")
        if not file_id:
            raise RuntimeError("CASEarth response did not include a file ID")
        response = client.get(
            DOWNLOAD_URL,
            params={"fileId": file_id, "username": username},
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "text" in content_type or "json" in content_type:
            raise RuntimeError(f"CASEarth returned an error instead of GeoTIFF: {response.text[:500]}")
        if len(response.content) < 1024:
            raise RuntimeError("Downloaded DEM file is unexpectedly small")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(response.content)
    print(f"Downloaded {dem_file['file_name']} ({len(response.content)} bytes) to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download the CASEarth Macau DEM GeoTIFF")
    parser.add_argument("--username", default=os.getenv("CASEARTH_USERNAME"))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.username:
        raise SystemExit("Set CASEARTH_USERNAME or pass --username with your CASEarth account.")
    download_dem(args.output, args.username)
