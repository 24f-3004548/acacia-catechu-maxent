"""Download 2025 annual Sentinel-2 NDVI tiles on the India 30-arc-second grid.

Requires Google Earth Engine authentication (`earthengine authenticate`) and a
cloud project with Earth Engine access. Tiles keep each direct download modest.
"""
import hashlib, json, time, os
from datetime import datetime, timezone
from pathlib import Path
import ee, geopandas as gpd, numpy as np, rasterio, requests
from rasterio.windows import Window, bounds as window_bounds, transform as window_transform
from rasterio.features import geometry_mask

ROOT = Path(__file__).resolve().parents[1]
grid = json.loads((ROOT / "data/raw/national/india_reference_grid.json").read_text())
shape = tuple(grid["shape"]); base_transform = rasterio.Affine(*grid["transform"])
project = os.environ.get("EARTHENGINE_PROJECT")
if not project: raise SystemExit("Set EARTHENGINE_PROJECT to your own Earth Engine-enabled Google Cloud project ID.")
ee.Initialize(project=project); ee.data.setDeadline(600000)
CLEAR_THRESHOLD = 0.6
country = gpd.read_file(ROOT / "data/raw/boundaries/india_soi_outline.geojson").to_crs(4326)
region = ee.Geometry.Rectangle(grid["bounds"], proj="EPSG:4326", geodesic=False)
collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region)
    .filterDate("2025-01-01", "2026-01-01").select(["B4", "B8"])
    .linkCollection(ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"), ["cs_cdf"]))
def ndvi(image):
    clear=image.select("cs_cdf").gte(CLEAR_THRESHOLD)
    red,nir=image.select("B4"),image.select("B8")
    value=nir.subtract(red).divide(nir.add(red)).rename("NDVI")
    return value.updateMask(clear).updateMask(nir.add(red).gt(0))
values=collection.map(ndvi)
count=values.count().rename("valid_granules")
image=values.mean().rename("NDVI_mean_2025_Annual").updateMask(count.gte(3)).addBands(count).toFloat().unmask(-9999)
folder=ROOT/"data/raw/ndvi"; folder.mkdir(parents=True,exist_ok=True)
output=folder/"India_S2_mean_NDVI_2025_Annual_DIRECT_1KM.tif"
status=ROOT/"data/interim/india_ndvi_download_status.json"
status.parent.mkdir(parents=True, exist_ok=True)
width,height=shape[1],shape[0]; tile_size=512
profile=dict(driver="GTiff",width=width,height=height,count=2,dtype="float32",crs=grid["crs"],
    transform=base_transform,nodata=-9999,compress="deflate",tiled=True)
tmp=output.with_suffix(".partial.tif")
with rasterio.open(tmp,"w",**profile) as dst:
    dst.set_band_description(1,"Sentinel-2 NDVI mean, annual 2025, evaluated at 30 arc-seconds")
    dst.set_band_description(2,"Contributing granules, not independent dates")
    for row in range(0,height,tile_size):
      for col in range(0,width,tile_size):
        h=min(tile_size,height-row); w=min(tile_size,width-col); win=Window(col,row,w,h)
        tile_transform=window_transform(win,base_transform); left,bottom,right,top=window_bounds(win,base_transform)
        rect=ee.Geometry.Rectangle([left,bottom,right,top],proj="EPSG:4326",geodesic=False)
        url=image.getDownloadURL({"region":rect,"crs":grid["crs"],"crs_transform":list(tile_transform)[:6],"format":"GEO_TIFF"})
        response=requests.get(url,timeout=900); response.raise_for_status()
        tile_path=folder/"_tile_download.tif"; tile_path.write_bytes(response.content)
        with rasterio.open(tile_path) as src:
          if src.shape != (h,w) or src.count != 2: raise ValueError(f"Unexpected EE tile shape/bands at {row},{col}: {src.shape}/{src.count}")
          dst.write(src.read(1),1,window=win); dst.write(src.read(2),2,window=win)
        tile_path.unlink(); time.sleep(0.25)
        status.write_text(json.dumps({"stage":"downloading","completed_tiles":(row//tile_size)*(int(np.ceil(width/tile_size)))+col//tile_size+1,"grid_shape":shape,"updated_utc":datetime.now(timezone.utc).isoformat()},indent=2)+"\n")
# Apply official boundary mask and validate coverage.
with rasterio.open(tmp,"r+") as dst:
    a=dst.read(masked=True).filled(np.nan)
    inside=geometry_mask(country.geometry,out_shape=shape,transform=base_transform,invert=True)
    valid=inside & np.isfinite(a).all(axis=0) & (a[0]>=-1) & (a[0]<=1) & (a[1]>=3)
    if not valid.any(): raise ValueError("No valid NDVI cells returned")
    a[0,~valid]=-9999; a[1,~inside]=-9999; a[:,~np.isfinite(a).all(axis=0)]=-9999
    dst.write(a.astype("float32"))
checksum=hashlib.sha256(tmp.read_bytes()).hexdigest()
provenance={"complete_region":True,"start_date":"2025-01-01","end_date_exclusive":"2026-01-01",
 "collection":"COPERNICUS/S2_SR_HARMONIZED","grid":grid,"mosaic_sha256":checksum,
 "minimum_granules":3,"cloud_mask":f"GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED cs_cdf >= {CLEAR_THRESHOLD}",
 "processing_method":"per-granule NDVI evaluated at requested 30-arcsecond scale, then calendar-year mean; tiled Earth Engine download",
 "coverage_percent":float(100*valid.sum()/inside.sum()),"downloaded_utc":datetime.now(timezone.utc).isoformat()}
output.with_suffix(".provenance.json").write_text(json.dumps(provenance,indent=2)+"\n")
tmp.replace(output)
status.write_text(json.dumps({"stage":"COMPLETED","file":str(output),"coverage_percent":provenance["coverage_percent"]},indent=2)+"\n")
print(json.dumps({"file":str(output),"coverage_percent":provenance["coverage_percent"]},indent=2))
