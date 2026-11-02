"""Validate and register a manually exported Earth Engine NDVI GeoTIFF."""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import Window
from affine import Affine

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_tif", help="Downloaded two-band GeoTIFF from the Code Editor export")
    args = parser.parse_args()
    source = Path(args.input_tif).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    grid = json.loads((ROOT / "data/raw/national/india_reference_grid.json").read_text())
    shape = tuple(grid["shape"])
    transform = rasterio.Affine(*grid["transform"])
    boundary = gpd.read_file(ROOT / "data/raw/boundaries/india_soi_outline.geojson").to_crs(grid["crs"])
    print("Checking downloaded raster and India boundary...", flush=True)
    with rasterio.open(source) as src:
        acceptable_shapes = {shape, (shape[0], shape[1] + 1)}
        if src.count != 2 or src.shape not in acceptable_shapes or src.crs is None or src.crs.to_epsg() != 4326:
            raise ValueError(f"Expected a two-band EPSG:4326 raster with shape {shape} (or one extra eastern edge column); found {src.count} bands, shape {src.shape}, CRS {src.crs}")
        if not src.transform.almost_equals(transform):
            raise ValueError(f"Raster transform does not match the model grid: {src.transform}")
    output_dir = ROOT / "data/raw/ndvi"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / "India_S2_mean_NDVI_2025_Annual_DIRECT_1KM.tif"
    profile = dict(driver="GTiff", width=shape[1], height=shape[0], count=2, dtype="float32",
        crs=grid["crs"], transform=transform, nodata=-9999, compress="deflate", tiled=True,
        blockxsize=256, blockysize=256)
    inside_count = 0
    valid_count = 0
    chunk_rows = 256
    print("Masking and writing India grid in small blocks...", flush=True)
    with rasterio.open(output, "w", **profile) as dst:
        dst.set_band_description(1, "Sentinel-2 NDVI mean, annual 2025, evaluated at 30 arc-seconds")
        dst.set_band_description(2, "Contributing granules, not independent dates")
        dst.update_tags(source="COPERNICUS/S2_SR_HARMONIZED", start_date="2025-01-01", end_date_exclusive="2026-01-01")
        with rasterio.open(source) as src:
            for row in range(0, shape[0], chunk_rows):
                height = min(chunk_rows, shape[0] - row)
                window = Window(col_off=0, row_off=row, width=shape[1], height=height)
                data = src.read(window=window, masked=True).filled(np.nan).astype("float32")
                data[data == -9999] = np.nan
                block_transform = transform * Affine.translation(0, row)
                inside = geometry_mask(boundary.geometry, out_shape=(height, shape[1]),
                    transform=block_transform, invert=True)
                finite = np.isfinite(data).all(axis=0)
                valid = inside & finite & (data[0] >= -1) & (data[0] <= 1) & (data[1] >= 3)
                inside_count += int(inside.sum())
                valid_count += int(valid.sum())
                data[0, ~valid] = -9999
                data[1, ~inside] = -9999
                data[:, ~finite] = -9999
                dst.write(data, window=window)
                print(f"Processed rows {row + height}/{shape[0]}", flush=True)
    if valid_count == 0:
        output.unlink(missing_ok=True)
        raise ValueError("The exported image contains no valid NDVI cells with at least three granules")
    digest_builder = hashlib.sha256()
    with output.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest_builder.update(chunk)
    digest = digest_builder.hexdigest()
    metadata = dict(complete_region=True, start_date="2025-01-01", end_date_exclusive="2026-01-01",
        collection="COPERNICUS/S2_SR_HARMONIZED", grid=grid, mosaic_sha256=digest,
        minimum_granules=3, cloud_mask="GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED cs_cdf >= 0.6",
        processing_method="Code Editor export: per-granule NDVI evaluated at requested 30-arcsecond scale, then annual temporal mean",
        coverage_percent=float(100 * valid_count / inside_count), downloaded_utc=datetime.now(timezone.utc).isoformat())
    output.with_suffix(".provenance.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(json.dumps({"stage":"COMPLETED", "file":str(output), "coverage_percent":metadata["coverage_percent"]}, indent=2))

if __name__ == "__main__":
    main()
