import csv
import errno
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

import numpy as np
from PIL import Image
import rasterio
from rasterio.transform import from_origin

from gpx2elev.providers import (Cancelled, MissingCoverage, ProfileCache, PublicModels,
    RemoteZip, Repository, Source, bilinear)

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


class TileHttp:
    """Sert la même tuile à chaque requête ; sans tuile, le réseau est interdit."""
    def __init__(self, data):
        self.data, self.urls = data, []

    def check(self):
        pass

    def fetch(self, url, headers=None, **kwargs):
        self.urls.append(url)
        if self.data is None:
            raise AssertionError("Réseau sollicité pour une tuile déjà sur le disque.")
        return self.data, {}


def webp_tile():
    """Tuile Terrarium constante : 128 * 256 + 10 - 32768 = 10 m."""
    buffer = io.BytesIO()
    Image.fromarray(np.full((256, 256, 3), (128, 10, 0), dtype=np.uint8)).save(buffer, "WEBP", lossless=True)
    return buffer.getvalue()


class ProviderTests(unittest.TestCase):
    def test_profile_cache_failure_preserves_valid_model_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Repository(directory, reader=Reader())
            points = np.array([[45., 5.], [45.001, 5.]])
            with patch.object(repo.reader, "read", return_value=np.full(len(points), 123.0)) as read, \
                    patch.object(repo.cache, "save", side_effect=OSError(errno.ENOSPC, "disk full")):
                result = repo.obtain(points)
            read.assert_called_once()
            self.assertEqual(result.source, Source.IGN)
            np.testing.assert_array_equal(result.values, [123, 123])
            self.assertFalse(result.from_cache)
            self.assertEqual(result.fallbacks, [])
            self.assertIn("disk full", result.cache_warning)
            repo.close()

    def test_fallback_uses_one_complete_model_and_caches_it(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Reader()
            repo = Repository(directory, reader=reader)
            points = np.array([[45., 5.], [45.001, 5.]])
            first = repo.obtain(points)
            self.assertEqual(reader.calls, [Source.IGN, Source.MAPTERHORN])
            self.assertEqual(first.source, Source.MAPTERHORN)
            self.assertIsNone(first.cache_warning)
            self.assertEqual(len(first.fallbacks), 1)
            second = repo.obtain(points, online=False)
            self.assertTrue(second.from_cache)
            np.testing.assert_array_equal(second.values, first.values)
            self.assertEqual(len(reader.calls), 2)
            repo.close()

    def test_cached_profile_is_reused_online_without_retrying_better_models(self):
        with tempfile.TemporaryDirectory() as directory:
            reader = Reader()
            points = np.array([[45., 5.], [45.001, 5.]])
            first = Repository(directory, reader=reader).obtain(points)
            again = Repository(directory, reader=reader).obtain(points, online=True)
            # Le repli Mapterhorn en cache est définitif : l'IGN n'est pas réinterrogé.
            self.assertEqual(reader.calls, [Source.IGN, Source.MAPTERHORN])
            self.assertTrue(again.from_cache)
            self.assertEqual(again.source, first.source)
            # Forcer un modèle l'interroge malgré le profil d'un autre modèle en cache.
            with self.assertRaises(MissingCoverage):
                Repository(directory, reader=reader).obtain(points, source=Source.IGN)
            self.assertEqual(reader.calls, [Source.IGN, Source.MAPTERHORN, Source.IGN])

    def test_closing_never_trims_the_cache(self):
        with tempfile.TemporaryDirectory() as directory, patch("gpx2elev.providers.trim_cache") as trim:
            Repository(directory, reader=Reader()).close()
        trim.assert_not_called()

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

    def test_mapterhorn_tile_read_from_disk_is_never_rewritten(self):
        # gpx2dash lit les mêmes tuiles depuis quatre processus : sous Windows,
        # réécrire une tuile qu'un autre processus lit échoue, et l'échec faisait
        # retenir un modèle moins bien classé pour toute la trace.
        with tempfile.TemporaryDirectory() as directory, patch("gpx2elev.providers.atomic_write") as write:
            (Path(directory) / "mapterhorn_13_10_10.webp").write_bytes(webp_tile())
            models = PublicModels(directory, TileHttp(None))
            for _ in range(3):
                models.images.clear()
                np.testing.assert_array_equal(models.image(13, 10, 10), np.full((256, 256), 10.))
        write.assert_not_called()

    def test_downloaded_tiles_survive_a_failed_publication(self):
        hgt = np.full((1201, 1201), 321, dtype=">i2").tobytes()
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as stream:
            stream.writestr("N45E005.hgt", hgt)
        denied = PermissionError(errno.EACCES, "Accès refusé")
        with tempfile.TemporaryDirectory() as directory, patch("gpx2elev.providers.atomic_write", side_effect=denied):
            # La tuile est en mémoire : ne pas pouvoir la publier n'empêche pas de la lire.
            self.assertEqual(float(PublicModels(directory, TileHttp(webp_tile())).image(13, 10, 10)[0, 0]), 10.)
            srtm = PublicModels(directory, TileHttp(archive.getvalue())).srtm((45, 5), np.array([[45.5, 5.5]]))
        np.testing.assert_allclose(srtm, [321.])

    def test_raster_published_meanwhile_by_another_process_is_used(self):
        tile = (RESOURCES / "copernicus.tif").read_bytes()

        def concurrent(path, data):
            Path(path).write_bytes(data)  # l'autre processus publie la même tuile...
            raise PermissionError(errno.EACCES, "Accès refusé")  # ...et la lit pendant notre remplacement

        with tempfile.TemporaryDirectory() as directory:
            with patch("gpx2elev.providers.atomic_write", side_effect=concurrent):
                path = PublicModels(directory, TileHttp(tile)).raster_path(Source.COPERNICUS, (45, 5))
            self.assertEqual(path.read_bytes(), tile)
            # Sans copie publiée, un disque plein reste une erreur : rasterio lit le fichier.
            path.unlink()
            with patch("gpx2elev.providers.atomic_write", side_effect=OSError(errno.ENOSPC, "disk full")), \
                    self.assertRaises(OSError):
                PublicModels(directory, TileHttp(tile)).raster_path(Source.COPERNICUS, (45, 5))


if __name__ == "__main__":
    unittest.main()
