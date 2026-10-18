"""Exercise the actual HTTP GUI, calculation, native readers and CSV exports."""
import base64
import csv
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import urllib.request

import numpy as np
from PIL import Image
import rasterio
from nico579_commons import serveweb

from . import __version__
from .core import parse_gpx, parse_time, prepare
from .providers import ProfileCache, Source
from .web import Application, start_server

SYNTHETIC_GPX = b'''<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
<trkpt lat="45" lon="5"><ele>100</ele><time>2026-10-08T10:00:00Z</time></trkpt>
<trkpt lat="45.001" lon="5"><ele>110</ele><time>2026-10-08T10:05:00Z</time></trkpt>
<trkpt lat="45.002" lon="5"><ele>120</ele><time>2026-10-08T10:10:00Z</time></trkpt>
</trkseg></trk></gpx>'''


def run_smoke(report_path, fixtures=None):
    report_path = Path(report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if fixtures is None:
        fixtures = Path(sys._MEIPASS) / "smoke_data" if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2] / "app/src/test/resources"
    fixtures = Path(fixtures)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        prepared = prepare(parse_gpx(SYNTHETIC_GPX))
        ProfileCache(root / "profiles").save(Source.IGN, prepared.coordinates, 100 + .1 * prepared.segments[0].distance)
        app = Application(root, online=False)
        server, port = start_server(app)
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

        def request(route, payload=None):
            req = urllib.request.Request(f"http://127.0.0.1:{port}{route}",
                data=json.dumps(payload).encode() if payload is not None else None,
                headers={"Content-Type": "application/json"})
            with opener.open(req, timeout=15) as response:
                data = response.read()
                return json.loads(data) if route.startswith("/api/") else data

        try:
            assert not serveweb.fichiers_manquants(), serveweb.fichiers_manquants()
            for asset in ("/", "/app.js", "/chart.js", "/route.js", "/style.css", "/web_bridge.js", "/nico579-langue.js",
                          "/nico579-maj.js", "/nico579-reglages.js", "/NotoSans.ttf", "/favicon.ico"):
                assert request(asset), asset
            assert request("/api/init")["app"] == "gpx2elev"
            assert request("/api/upload", {"name": "test.gpx", "content": base64.b64encode(SYNTHETIC_GPX).decode(),
                                          "online": False, "model": None})["ok"]
            deadline = time.monotonic() + 20
            while request("/api/state")["busy"] and time.monotonic() < deadline:
                time.sleep(.01)
            state = request("/api/state")
            assert not state["busy"] and state["has_result"], state
            result = request("/api/result")
            summary = result["summary"]
            np.testing.assert_allclose(summary["terrain"]["Dplus_m"], .1 * prepared.length, atol=1e-8)
            np.testing.assert_allclose(summary["terrain"]["Dmoins_m"], 0, atol=1e-8)
            assert summary["depuis_cache"] and summary["fichier"] == "test.gpx"
            assert result["chart"]["native"]["y"] == [100, 110, 120]
            x = result["chart"]["native"]["x"][1]
            selection = request(f"/api/select?x={x}&y=110&left=0&right={prepared.length}")
            assert selection["gpx"] == 110 and selection["time"] == parse_time("2026-10-08T10:05:00Z")
            for kind, count in (("summary", 3), ("profile", prepared.sample_count)):
                export = request("/api/export?kind=" + kind)
                assert export["content"].startswith("\ufeff")
                rows = list(csv.DictReader(io.StringIO(export["content"].lstrip("\ufeff")), delimiter=";"))
                assert len(rows) == count
            for code in ("en", "fr"):
                assert request("/api/langue", {"code": code})["enregistre"]
                assert request("/api/langue")["code"] == code
            update = request("/api/maj")
            assert update["version_locale"] == __version__ and update["etat"]["etat"] == "inactif", update
            assert request("/api/clear-cache", {})["error"]
            assert request("/api/clear-cache", {"confirm": True})["ok"]
            deadline = time.monotonic() + 10
            while request("/api/state")["busy"] and time.monotonic() < deadline:
                time.sleep(.01)
            assert sum(request("/api/state")["cache"].values()) == 0
            assert request("/api/result")["summary"] == summary
            assert (root / "last.gpx").read_bytes() == SYNTHETIC_GPX
            for name in ("copernicus.tif", "fabdem.tif"):
                with rasterio.open(fixtures / name) as dataset:
                    assert np.isfinite(dataset.read(1)).any() and dataset.crs.to_epsg() == 4326
            with Image.open(fixtures / "mapterhorn.webp") as image:
                image.load()
                assert image.size == (512, 512)
            assert not any(name.startswith(("PySide", "PyQt")) for name in sys.modules)
            report = {"status": "OK", "version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
                      "platform": sys.platform, "checks": ["serveur HTTP nico579-commons", "page et assets embarqués",
                      "import GPX", "calcul hors connexion", "profil linéaire conservé", "GPX brut et filtré",
                      "heures et curseur GPX", "exports CSV", "langue FR/EN persistée", "API de mise à jour",
                      "taille et suppression du cache", "GeoTIFF GDAL", "WebP Terrarium", "aucun Qt chargé"],
                      "resultat_synthetique": summary}
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            app.close()
            server.shutdown()
            server.server_close()
    return 0
