"""Native GPX observations, time ticks and a cursor independent of draw decimation."""
from dataclasses import dataclass
from datetime import datetime, timezone
import math

import numpy as np

from .core import distances


@dataclass(frozen=True)
class Selection:
    distance: float
    time: float | None
    terrain: float | None
    gpx: float | None
    interpolated: bool = False


class ChartObservations:
    def __init__(self, prepared, terrain):
        xs, zs, times, groups = [], [], [], []
        self.terrain = []
        offset = 0.0
        terrain_index = 0
        for group, segment in enumerate(prepared.track.segments):
            x = distances(segment.coordinates)
            xs.append(x + offset)
            zs.append(segment.elevations)
            times.append(segment.times if segment.times is not None else np.full(len(x), np.nan))
            groups.append(np.full(len(x), group, dtype=int))
            self.terrain.append(terrain[terrain_index] if len(x) >= 2 and x[-1] > 0 else None)
            if len(x) >= 2 and x[-1] > 0:
                terrain_index += 1
            offset += x[-1]
        self.distance = np.concatenate(xs)
        self.elevation = np.concatenate(zs)
        self.times = np.concatenate(times)
        self.groups = np.concatenate(groups)
        self.has_time = bool(np.isfinite(self.times).any())

    def time_at(self, distance):
        """Interpolate adjacent times only, without crossing gaps, segments or clock reversals."""
        end = int(np.searchsorted(self.distance, distance, side="right"))
        if end and self.distance[end - 1] == distance:
            value = self.times[end - 1]
            return float(value) if np.isfinite(value) else None
        if end == 0 or end == len(self.distance):
            return None
        a, b = end - 1, end
        start, finish = self.times[a], self.times[b]
        if self.groups[a] != self.groups[b] or not np.isfinite([start, finish]).all() or finish < start:
            return None
        fraction = (distance - self.distance[a]) / (self.distance[b] - self.distance[a])
        return float(start + fraction * (finish - start))

    def select(self, distance, elevation, visible=None):
        at = int(np.searchsorted(self.distance, distance))
        neighbours = {max(0, min(len(self.distance) - 1, at)), max(0, min(len(self.distance) - 1, at - 1))}
        closest = min(abs(self.distance[i] - distance) for i in neighbours)
        candidates = []
        for i in sorted(neighbours):
            if abs(self.distance[i] - distance) > closest + 1e-9:
                continue
            start = int(np.searchsorted(self.distance, self.distance[i], side="left"))
            end = int(np.searchsorted(self.distance, self.distance[i], side="right"))
            candidates.extend(range(start, end))
        # Multiple measurements at a stop share x; select the closest recorded elevation to the tap.
        index = min(set(candidates), key=lambda i: (abs(self.elevation[i] - elevation)
                    if np.isfinite(self.elevation[i]) else math.inf, -i))
        x = float(self.distance[index])
        if visible is not None and not visible[0] <= x <= visible[1]:
            # A zoomed view may contain no native observation. Read the visible line at the tap.
            end = int(np.searchsorted(self.distance, distance, side="right"))
            if 0 < end < len(self.distance) and self.groups[end - 1] == self.groups[end]:
                a, b = end - 1, end
                fraction = (distance - self.distance[a]) / (self.distance[b] - self.distance[a])
                gpx = ((1 - fraction) * self.elevation[a] + fraction * self.elevation[b]
                       if np.isfinite(self.elevation[a:b + 1]).all() else None)
                profile = self.terrain[self.groups[a]]
                terrain = float(np.interp(distance, profile.distance, profile.elevations)) if profile is not None else None
                return Selection(float(distance), self.time_at(distance), terrain, None if gpx is None else float(gpx), True)
        profile = self.terrain[self.groups[index]]
        terrain = float(np.interp(x, profile.distance, profile.elevations)) if profile is not None else None
        time = float(self.times[index]) if np.isfinite(self.times[index]) else None
        gpx = float(self.elevation[index]) if np.isfinite(self.elevation[index]) else None
        return Selection(x, time, terrain, gpx)


def local_time(value, seconds=False, language="fr", date=False, zone=None):
    if value is None:
        return "—"
    try:
        time = datetime.fromtimestamp(value, timezone.utc).astimezone(zone)
        clock = time.strftime("%H:%M:%S" if seconds else "%H:%M")
        return time.strftime("%d/%m/%Y " if language == "fr" else "%Y-%m-%d ") + clock if date else clock
    except (ValueError, OverflowError, OSError):
        return "—"
