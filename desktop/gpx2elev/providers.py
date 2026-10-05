"""Public DEM readers and verified, bounded, local caches."""
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
import hashlib
import io
import math
from pathlib import Path
import re
import struct
import tempfile
import threading
import zipfile

import numpy as np
from PIL import Image
import rasterio
import requests


class Source(Enum):
    IGN = ("IGN LiDAR HD", "ign_lidar_hd_mnt_mono_wld-7dec-v1")
    MAPTERHORN = ("Mapterhorn", "terrarium-z13-parent-bilinear-v1")
    FABDEM = ("FABDEM 1.2", "FABDEM_V1-2-bilinear-seamless-v1")
    COPERNICUS = ("Copernicus GLO-30", "GLO30-2021-bilinear-seamless-v1")
    SRTM = ("SRTM90", "SRTM3-v2.1-bilinear-v1")

    @property
    def label(self):
        return self.value[0]

    @property
    def configuration(self):
        return self.value[1]


RANKING = tuple(Source)


class Cancelled(Exception):
    pass


class MissingCoverage(Exception):
    pass


@dataclass
class Series:
    source: Source
    values: np.ndarray
    from_cache: bool
    fallbacks: list[tuple[Source, str]]


def atomic_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False) as stream:
        temp = Path(stream.name)
        stream.write(data)
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def valid(values):
    return np.isfinite(values).all() and np.all((values >= -1000) & (values <= 9000))


class ProfileCache:
    def __init__(self, directory):
        self.directory = Path(directory)

    def file(self, source, coordinates):
        digest = hashlib.sha256(source.configuration.encode())
        digest.update(np.asarray(coordinates, dtype=">f8").tobytes())
        return self.directory / f"{source.name}_{digest.hexdigest()}.profile"

    def load(self, source, coordinates):
        path = self.file(source, coordinates)
        n = len(coordinates)
        try:
            if path.stat().st_size != 8 + n * 8 + 32:
                return None
            data = path.read_bytes()
            if hashlib.sha256(data[:-32]).digest() != data[-32:]:
                return None
            if struct.unpack(">II", data[:8]) != (0x47505831, n):
                return None
            values = np.frombuffer(data[8:-32], dtype=">f8").astype(float)
            if not valid(values):
                return None
            path.touch()
            return values
        except (OSError, ValueError, struct.error):
            return None

    def save(self, source, coordinates, values):
        values = np.asarray(values, dtype=float)
        if values.shape != (len(coordinates),) or not valid(values):
            raise ValueError("Le profil à conserver est incomplet.")
        content = struct.pack(">II", 0x47505831, len(values)) + values.astype(">f8").tobytes()
        atomic_write(self.file(source, coordinates), content + hashlib.sha256(content).digest())


def trim_cache(directory, limit):
    directory = Path(directory)
    files = []
    for p in directory.glob("*"):
        try:
            if p.is_file() and not p.is_symlink() and p.suffix != ".part":
                files.append((p.stat().st_mtime, p.stat().st_size, p))
        except OSError:
            continue
    size = sum(f[1] for f in files)
    for _, n, path in sorted(files):
        if size <= limit:
            break
        try:
            path.unlink()
            size -= n
        except OSError:
            continue


class Http:
    def __init__(self, cancel=None):
        self.cancel = cancel if cancel is not None else threading.Event()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "gpx2elev/0.2.2", "Accept-Encoding": "identity"})

    def check(self):
        if self.cancel.is_set():
            raise Cancelled("Calcul annulé.")

    def fetch(self, url, *, headers=None, payload=None, max_bytes=128 * 1024 * 1024):
        for attempt in range(3):
            self.check()
            try:
                method = "GET" if payload is None else "POST"
                with self.session.request(method, url, headers=headers, json=payload, stream=True, timeout=(10, 15)) as response:
                    response.raise_for_status()
                    # Reject a server ignoring a Range request before reading a multi-GB archive.
                    if headers and "Range" in headers and response.status_code != 206:
                        raise ValueError("Le serveur ne respecte pas la lecture HTTP partielle.")
                    length = response.headers.get("Content-Length")
                    if length and int(length) > max_bytes:
                        raise ValueError("Téléchargement trop volumineux.")
                    data = bytearray()
                    for chunk in response.iter_content(64 * 1024):
                        self.check()
                        data.extend(chunk)
                        if len(data) > max_bytes:
                            raise ValueError("Téléchargement trop volumineux.")
                    return bytes(data), response.headers.copy()
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code in (400, 401, 403, 404, 412):
                    raise
                if attempt == 2:
                    raise
            except requests.RequestException:
                if attempt == 2:
                    raise
            if self.cancel.wait(2**attempt):
                self.check()

    def close(self):
        self.session.close()


