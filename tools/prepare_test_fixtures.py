"""Export audited reference values into Android unit-test-only fixtures (never APK assets)."""
from pathlib import Path
import csv
import json
import sys
import zipfile
import math

from PIL import Image

import numpy as np
import rasterio
from rasterio.windows import Window

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from analyse_fourchette_denivele import read_existing_nominal
from analyse_protocole_propose import spatial_gaussian
import compare_deniveles as c


def main():
    output = ROOT / 'android/app/src/test/resources'
    output.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((ROOT / 'analyse_incertitude_XY_2026-10-04/metadonnees.json').read_text(encoding='utf-8'))
    x, z = read_existing_nominal(metadata)
    target = Path(r'C:\Users\Nico\Documents\gpx') / metadata['fichier']
    xy = c.read_gpx(target, 5.)[0][1]
    filtered = spatial_gaussian(x, z, 20., 5.)
    (output / 'reference.gpx').write_bytes(target.read_bytes())
    with (output / 'reference.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['distance', 'lat', 'lon', 'ign', 'ign_filtered'])
        writer.writerows(zip(x, xy[:, 0], xy[:, 1], z, filtered))
    expected = {'distance': float(x[-1]), 'samples': len(x), 'up': 735.1285660253573,
                'down': 735.1495651743335, 'raw_gpx_up': 3380.71,
                'raw_gpx_down': 3380.89, 'filtered_gpx_up': 1165.4629988478032,
                'filtered_gpx_down': 1165.6437051934863}
    (output / 'reference_expected.json').write_text(json.dumps(expected, indent=2), encoding='utf-8')
    lat, lon = xy[0]
    tile_x = math.floor((lon + 180) / 360 * 8192)
    tile_y = math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 8192)
    webp = c.CACHE / f'mapterhorn_13_{tile_x}_{tile_y}.webp'
    (output / 'mapterhorn.webp').write_bytes(webp.read_bytes())
    with Image.open(webp) as im:
        rgb = im.convert('RGB')
        with (output / 'mapterhorn_pixels.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['x', 'y', 'red', 'green', 'blue'])
            for pixel_x, pixel_y in np.random.default_rng(52).integers(0, rgb.width, (100, 2)):
                writer.writerow([int(pixel_x), int(pixel_y), *rgb.getpixel((int(pixel_x), int(pixel_y)))])
    for source, filename, predictor in [('copernicus', 'Copernicus_DSM_COG_10_N43_00_E005_00_DEM.tif', 3),
                                        ('fabdem', 'N43E005_FABDEM_V1-2.tif', 2)]:
        with rasterio.open(c.CACHE / filename) as original:
            window = Window(1200, 1200, 128, 128)
            data = original.read(1, window=window)
            transform = original.window_transform(window)
        raster = output / f'{source}.tif'
        with rasterio.open(raster, 'w', driver='GTiff', width=128, height=128, count=1,
                           crs='EPSG:4326', transform=transform, dtype='float32',
                           tiled=True, blockxsize=64, blockysize=64,
                           compress='deflate', predictor=predictor, nodata=-9999) as saved:
            saved.write(data, 1)
            saved.update_tags(AREA_OR_POINT='Point')
        with rasterio.open(raster) as saved, (output / f'{source}_pixels.csv').open('w', encoding='utf-8', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['col', 'row', 'lat', 'lon', 'z'])
            rng = np.random.default_rng(42)
            for col, row in rng.integers(1, 126, (100, 2)):
                lon, lat = saved.transform * (col + .5, row + .5)
                writer.writerow([int(col), int(row), lat, lon, float(data[row, col])])
    for zip64 in (False, True):
        previous = zipfile.ZIP64_LIMIT
        try:
            if zip64:
                zipfile.ZIP64_LIMIT = 100
            with zipfile.ZipFile(output / ('test64.zip' if zip64 else 'test.zip'), 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(output / 'fabdem.tif', 'nested/N43E005_FABDEM_V1-2.tif')
        finally:
            zipfile.ZIP64_LIMIT = previous
    indices = np.array([0, len(x)//2, len(x)-1])
    selected = xy[indices]
    map_values = []
    for lat, lon in selected:
        key = (13, math.floor((lon+180)/360*8192),
               math.floor((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*8192))
        map_values.append(float(c.mapterhorn_values(key, np.array([[lat, lon]]))[0]))
    models = {
        'IGN': z[indices], 'MAPTERHORN': map_values,
        'FABDEM': c.raster_values(c.CACHE/'N43E005_FABDEM_V1-2.tif', selected),
        'COPERNICUS': c.raster_values(c.CACHE/'Copernicus_DSM_COG_10_N43_00_E005_00_DEM.tif', selected),
        'SRTM': c.tile_values('SRTM90', (43, 5), selected, np.arange(3))[1],
    }
    with (output/'live_expected.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['source', 'lat', 'lon', 'z'])
        for source, values in models.items():
            writer.writerows((source, float(lat), float(lon), float(value))
                             for (lat, lon), value in zip(selected, values))
    print(f'Fixture de référence : {len(x)} positions ; GeoTIFF predictor2/predictor3 et ZIP/ZIP64.')


if __name__ == '__main__':
    main()
