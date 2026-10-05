import csv
import io
from pathlib import Path
import tempfile
import threading
import unittest
import zipfile

import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_origin

from gpx2elev.providers import (Cancelled, MissingCoverage, ProfileCache, PublicModels,
    RANKING, RemoteZip, Repository, Source, bilinear)

RESOURCES = Path(__file__).resolve().parents[2] / "app/src/test/resources"


class Reader:
    def __init__(self):
        self.calls = []

    def read(self, source, points, progress):
        self.calls.append(source)
        if source == Source.IGN:
            return np.full(len(points), -99999.)
        return np.arange(len(points)) + 100.


class MemoryHttp:
    def __init__(self, data):
        self.data = data

    def check(self):
        pass

    def fetch(self, url, headers=None, **kwargs):
        span = headers["Range"][6:]
        if span.startswith("-"):
            start, end = max(0, len(self.data) - int(span[1:])), len(self.data) - 1
        else:
            start, end = map(int, span.split("-"))
        return self.data[start:end + 1], {"Content-Range": f"bytes {start}-{end}/{len(self.data)}", "ETag": '"fixture"'}


class ProviderTests(unittest.TestCase):
    def test_fallback_uses_one_complete_model_and_caches_it(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Reader()
            repo = Repository(directory, reader=reader)
            points = np.array([[45., 5.], [45.001, 5.]])
            first = repo.obtain(points)
            self.assertEqual(reader.calls, [Source.IGN, Source.MAPTERHORN])
            self.assertEqual(first.source, Source.MAPTERHORN)
            self.assertEqual(len(first.fallbacks), 1)
            second = repo.obtain(points, online=False)
            self.assertTrue(second.from_cache)
            np.testing.assert_array_equal(second.values, first.values)
            self.assertEqual(len(reader.calls), 2)
            repo.close()

    def test_cache_integrity_coordinates_and_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = ProfileCache(directory)
            points = np.array([[45., 5.], [45.001, 5.]])
            cache.save(Source.IGN, points, [10, 20])
            self.assertIsNone(cache.load(Source.MAPTERHORN, points))
            self.assertIsNone(cache.load(Source.IGN, points + .00001))
            path = cache.file(Source.IGN, points)
            data = bytearray(path.read_bytes())
            data[10] ^= 1
            path.write_bytes(data)
            self.assertIsNone(cache.load(Source.IGN, points))

    def test_cancellation_never_becomes_a_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            cancel = threading.Event()
            cancel.set()
            reader = Reader()
            repo = Repository(directory, reader=reader, cancel=cancel)
            with self.assertRaises(Cancelled):
                repo.obtain(np.array([[45, 5]]))
            self.assertEqual(reader.calls, [])
            repo.close()

    def test_zero_negative_and_nodata_bilinear_samples(self):
        array = np.array([[-10., 0], [10, np.nan]])
        self.assertEqual(float(bilinear(array, 1, 0)), 0)
        self.assertEqual(float(bilinear(array, 0, 0)), -10)
        self.assertTrue(np.isnan(bilinear(array, .5, .5)))
        self.assertTrue(np.isnan(bilinear(array, -1, 0)))

    def test_remote_zip_and_zip64_extract_real_fixture(self):
        for name in ("test.zip", "test64.zip"):
            with self.subTest(name=name):
                data = (RESOURCES / name).read_bytes()
                with RemoteZip("fixture", MemoryHttp(data)) as remote, zipfile.ZipFile(remote) as archive:
                    member = next(e for e in archive.infolist() if e.filename.endswith(".tif"))
                    self.assertEqual(archive.read(member), (RESOURCES / "fabdem.tif").read_bytes())

    def test_raster_interpolation_across_tile_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Two adjacent 2x2 tiles; constant north/south, linear west/east.
            for lon, values in ((5, [[100, 110], [100, 110]]), (6, [[120, 130], [120, 130]])):
                name = f"N45E00{lon}_FABDEM_V1-2.tif"
                with rasterio.open(root / name, "w", driver="GTiff", width=2, height=2, count=1,
                                   dtype="float32", crs="EPSG:4326", transform=from_origin(lon, 46, .5, .5)) as dataset:
                    dataset.write(np.asarray(values, dtype=np.float32), 1)
            models = PublicModels(root, MemoryHttp(b""))
            values = models.raster_values(Source.FABDEM, (45, 5), np.array([[45.5, 5.99], [45.5, 6.]]))
            np.testing.assert_allclose(values, [114.8, 115], atol=1e-9)

    def test_public_geotiff_values(self):
        for stem in ("fabdem", "copernicus"):
            with self.subTest(source=stem), rasterio.open(RESOURCES / f"{stem}.tif") as dataset:
                array = dataset.read(1)
                with (RESOURCES / f"{stem}_pixels.csv").open() as stream:
                    rows = list(csv.DictReader(stream))
                for row in rows:
                    # The same raster-control grids used by the Android decoder tests.
                    x, y, expected = int(row["col"]), int(row["row"]), float(row["z"])
                    self.assertAlmostEqual(float(array[y, x]), expected, places=5)
                    col, line = (~dataset.transform) * (float(row["lon"]), float(row["lat"]))
                    self.assertAlmostEqual(col - .5, x, places=7)
                    self.assertAlmostEqual(line - .5, y, places=7)

    def test_public_webp_terrarium_rgb(self):
        with Image.open(RESOURCES / "mapterhorn.webp") as image:
            rgb = np.asarray(image.convert("RGB"))
        with (RESOURCES / "mapterhorn_pixels.csv").open() as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            values = list(row.values())
            x, y = int(values[0]), int(values[1])
            np.testing.assert_array_equal(rgb[y, x], [int(v) for v in values[2:5]])


if __name__ == "__main__":
    unittest.main()
