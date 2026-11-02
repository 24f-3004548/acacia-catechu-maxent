// Manual Sentinel-2 NDVI export for the Acacia catechu India model.
// Paste into https://code.earthengine.google.com, select your registered
// Earth Engine Cloud project, click Run, then start the task under Tasks.

var bounds = [68.17499999999998, 6.75, 97.41666666666669, 37.09166666666667];
var region = ee.Geometry.Rectangle(bounds, 'EPSG:4326', false);
var transform = [
  0.008333333333333333, 0, 68.17499999999998,
  0, -0.008333333333333333, 37.09166666666667
];
var clearThreshold = 0.6;
var cloudScore = ee.ImageCollection('GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED');
var scenes = ee.ImageCollection('COPERNICUS/S2_SR_HARMONIZED')
  .filterBounds(region)
  .filterDate('2025-01-01', '2026-01-01')
  .select(['B4', 'B8'])
  .linkCollection(cloudScore, ['cs_cdf']);

var ndviScenes = scenes.map(function(image) {
  var red = image.select('B4');
  var nir = image.select('B8');
  var clear = image.select('cs_cdf').gte(clearThreshold);
  return nir.subtract(red).divide(nir.add(red))
    .rename('NDVI')
    .updateMask(clear)
    .updateMask(nir.add(red).gt(0));
});

var count = ndviScenes.count().rename('valid_granules');
var mean = ndviScenes.mean().rename('NDVI_mean_2025_Annual')
  .updateMask(count.gte(3));
var exportImage = mean.addBands(count).toFloat().unmask(-9999, false);

Map.centerObject(region, 4);
Map.addLayer(mean, {min: 0, max: 0.8, palette: ['brown', 'yellow', 'green']}, 'annual mean 2025 NDVI');

Export.image.toDrive({
  image: exportImage,
  description: 'Acacia_India_NDVI_2025_Annual',
  folder: 'Acacia_NDVI',
  fileNamePrefix: 'India_S2_mean_NDVI_2025_Annual_DIRECT_1KM',
  region: region,
  crs: 'EPSG:4326',
  crsTransform: transform,
  maxPixels: 1e13,
  fileFormat: 'GeoTIFF',
  formatOptions: {noData: -9999}
});
