import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gpx2elev.smoke import run_smoke
from gpx2elev.smoke import SYNTHETIC_GPX
from gpx2elev.core import parse_gpx, prepare
from gpx2elev.providers import ProfileCache, Source
from gpx2elev.ui import DesktopApplication, MainWindow
from PySide6.QtGui import QFileOpenEvent
from gpx2elev.i18n import translate, number
from gpx2elev.service import calculate


class UiTests(unittest.TestCase):
    def test_clear_cache_preserves_result_and_requires_confirmation(self):
        from PySide6.QtWidgets import QMessageBox
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'last.gpx'
            path.write_bytes(SYNTHETIC_GPX)
            prepared = prepare(parse_gpx(path))
            ProfileCache(root / 'profiles').save(Source.IGN, prepared.coordinates, 100 + .1 * prepared.segments[0].distance)
            result = calculate(path, root, online=False)
            window = MainWindow(root, restore=False)
            window.current_path = path
            window.show_result(result)
            window.language_picker.setCurrentIndex(1)
            window.select_language()
            settings = (root / 'settings.json').read_bytes()
            self.assertEqual(window.clear_cache_button.text(), 'Clear cache')
            self.assertGreater(sum(window.cache_bytes.values()), 0)
            with patch('gpx2elev.ui.QMessageBox.question', return_value=QMessageBox.StandardButton.No):
                window.confirm_clear_cache()
            self.assertIsNone(window.cache_worker)
            with patch('gpx2elev.ui.QMessageBox.question', return_value=QMessageBox.StandardButton.Yes):
                window.confirm_clear_cache()
            self.assertFalse(window.import_button.isEnabled())
            self.assertFalse(window.clear_cache_button.isEnabled())
            deadline = time.monotonic() + 5
            while window.cache_worker is not None and time.monotonic() < deadline:
                app.processEvents()
                time.sleep(.01)
            self.assertIsNone(window.cache_worker)
            self.assertEqual(sum(window.cache_bytes.values()), 0)
            self.assertFalse(window.clear_cache_button.isEnabled())
            self.assertIs(window.result, result)
            self.assertTrue(window.export_button.isEnabled())
            self.assertEqual(path.read_bytes(), SYNTHETIC_GPX)
            self.assertEqual((root / 'settings.json').read_bytes(), settings)
            self.assertEqual(window.status.text(), 'Cache cleared.')
            window.close()

    def test_language_switch_persistence_results_and_messages(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'test.gpx'
            path.write_bytes(SYNTHETIC_GPX)
            prepared = prepare(parse_gpx(path))
            ProfileCache(root / 'profiles').save(Source.IGN, prepared.coordinates, 100 + .1 * prepared.segments[0].distance)
            result = calculate(path, root, online=False)
            window = MainWindow(root, restore=False)
            window.current_path = path
            window.show_result(result)
            window.language_picker.setCurrentIndex(0)
            self.assertEqual(window.import_button.text(), 'Choisir un GPX')
            self.assertIn('0,22', window.length.text())
            gain = window.result.computed.gain
            window.language_picker.setCurrentIndex(1)
            self.assertEqual(window.import_button.text(), 'Choose a GPX')
            self.assertIn('0.22', window.length.text())
            self.assertEqual(window.result.computed.gain, gain)
            self.assertIn('Raw sum of elevation changes', window.comparison.text())
            with patch('gpx2elev.ui.QMessageBox.about') as about:
                window.about()
                self.assertIn('Estimated elevation gain', about.call_args.args[2])
                self.assertNotIn('Les coordonnées', about.call_args.args[2])
            window.result = None
            window.show_error('Coordonnées invalides au point 42.')
            self.assertEqual(window.details.toPlainText(), 'Invalid coordinates at point 42.')
            self.assertEqual(window.source_label.text(), 'No complete profile available')
            restored = MainWindow(root, restore=False)
            self.assertEqual(restored.language, 'en')
            self.assertEqual(restored.import_button.text(), 'Choose a GPX')
            window.language_picker.setCurrentIndex(0)
            self.assertEqual(window.details.toPlainText(), 'Coordonnées invalides au point 42.')
            window.close()
            restored.close()

    def test_shared_catalog_and_dynamic_messages(self):
        import json
        from gpx2elev.i18n import CATALOG
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(CATALOG, json.loads((root / 'app/src/main/assets/translations.json').read_text(encoding='utf-8')))
        self.assertEqual(translate('Calcul terminé · 1,500 points GPX · 4,467 positions à 5 m', 'en'),
                         'Calculation complete · 1,500 GPX points · 4,467 positions at 5 m')
        self.assertEqual(number(1234.5, 1, 'en'), '1,234.5')
        self.assertEqual(number(1234.5, 1, 'fr'), '1\u202f234,5')

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
