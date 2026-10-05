"""One calculation service for the desktop UI and command line."""
import csv
from dataclasses import dataclass
import io
import json
from pathlib import Path

from . import __version__
from .core import STEP, SIGMA, HYSTERESIS, PROTOCOL, Computed, PreparedTrack, compute, parse_gpx, prepare
from .providers import Repository, Series, atomic_write


@dataclass
class Result:
    filename: str
    prepared: PreparedTrack
    series: Series
    computed: Computed

    def summary(self):
        def gain(g):
            return {"Dplus_m": g.up, "Dmoins_m": g.down} if g is not None else None
        return {"application": "gpx2elev", "version": __version__, "fichier": self.filename,
                "modele": self.series.source.label, "depuis_cache": self.series.from_cache,
                "protocole": PROTOCOL, "pas_m": STEP, "sigma_m": SIGMA, "hysteresis_m": HYSTERESIS,
                "distance_m": self.prepared.length, "points_origine": self.prepared.track.point_count,
                "positions_5m": self.prepared.sample_count, "terrain": gain(self.computed.gain),
                "gpx_somme_brute": gain(self.computed.gpx_raw), "gpx_filtre": gain(self.computed.gpx_filtered),
                "altitude_min_m": self.computed.minimum, "altitude_max_m": self.computed.maximum,
                "replis": [{"modele": s.label, "raison": r} for s, r in self.series.fallbacks]}


def calculate(path, directory, online=True, source=None, progress=lambda *args: None, cancel=None):
    progress("Lecture de la trace GPX", 0, 0)
    track = parse_gpx(Path(path))
    prepared = prepare(track)
    repository = Repository(directory, cancel=cancel)
    try:
        series = repository.obtain(prepared.coordinates, online=online, source=source, progress=progress)
        repository.http.check()
        progress("Lissage du profil et calcul du dénivelé", 0, 0)
        computed = compute(prepared, series.values)
        repository.http.check()
        return Result(Path(path).name, prepared, series, computed)
    finally:
        repository.close()


def export_summary(result, path):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["fichier", "methode", "Dplus_m", "Dmoins_m", "distance_m", "pas_m", "sigma_m", "hysteresis_m", "version_protocole"])
    rows = [(result.series.source.label, result.computed.gain, STEP, SIGMA, HYSTERESIS, PROTOCOL),
            ("GPX · somme brute", result.computed.gpx_raw, "", "", "", "points d'origine"),
            ("GPX · filtré", result.computed.gpx_filtered, STEP, SIGMA, HYSTERESIS, PROTOCOL)]
    for label, gain, step, sigma, threshold, protocol in rows:
        writer.writerow([result.filename, label, f"{gain.up:.6f}" if gain is not None else "",
                         f"{gain.down:.6f}" if gain is not None else "", f"{result.prepared.length:.6f}", step, sigma, threshold, protocol])
    # UTF-8 BOM for Excel on Windows. The same file opens on Linux and macOS.
    atomic_write(path, output.getvalue().encode("utf-8-sig"))


def export_profile(result, path):
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["segment", "distance_cumulee_m", "latitude", "longitude", "modele", "altitude_modele_m", "altitude_lissee_m"])
    offset = 0
    for number, (segment, profile) in enumerate(zip(result.prepared.segments, result.computed.profiles), 1):
        for i, (distance, point, altitude) in enumerate(zip(profile.distance, segment.coordinates, profile.elevations)):
            writer.writerow([number, f"{distance:.6f}", f"{point[0]:.9f}", f"{point[1]:.9f}",
                             result.series.source.label, f"{result.series.values[offset + i]:.6f}", f"{altitude:.6f}"])
        offset += len(segment.distance)
    atomic_write(path, output.getvalue().encode("utf-8-sig"))


def export_json(result, path):
    atomic_write(path, json.dumps(result.summary(), ensure_ascii=False, indent=2).encode("utf-8"))