class RemoteZip(io.RawIOBase):
    """Seekable HTTP range reader. Python's ZipFile handles ZIP and ZIP64/CRC."""
    def __init__(self, url, http):
        super().__init__()
        self.url, self.http = url, http
        data, headers = http.fetch(url, headers={"Range": "bytes=-65557"}, max_bytes=65557)
        match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", headers.get("Content-Range", ""))
        if not match:
            raise ValueError("Taille de l'archive inconnue.")
        start, end, self.size = map(int, match.groups())
        if end != self.size - 1 or len(data) != end - start + 1:
            raise ValueError("Réponse HTTP partielle incohérente.")
        self.tail, self.tail_start, self.pos = data, start, 0
        self.etag = headers.get("ETag")

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = offset + (0 if whence == 0 else self.pos if whence == 1 else self.size)
        if self.pos < 0:
            raise ValueError("Position négative dans l'archive.")
        return self.pos

    def read(self, n=-1):
        self.http.check()
        n = min(self.size - self.pos, self.size if n < 0 else n)
        if n <= 0:
            return b""
        if self.pos >= self.tail_start:
            data = self.tail[self.pos - self.tail_start:self.pos - self.tail_start + n]
        else:
            end = self.pos + n - 1
            headers = {"Range": f"bytes={self.pos}-{end}"}
            if self.etag:
                headers["If-Match"] = self.etag
            data, response_headers = self.http.fetch(self.url, headers=headers, max_bytes=n)
            if response_headers.get("Content-Range") != f"bytes {self.pos}-{end}/{self.size}" or len(data) != n:
                raise ValueError("Réponse HTTP partielle incohérente.")
        self.pos += len(data)
        return data


def tile_name(lat, lon):
    return f'{"N" if lat >= 0 else "S"}{abs(lat):02d}{"E" if lon >= 0 else "W"}{abs(lon):03d}'


def wrap_lon(lon):
    return (lon + 180) % 360 - 180


def bilinear(array, x, y):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    inside = np.isfinite(x) & np.isfinite(y) & (x >= -1e-7) & (y >= -1e-7) & (x <= array.shape[1] - 1 + 1e-7) & (y <= array.shape[0] - 1 + 1e-7)
    x = np.clip(np.where(inside, x, 0), 0, array.shape[1] - 1)
    y = np.clip(np.where(inside, y, 0), 0, array.shape[0] - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, array.shape[1] - 1), np.minimum(y0 + 1, array.shape[0] - 1)
    fx, fy = x - x0, y - y0
    weights = np.array([(1 - fx) * (1 - fy), fx * (1 - fy), (1 - fx) * fy, fx * fy])
    samples = np.array([array[y0, x0], array[y0, x1], array[y1, x0], array[y1, x1]])
    result = np.sum(np.where(weights > 1e-12, samples, 0) * weights, axis=0)
    return np.where(inside, result, np.nan)


