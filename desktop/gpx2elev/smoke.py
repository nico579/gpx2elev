"""Exercise the packaged executable, including Qt, GDAL, WebP and CSV exports."""
import csv
import json
from pathlib import Path
import sys
import tempfile
import time

import numpy as np
from PIL import Image
import rasterio
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent

from .core import parse_gpx, prepare
from .providers import ProfileCache, Source
from .service import export_profile, export_summary
from .ui import DesktopApplication, MainWindow

SYNTHETIC_GPX = b'''<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
<trkpt lat="45" lon="5"><ele>100</ele></trkpt>
<trkpt lat="45.001" lon="5"><ele>110</ele></trkpt>
<trkpt lat="45.002" lon="5"><ele>120</ele></trkpt>
</trkseg></trk></gpx>'''


def run_smoke(report_path, fixtures=None):
    report_path = Path(report_path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if fixtures is None:
        fixtures = Path(sys._MEIPASS) / "smoke_data" if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2] / "app/src/test/resources"
    fixtures = Path(fixtures)
    app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-self-test"])
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "test.gpx"
        path.write_bytes(SYNTHETIC_GPX)
        prepared = prepare(parse_gpx(path))
        ProfileCache(root / "profiles").save(Source.IGN, prepared.coordinates, 100 + .1 * prepared.segments[0].distance)
        window = MainWindow(root, restore=False)
        window.online.setChecked(False)
        window.show()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        enter = QDragEnterEvent(QPoint(100, 100), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        app.sendEvent(window, enter)
        if not enter.isAccepted():
            raise AssertionError("Le glisser-déposer n'est pas accepté.")
        drop = QDropEvent(QPointF(100, 100), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        app.sendEvent(window, drop)
        deadline = time.monotonic() + 20
        while window.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        if window.worker is not None:
            window.cancel()
            window.worker.wait(20_000)
            raise AssertionError("Le calcul hors connexion n'a pas terminé.")
        result = window.result
        if result is None:
            raise AssertionError(window.details.toPlainText())
        np.testing.assert_allclose(result.computed.gain.up, .1 * prepared.length, atol=1e-8)
        np.testing.assert_allclose(result.computed.gain.down, 0, atol=1e-8)
        if not result.series.from_cache or not window.export_button.isEnabled():
            raise AssertionError("L'interface ne présente pas un résultat exportable depuis le cache.")
        export_summary(result, root / "resultat.csv")
        export_profile(result, root / "profil.csv")
        with (root / "resultat.csv").open(encoding="utf-8-sig", newline="") as stream:
            if len(list(csv.DictReader(stream, delimiter=";"))) != 3:
                raise AssertionError("Comparaison GPX absente de l'export.")
        with (root / "profil.csv").open(encoding="utf-8-sig", newline="") as stream:
            if len(list(csv.DictReader(stream, delimiter=";"))) != prepared.sample_count:
                raise AssertionError("Profil exporté incomplet.")
        app.processEvents()
        window.grab().save(str(report_path.with_suffix(".png")))
        # Verify the libraries and their binary plugins inside the frozen bundle.
        for name in ("copernicus.tif", "fabdem.tif"):
            with rasterio.open(fixtures / name) as dataset:
                pixels = dataset.read(1)
                if not np.isfinite(pixels).any() or dataset.crs.to_epsg() != 4326:
                    raise AssertionError(f"GeoTIFF ou base PROJ illisible : {name}, CRS={dataset.crs}, EPSG={dataset.crs.to_epsg()}.")
        with Image.open(fixtures / "mapterhorn.webp") as image:
            image.load()
            if image.size != (512, 512):
                raise AssertionError("WebP illisible.")
        report = {"status": "OK", "frozen": bool(getattr(sys, "frozen", False)),
                  "platform": sys.platform, "checks": ["ouverture GPX par glisser-déposer", "calcul hors connexion",
                      "profil linéaire conservé", "GPX brut et filtré", "exports CSV", "rendu Qt", "GeoTIFF GDAL", "WebP Terrarium"],
                  "resultat_synthetique": result.summary()}
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        window.close()
        app.processEvents()
    return 0
