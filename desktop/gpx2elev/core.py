"""Distance sampling, Gaussian smoothing and reversal hysteresis.

Independent of the UI, network and operating system. Conventions match
ElevationMath.kt and the audited Python reference, including segment ends.
"""
from dataclasses import dataclass
import io
import math
from pathlib import Path

from defusedxml import ElementTree as ET
import numpy as np

STEP = 5.0
SIGMA = 20.0
HYSTERESIS = 2.0
PROTOCOL = "5m-gaussian20m-odd-extension-hysteresis2m-v1"
MAX_GPX_BYTES = 20 * 1024 * 1024
MAX_POINTS = 250_000
MAX_SAMPLES = 300_000
NAMESPACES = ("", "http://www.topografix.com/GPX/1/0", "http://www.topografix.com/GPX/1/1")


@dataclass
class Segment:
    coordinates: np.ndarray
    elevations: np.ndarray


@dataclass
class Track:
    segments: list[Segment]

    @property
    def point_count(self):
        return sum(len(s.coordinates) for s in self.segments)


@dataclass
class SampledSegment:
    distance: np.ndarray
    coordinates: np.ndarray
    gpx_elevations: np.ndarray | None


@dataclass
class PreparedTrack:
    track: Track
    segments: list[SampledSegment]

    @property
    def coordinates(self):
        return np.concatenate([s.coordinates for s in self.segments])

    @property
    def sample_count(self):
        return sum(len(s.distance) for s in self.segments)

    @property
    def length(self):
        return math.fsum(s.distance[-1] for s in self.segments)


@dataclass(frozen=True)
class Gain:
    up: float
    down: float

    def __add__(self, other):
        return Gain(self.up + other.up, self.down + other.down)


@dataclass
class Profile:
    distance: np.ndarray
    elevations: np.ndarray


@dataclass
class Computed:
    gain: Gain
    profiles: list[Profile]
    gpx_raw: Gain | None
    gpx_filtered: Gain | None

    @property
    def minimum(self):
        return min(float(p.elevations.min()) for p in self.profiles)

    @property
    def maximum(self):
        return max(float(p.elevations.max()) for p in self.profiles)


def tag_name(tag):
    if tag.startswith("{"):
        uri, name = tag[1:].split("}", 1)
        return name if uri in NAMESPACES else None
    return tag


def parse_gpx(source: Path | bytes) -> Track:
    if isinstance(source, bytes):
        data = source
    else:
        with Path(source).open("rb") as stream:
            data = stream.read(MAX_GPX_BYTES + 1)
    if len(data) > MAX_GPX_BYTES:
        raise ValueError("Le GPX dépasse la limite de 20 Mo.")
    try:
        root = ET.parse(io.BytesIO(data), forbid_dtd=True, forbid_entities=True).getroot()
    except Exception as exc:
        raise ValueError("Fichier XML invalide ou contenant une déclaration DTD interdite.") from exc
    if tag_name(root.tag) != "gpx":
        raise ValueError("Ce fichier n'est pas un GPX 1.0 ou 1.1.")
    groups = []
    for child in root:
        if tag_name(child.tag) == "trk":
            groups.extend((s, "trkpt") for s in child if tag_name(s.tag) == "trkseg")
        elif tag_name(child.tag) == "rte":
            groups.append((child, "rtept"))
    segments = []
    count = 0
    for group, point_tag in groups:
        xy, elevations = [], []
        for node in group:
            if tag_name(node.tag) != point_tag:
                continue
            count += 1
            if count > MAX_POINTS:
                raise ValueError(f"Le GPX dépasse {MAX_POINTS:,} points.")
            try:
                lat, lon = float(node.attrib["lat"]), float(node.attrib["lon"])
                if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                    raise ValueError()
            except (KeyError, ValueError) as exc:
                raise ValueError(f"Coordonnées invalides au point {count}.") from exc
            xy.append((lat, lon))
            text = next((e.text for e in node if tag_name(e.tag) == "ele"), None)
            try:
                z = float(text)
            except (TypeError, ValueError):
                z = math.nan
            elevations.append(z if math.isfinite(z) else math.nan)
        if xy:
            segments.append(Segment(np.asarray(xy, dtype=float), np.asarray(elevations, dtype=float)))
    if not any(len(s.coordinates) >= 2 for s in segments):
        raise ValueError("Le GPX ne contient pas de trace ou de route utilisable.")
    return Track(segments)


def distances(coordinates):
    a, b = coordinates[:-1], coordinates[1:]
    lat1, lat2 = np.radians(a[:, 0]), np.radians(b[:, 0])
    dlat, dlon = np.radians(b - a).T
    h = np.sin(dlat / 2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2)**2
    return np.r_[0.0, 12_742_000 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))].cumsum()