class PublicModels:
    def __init__(self, directory, http):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.http = http
        self.images = OrderedDict()
        self.rasters = OrderedDict()
        self.missing_images = set()

    def read(self, source, points, progress):
        points = np.asarray(points, dtype=float)
        if source == Source.IGN:
            return self.ign(points, progress)
        if source == Source.MAPTERHORN:
            return self.mapterhorn(points, progress)
        result = np.empty(len(points))
        groups = {}
        for i, (lat, lon) in enumerate(points):
            groups.setdefault((math.floor(lat), math.floor(wrap_lon(lon))), []).append(i)
        completed = 0
        for key, indices in groups.items():
            self.http.check()
            progress(f"Altitudes {source.label} · {tile_name(*key)}", completed, len(points))
            coords = points[indices].copy()
            coords[:, 1] = wrap_lon(coords[:, 1])
            if source == Source.SRTM:
                result[indices] = self.srtm(key, coords)
            else:
                result[indices] = self.raster_values(source, key, coords)
            completed += len(indices)
            progress(f"Altitudes {source.label}", completed, len(points))
        return result

    def ign(self, points, progress):
        result = np.empty(len(points))
        for start in range(0, len(points), 5000):
            self.http.check()
            batch = points[start:start + 5000]
            payload = {"resource": "ign_lidar_hd_mnt_mono_wld", "delimiter": "|", "zonly": "true",
                       "lat": "|".join(f"{p[0]:.7f}" for p in batch), "lon": "|".join(f"{p[1]:.7f}" for p in batch)}
            data, _ = self.http.fetch("https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json", payload=payload, max_bytes=4 * 1024 * 1024)
            import json
            response = json.loads(data)["elevations"]
            if len(response) != len(batch):
                raise MissingCoverage("Réponse IGN incomplète.")
            z = [v.get("z") if isinstance(v, dict) else v for v in response]
            try:
                values = np.asarray(z, dtype=float)
            except (TypeError, ValueError) as exc:
                raise MissingCoverage("Réponse IGN invalide.") from exc
            if not valid(values):
                raise MissingCoverage("La trace sort de la couverture IGN LiDAR HD.")
            result[start:start + len(batch)] = values
            progress("Altitudes IGN LiDAR HD", start + len(batch), len(points))
        return result

    def image(self, z, x, y):
        count = 2**z
        if not 0 <= y < count:
            raise MissingCoverage("Position hors de la couverture Mercator.")
        key = z, x % count, y
        if key in self.images:
            self.images.move_to_end(key)
            return self.images[key]
        if key in self.missing_images:
            raise MissingCoverage("Tuile Mapterhorn absente.")
        path = self.directory / f"mapterhorn_{key[0]}_{key[1]}_{key[2]}.webp"
        data = path.read_bytes() if path.exists() else None
        for attempt in range(2):
            if data is None:
                try:
                    data, _ = self.http.fetch(f"https://tiles.mapterhorn.com/{key[0]}/{key[1]}/{key[2]}.webp", max_bytes=4 * 1024 * 1024)
                except requests.HTTPError as exc:
                    if exc.response is not None and exc.response.status_code == 404:
                        self.missing_images.add(key)
                        raise MissingCoverage("Tuile Mapterhorn absente.") from exc
                    raise
            try:
                with Image.open(io.BytesIO(data)) as image:
                    if image.width != image.height or image.width not in (256, 512):
                        raise ValueError("Dimensions de tuile invalides.")
                    rgb = np.asarray(image.convert("RGB"), dtype=float)
                break
            except (OSError, ValueError):
                if attempt:
                    raise
                data = None
        atomic_write(path, data)
        array = rgb[:, :, 0] * 256 + rgb[:, :, 1] + rgb[:, :, 2] / 256 - 32768
        array[array <= -32000] = np.nan
        self.images[key] = array
        if len(self.images) > 8:
            self.images.popitem(last=False)
        return array

    def mapterhorn_at(self, point, zoom=13):
        lat, lon = point
        if abs(lat) > 85.0511287798066:
            raise MissingCoverage("Position hors de la couverture Mercator.")
        lon = wrap_lon(lon)
        tiles = 2**zoom
        tx = (lon + 180) / 360 * tiles
        ty = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * tiles
        try:
            array = self.image(zoom, math.floor(tx), math.floor(ty))
        except MissingCoverage:
            if zoom == 0:
                raise
            return self.mapterhorn_at(point, zoom - 1)
        size = array.shape[0]
        gx, gy = tx * size - .5, ty * size - .5
        x, y = math.floor(gx), math.floor(gy)
        dx, dy = gx - x, gy - y
        result = 0.0
        for px, py, weight in ((x, y, (1 - dx) * (1 - dy)), (x + 1, y, dx * (1 - dy)), (x, y + 1, (1 - dx) * dy), (x + 1, y + 1, dx * dy)):
            if weight <= 1e-12:
                continue
            try:
                neighbor = self.image(zoom, px // size, py // size)
                if neighbor.shape != array.shape:
                    raise ValueError("Dimensions de tuiles incohérentes.")
                value = neighbor[py % size, px % size]
            except MissingCoverage:
                if zoom == 0:
                    raise
                qlon = wrap_lon((px + .5) / (tiles * size) * 360 - 180)
                qlat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (py + .5) / (tiles * size)))))
                value = self.mapterhorn_at((qlat, qlon), zoom - 1)
            result += weight * value
        return result

    def mapterhorn(self, points, progress):
        result = np.empty(len(points))
        for i, p in enumerate(points):
            self.http.check()
            if i % 128 == 0:
                progress("Altitudes Mapterhorn", i, len(points))
            result[i] = self.mapterhorn_at(p)
        return result

    def raster_path(self, source, key):
        lat, lon = key
        name = tile_name(lat, lon)
        if source == Source.COPERNICUS:
            stem = f"Copernicus_DSM_COG_10_{name[:3]}_00_{name[3:]}_00_DEM"
            path = self.directory / f"{stem}.tif"
            url = f"https://copernicus-dem-30m.s3.amazonaws.com/{stem}/{stem}.tif"
        else:
            path = self.directory / f"{name}_FABDEM_V1-2.tif"
        if path.exists():
            try:
                with rasterio.open(path) as dataset:
                    dataset.read(1, window=((0, 1), (0, 1)))
                path.touch()
                return path
            except (rasterio.errors.RasterioError, OSError):
                path.unlink(missing_ok=True)
        self.http.check()
        if source == Source.COPERNICUS:
            data, _ = self.http.fetch(url)
        else:
            a, b = 10 * math.floor(lat / 10), 10 * math.floor(lon / 10)
            archive = f"{tile_name(a, b)}-{tile_name(a + 10, b + 10)}_FABDEM_V1-2.zip"
            with RemoteZip("https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/" + archive, self.http) as remote, zipfile.ZipFile(remote) as zip_file:
                info = next((e for e in zip_file.infolist() if Path(e.filename).name == path.name), None)
                if info is None:
                    raise MissingCoverage(f"Tuile FABDEM {name} absente.")
                if info.file_size > 128 * 1024 * 1024:
                    raise ValueError("Tuile FABDEM trop volumineuse.")
                with zip_file.open(info) as stream:
                    chunks = []
                    while chunk := stream.read(1024 * 1024):
                        self.http.check()
                        chunks.append(chunk)
                    data = b"".join(chunks)
        atomic_write(path, data)
        return path

    def open_raster(self, source, key):
        cache_key = source, key
        if cache_key in self.rasters:
            self.rasters.move_to_end(cache_key)
            return self.rasters[cache_key]
        with rasterio.open(self.raster_path(source, key)) as dataset:
            if dataset.crs != rasterio.crs.CRS.from_epsg(4326):
                raise ValueError("Le raster n'est pas en WGS84.")
            array = dataset.read(1, masked=True).astype(np.float32).filled(np.nan)
            array[(array < -1000) | (array > 9000)] = np.nan
            transform = dataset.transform
        self.rasters[cache_key] = array, transform
        if len(self.rasters) > 2:
            self.rasters.popitem(last=False)
        return array, transform

    def raster_values(self, source, key, coordinates):
        array, transform = self.open_raster(source, key)
        cols, rows = (~transform) * (coordinates[:, 1], coordinates[:, 0])
        x, y = cols - .5, rows - .5
        x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
        dx, dy = x - x0, y - y0
        px, py = np.array([x0, x0 + 1, x0, x0 + 1]), np.array([y0, y0, y0 + 1, y0 + 1])
        weights = np.array([(1 - dx) * (1 - dy), dx * (1 - dy), (1 - dx) * dy, dx * dy])
        samples = np.full(px.shape, np.nan)
        inside = (px >= 0) & (px < array.shape[1]) & (py >= 0) & (py < array.shape[0])
        samples[inside] = array[py[inside], px[inside]]
        corner, indices = np.where((~inside) & (weights > 1e-12))
        if len(indices):
            lons, lats = transform * (px[corner, indices] + .5, py[corner, indices] + .5)
            groups = {}
            for i, (lat, lon) in enumerate(zip(lats, lons)):
                groups.setdefault((math.floor(lat - 1e-10), math.floor(wrap_lon(lon) + 1e-10)), []).append(i)
            for neighbor_key, locations in groups.items():
                self.http.check()
                neighbor, nt = self.open_raster(source, neighbor_key)
                loc = np.array(locations)
                nx, ny = (~nt) * (wrap_lon(lons[loc]), lats[loc])
                samples[corner[loc], indices[loc]] = bilinear(neighbor, nx - .5, ny - .5)
        return np.sum(np.where(weights > 1e-12, samples, 0) * weights, axis=0)

    def srtm(self, key, points):
        lat, lon = key
        if not -56 <= lat < 60:
            raise MissingCoverage("Latitude hors de la couverture SRTM90.")
        name = tile_name(lat, lon)
        path = self.directory / f"{name}.hgt"
        length = 1201 * 1201 * 2
        if not path.exists() or path.stat().st_size != length:
            regions = ["Eurasia", "Africa", "North_America", "South_America", "Australia", "Islands"]
            hint = "North_America" if lon < -30 and lat >= 0 else "South_America" if lon < -30 else "Australia" if lon > 100 and lat < 0 else "Africa" if lat < 38 and -30 <= lon <= 60 else "Eurasia"
            for region in [hint] + [r for r in regions if r != hint]:
                try:
                    data, _ = self.http.fetch(f"https://srtm.kurviger.de/SRTM3/{region}/{name}.hgt.zip", max_bytes=length + 1024 * 1024)
                except requests.HTTPError as exc:
                    if exc.response is not None and exc.response.status_code == 404:
                        continue
                    raise
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    info = next((e for e in archive.infolist() if Path(e.filename).name == f"{name}.hgt"), None)
                    if info is None or info.file_size != length:
                        raise ValueError("Archive SRTM invalide.")
                    raw = archive.read(info)
                atomic_write(path, raw)
                break
            else:
                raise MissingCoverage(f"Tuile SRTM {name} absente.")
        array = np.frombuffer(path.read_bytes(), dtype=">i2").reshape(1201, 1201).astype(float)
        array[array == -32768] = np.nan
        return bilinear(array, (points[:, 1] - lon) * 1200, (lat + 1 - points[:, 0]) * 1200)


