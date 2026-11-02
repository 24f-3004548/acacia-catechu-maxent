"""Validate the India-wide seasonal Sentinel-2 raster and provenance."""
import hashlib, json
from pathlib import Path
import rasterio

def assemble_seasonal(root):
    root=Path(root)
    path=root/"data/raw/ndvi/India_S2_mean_NDVI_2025_Annual_DIRECT_1KM.tif"
    if not path.is_file(): return {"available":False,"reason":"Run scripts/download_direct_seasonal.py first."}
    grid=json.loads((root/"data/raw/national/india_reference_grid.json").read_text())
    sidecar=path.with_suffix(".provenance.json")
    if not sidecar.is_file(): raise ValueError("NDVI provenance sidecar is missing")
    meta=json.loads(sidecar.read_text())
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if not (meta.get("complete_region") and meta.get("grid")==grid and meta.get("mosaic_sha256")==digest):
        raise ValueError("India NDVI grid/provenance/checksum mismatch")
    with rasterio.open(path) as src:
        if src.count!=2 or src.shape!=tuple(grid["shape"]) or src.crs.to_epsg()!=4326 or not src.transform.almost_equals(rasterio.Affine(*grid["transform"])):
            raise ValueError("India NDVI raster does not match the reference grid")
    return {"available":True,"path":str(path),"coverage_percent":meta["coverage_percent"],"processing_method":meta["processing_method"],"mode":"direct_tiled_grid"}