def prepare(track: Track) -> PreparedTrack:
    segments = []
    count = 0
    for segment in track.segments:
        if len(segment.coordinates) < 2:
            continue
        ds = distances(segment.coordinates)
        # Retain the last observation at a stop; raw GPX totals retain all points.
        keep = np.r_[np.diff(ds) > 0, True]
        x, xy = ds[keep], segment.coordinates[keep]
        if len(x) < 2 or x[-1] == 0:
            continue
        n = math.ceil(x[-1] / STEP)
        if n <= 0 or count + n + 1 > MAX_SAMPLES:
            raise ValueError(f"Trace trop longue : maximum {MAX_SAMPLES:,} positions à 5 m.")
        grid = np.r_[np.arange(n, dtype=float) * STEP, x[-1]]
        lon = xy[:, 1]
        crosses_date_line = np.any(np.abs(np.diff(lon)) > 180)
        if crosses_date_line:
            lon = np.degrees(np.unwrap(np.radians(lon)))
        sampled_lon = np.interp(grid, x, lon)
        if crosses_date_line:
            sampled_lon = (sampled_lon + 180) % 360 - 180
        points = np.column_stack((np.interp(grid, x, xy[:, 0]), sampled_lon))
        gps = segment.elevations[keep]
        sampled_gps = np.interp(grid, x, gps) if np.isfinite(gps).all() else None
        segments.append(SampledSegment(grid, points, sampled_gps))
        count += len(grid)
    if not segments:
        raise ValueError("Le GPX ne contient aucun parcours avec deux positions distinctes.")
    return PreparedTrack(track, segments)


def gaussian(x, z, sigma=SIGMA, step=STEP):
    x, z = np.asarray(x, dtype=float), np.asarray(z, dtype=float)
    if (x.ndim != 1 or z.shape != x.shape or not len(x) or not np.isfinite(x).all()
            or not np.isfinite(z).all() or not math.isfinite(sigma) or sigma < 0
            or not math.isfinite(step) or step <= 0 or np.any(np.diff(x) <= 0)):
        raise ValueError("Profil ou paramètres gaussiens invalides.")
    if len(x) == 1 or sigma == 0:
        return z.copy()
    length = x[-1] - x[0]
    radius = int(4 * sigma / step + .5)
    offsets = np.arange(-radius, radius + 1) * step
    weights = np.exp(-.5 * (offsets / sigma)**2)
    weights /= weights.sum()
    last = math.ceil(length / step)
    grid = x[0] + np.arange(-radius, last + radius + 1) * step
    q = grid - x[0]
    periods = np.floor(q / (2 * length))
    remainder = q - periods * 2 * length
    forward = remainder <= length
    reflected = np.where(forward, remainder, 2 * length - remainder)
    inside = np.interp(x[0] + reflected, x, z)
    extension = np.where(forward, inside, 2 * z[-1] - inside) + 2 * periods * (z[-1] - z[0])
    # No SciPy runtime: the exact same finite Gaussian kernel, radius 4 sigma.
    filtered = np.convolve(extension, weights, mode="valid")
    return np.interp(x, x[0] + np.arange(last + 1) * step, filtered)


def anchors(z, threshold=HYSTERESIS):
    z = np.asarray(z, dtype=float)
    if not len(z) or not np.isfinite(z).all() or not math.isfinite(threshold) or threshold < 0:
        raise ValueError("Profil ou seuil d'hystérésis invalide.")
    if threshold == 0:
        return np.arange(len(z))
    result = [0]
    low = high = extreme = direction = 0

    def append(i):
        if result[-1] != i:
            result.append(i)

    for i in range(1, len(z)):
        if direction == 0:
            if z[i] <= z[low]:
                low = i
            if z[i] >= z[high]:
                high = i
            if z[i] - z[low] >= threshold:
                append(low)
                direction, extreme = 1, i
            elif z[high] - z[i] >= threshold:
                append(high)
                direction, extreme = -1, i
        elif direction == 1:
            if z[i] >= z[extreme]:
                extreme = i
            elif z[extreme] - z[i] >= threshold:
                append(extreme)
                direction, extreme = -1, i
        else:
            if z[i] <= z[extreme]:
                extreme = i
            elif z[i] - z[extreme] >= threshold:
                append(extreme)
                direction, extreme = 1, i
    if direction:
        append(extreme)
    append(len(z) - 1)
    return np.asarray(result)


def totals(z):
    delta = np.diff(np.asarray(z, dtype=float))
    if not np.isfinite(delta).all():
        raise ValueError("Altitudes non finies.")
    return Gain(math.fsum(delta[delta > 0]), math.fsum(-delta[delta < 0]))


def filtered_gain(x, z):
    smoothed = gaussian(x, z)
    gain = totals(smoothed[anchors(smoothed)])
    if abs(gain.up - gain.down - (smoothed[-1] - smoothed[0])) >= 1e-6:
        raise ArithmeticError("Incohérence entre montée, descente et extrémités.")
    return gain, smoothed


def compute(prepared, elevations):
    elevations = np.asarray(elevations, dtype=float)
    if elevations.shape != (prepared.sample_count,) or not np.isfinite(elevations).all():
        raise ValueError("Le profil d'altitude est incomplet.")
    offset = 0
    distance_offset = 0.0
    gain, gps = Gain(0, 0), Gain(0, 0)
    profiles = []
    for segment in prepared.segments:
        n = len(segment.distance)
        part, smoothed = filtered_gain(segment.distance, elevations[offset:offset + n])
        gain += part
        profiles.append(Profile(segment.distance + distance_offset, smoothed))
        offset += n
        distance_offset += segment.distance[-1]
        gps = gps + filtered_gain(segment.distance, segment.gpx_elevations)[0] if gps is not None and segment.gpx_elevations is not None else None
    native = [s for s in prepared.track.segments if len(s.elevations) >= 2]
    raw = Gain(0, 0)
    for segment in native:
        if not np.isfinite(segment.elevations).all():
            raw = None
            break
        raw += totals(segment.elevations)
    return Computed(gain, profiles, raw, gps)