class Repository:
    def __init__(self, directory, reader=None, cancel=None):
        self.directory = Path(directory)
        self.http = Http(cancel)
        self.cache = ProfileCache(self.directory / "profiles")
        self.reader = reader if reader is not None else PublicModels(self.directory / "tiles", self.http)

    def obtain(self, coordinates, online=True, progress=lambda *args: None, source=None):
        failures = []
        for candidate in (RANKING if source is None else (source,)):
            self.http.check()
            progress(f"Recherche des altitudes · {candidate.label}", 0, len(coordinates))
            cached = self.cache.load(candidate, coordinates)
            if cached is not None:
                return Series(candidate, cached, True, failures)
            if not online:
                failures.append((candidate, "Profil absent du cache hors connexion."))
                continue
            try:
                values = np.asarray(self.reader.read(candidate, coordinates, progress), dtype=float)
                self.http.check()
                if values.shape != (len(coordinates),) or not valid(values):
                    raise MissingCoverage("Le modèle ne couvre pas toutes les positions de la trace.")
                self.cache.save(candidate, coordinates, values)
                return Series(candidate, values, False, failures)
            except Cancelled:
                raise
            except Exception as exc:
                failures.append((candidate, str(exc)[:240]))
        if not online:
            raise MissingCoverage("Cette trace n'est pas encore disponible hors connexion. Activez Internet pour son premier calcul.")
        raise MissingCoverage("Aucun modèle n'a fourni un profil complet.\n" + "\n".join(f"{s.label} : {reason}" for s, reason in failures))

    def close(self):
        self.http.close()
        trim_cache(self.directory / "profiles", 64 * 1024 * 1024)
        trim_cache(self.directory / "tiles", 512 * 1024 * 1024)
