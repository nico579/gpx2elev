import os
from pathlib import Path
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gpx2elev.smoke import run_smoke
from gpx2elev.smoke import SYNTHETIC_GPX
from gpx2elev.core import parse_gpx, prepare
from gpx2elev.providers import ProfileCache, Source
from gpx2elev.ui import DesktopApplication, MainWindow
from PySide6.QtGui import QFileOpenEvent


class UiTests(unittest.TestCase):
    def test_real_window_drop_worker_cache_chart_and_export(self):
        resources = Path(__file__).resolve().parents[2] / "app/src/test/resources"
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "ui.json"
            self.assertEqual(run_smoke(report, resources), 0)
            self.assertTrue(report.with_suffix(".png").exists())

    def test_native_file_open_during_another_calculation_is_not_lost(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "premier.gpx", root / "second.gpx"
            first.write_bytes(SYNTHETIC_GPX)
            second.write_bytes(SYNTHETIC_GPX.replace(b'45.002', b'45.003'))
            for path in (first, second):
                prepared = prepare(parse_gpx(path))
                ProfileCache(root / "profiles").save(Source.IGN, prepared.coordinates, 100 + .1 * prepared.segments[0].distance)
            window = MainWindow(root, restore=False)
            window.online.setChecked(False)
            app.window = window
            window.open_path(first)
            app.sendEvent(app, QFileOpenEvent(str(second)))
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                app.processEvents()
                if window.worker is None and window.result is not None and window.result.filename == second.name:
                    break
                time.sleep(.01)
            self.assertIsNotNone(window.result)
            self.assertEqual(window.result.filename, second.name)
            self.assertIsNone(window.worker)
            window.close()
            app.window = None


if __name__ == "__main__":
    unittest.main()
