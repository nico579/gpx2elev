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

from .core import parse_gpx, parse_time, prepare
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
        data = SYNTHETIC_GPX
        for altitude, clock in ((100, "10:00:00"), (110, "10:05:00"), (120, "10:10:00")):
            element = f"<ele>{altitude}</ele>".encode()
            data = data.replace(element, element + f"<time>2026-10-08T{clock}Z</time>".encode())
        path.write_bytes(data)
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
        window.chart.select_at(window.chart.chart_rect().center())
        selection = window.chart.selection
        if selection.gpx != 110 or selection.time != parse_time("2026-10-08T10:05:00Z") or selection.terrain is None:
            raise AssertionError("Le curseur ne présente pas l'heure GPX et les deux altitudes.")
        original_size = window.size()
        window.resize(1339, 667)
        app.processEvents()
        if any(label.height() < label.fontMetrics().height() for label in (window.up, window.down, window.length)):
            raise AssertionError("Les valeurs de dénivelé sont coupées dans une fenêtre large et peu haute.")
        if window.chart.geometry().bottom() >= window.fullscreen_button.geometry().top():
            raise AssertionError("Les commandes chevauchent le graphique.")
        window.resize(original_size)
        app.processEvents()
        window.grab().save(str(report_path.with_suffix(".png")))
        gain = result.computed.gain
        for index, language, caption in ((0, "fr", "Choisir un GPX"), (1, "en", "Choose a GPX")):
            window.language_picker.setCurrentIndex(index)
            if window.import_button.text() != caption or window.result.computed.gain != gain:
                raise AssertionError("Échec du changement de langue ou résultat modifié.")
            if window.chart.selection is not selection or ("Mesure GPX :" if language == "fr" else "GPX measurement:") not in window.chart.selection_text():
                raise AssertionError("Le curseur n'est pas conservé ou traduit.")
            app.processEvents()
            window.grab().save(str(report_path.with_suffix(f".{language}.png")))
            # Exercise lazy updater imports in the frozen executable without accessing the network.
            from .update_ui import UpdateDialog
            updates = UpdateDialog(window)
            if updates.check_button.text() != ("Vérifier à nouveau" if language == "fr" else "Check again"):
                raise AssertionError("Dialogue de mise à jour non traduit.")
            updates.status_text = "Vous utilisez la dernière version publiée."
            updates.progress_bar.hide()
            updates.retranslate()
            updates.show()
            app.processEvents()
            updates.grab().save(str(report_path.with_suffix(f".updates.{language}.png")))
            updates.reject()
            updates.deleteLater()
            app.processEvents()
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
        if sum(window.cache_bytes.values()) <= 0 or not window.clear_cache_button.isEnabled():
            raise AssertionError("Taille du cache absente de l'interface.")
        window.start_clear_cache()
        deadline = time.monotonic() + 10
        while window.cache_worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        if window.cache_worker is not None:
            window.cache_worker.wait(10_000)
            raise AssertionError("La suppression du cache n'a pas terminé.")
        if sum(window.cache_bytes.values()) != 0 or window.result is not result or not (root / 'last.gpx').exists():
            raise AssertionError("Suppression du cache incorrecte ou trace perdue.")
        from . import __version__
        report = {"status": "OK", "version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
                  "platform": sys.platform, "checks": ["ouverture GPX par glisser-déposer", "calcul hors connexion",
                      "profil linéaire conservé", "GPX brut et filtré", "exports CSV", "rendu Qt", "mise en page sans chiffres coupés à 1339 × 667", "EN/FR sans recalcul", "heures GPX et curseur avec deux altitudes EN/FR", "dialogue de mise à jour EN/FR sans réseau", "taille et suppression du cache", "GeoTIFF GDAL", "WebP Terrarium"],
                  "resultat_synthetique": result.summary()}
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        window.close()
        app.processEvents()
    return 0
