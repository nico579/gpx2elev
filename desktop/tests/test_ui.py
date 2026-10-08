import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from gpx2elev.smoke import run_smoke
from gpx2elev.smoke import SYNTHETIC_GPX
from gpx2elev.core import Segment, Track, Profile, compute, distances, parse_gpx, prepare
from gpx2elev.providers import ProfileCache, Series, Source
from gpx2elev.ui import DesktopApplication, MainWindow
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QFileOpenEvent, QWheelEvent
from PySide6.QtTest import QTest
from gpx2elev.i18n import translate, number
from gpx2elev.service import Result, calculate


class UiTests(unittest.TestCase):
    def test_short_wide_windows_keep_metrics_readable_and_chart_controls_separate(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        prepared = prepare(parse_gpx(SYNTHETIC_GPX))
        values = 100 + .1 * prepared.segments[0].distance
        result = Result('screen.gpx', prepared, Series(Source.IGN, values, True, []), compute(prepared, values))
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(directory, restore=False)
            window.show_result(result)
            window.show()
            try:
                for language in (0, 1):
                    window.language_picker.setCurrentIndex(language)
                    texts = [label.text() for label in (window.up, window.down, window.length)]
                    for width, height in ((1000, 820), (1339, 667), (1600, 900), (1000, 600), (1000, 820)):
                        with self.subTest(language=language, width=width, height=height):
                            window.resize(width, height)
                            app.processEvents()
                            for label, text in zip((window.up, window.down, window.length), texts):
                                self.assertEqual(label.text(), text)
                                self.assertGreaterEqual(label.height(), label.fontMetrics().height())
                                self.assertGreaterEqual(label.width(), label.fontMetrics().horizontalAdvance(text))
                                frame = label.parentWidget()
                                labels = [frame.layout().itemAt(i).widget() for i in range(3)]
                                for first, second in zip(labels, labels[1:]):
                                    self.assertLess(first.geometry().bottom(), second.geometry().top())
                            self.assertLess(window.chart.geometry().bottom(), window.range_label.geometry().top())
                            self.assertLess(window.chart.geometry().bottom(), window.fullscreen_button.geometry().top())
                            if height < 800:
                                self.assertGreater(window.scroll_area.verticalScrollBar().maximum(), 0)
                                window.scroll_area.ensureWidgetVisible(window.status)
                                app.processEvents()
                                status = window.status.mapTo(window.scroll_area.viewport(), QPoint())
                                self.assertGreaterEqual(status.y(), 0)
                                self.assertLessEqual(status.y() + window.status.height(), window.scroll_area.viewport().height())
                            self.assertIs(window.result, result)
                    window.showMaximized()
                    app.processEvents()
                    for label in (window.up, window.down, window.length):
                        self.assertGreaterEqual(label.height(), label.fontMetrics().height())
                    self.assertLess(window.chart.geometry().bottom(), window.fullscreen_button.geometry().top())
                    window.showNormal()
                    app.processEvents()
            finally:
                window.close()
                app.processEvents()

    def test_click_reads_time_and_both_altitudes_without_turning_a_drag_into_selection(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        from gpx2elev.core import parse_time
        data = SYNTHETIC_GPX.replace(b'<ele>100</ele>', b'<ele>100</ele><time>2026-10-08T10:00:00Z</time>') \
            .replace(b'<ele>110</ele>', b'<ele>110</ele><time>2026-10-08T10:05:00Z</time>') \
            .replace(b'<ele>120</ele>', b'<ele>120</ele><time>2026-10-08T10:10:00Z</time>')
        prepared = prepare(parse_gpx(data))
        values = np.full(prepared.sample_count, 100.)
        result = Result('timed.gpx', prepared, Series(Source.IGN, values, True, []), compute(prepared, values))
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(directory, restore=False)
            window.language_picker.setCurrentIndex(0)
            window.show_result(result)
            window.show()
            app.processEvents()
            chart = window.chart
            view = chart.view
            QTest.mouseClick(chart, Qt.MouseButton.LeftButton, pos=chart.chart_rect().center().toPoint())
            point = chart.selection
            self.assertEqual(point.time, parse_time('2026-10-08T10:05:00Z'))
            self.assertEqual(point.gpx, 110.)
            self.assertAlmostEqual(point.terrain, 100., places=9)
            self.assertEqual(chart.view, view)
            chart.zoom(2)
            center = chart.chart_rect().center().toPoint()
            QTest.mousePress(chart, Qt.MouseButton.LeftButton, pos=center)
            QTest.mouseMove(chart, center + QPoint(40, 15))
            QTest.mouseRelease(chart, Qt.MouseButton.LeftButton, pos=center + QPoint(40, 15))
            self.assertIs(chart.selection, point)
            self.assertNotEqual(chart.view, chart.bounds)
            QTest.mouseClick(window.fullscreen_button, Qt.MouseButton.LeftButton)
            app.processEvents()
            self.assertIs(chart.selection, point)
            window.language_picker.setCurrentIndex(1)
            self.assertIn('Local time:', chart.accessibleDescription())
            self.assertIn('GPX measurement: 110.0 m', chart.selection_text())
            self.assertFalse(chart.grab().isNull())
            QTest.mouseClick(window.fullscreen_exit, Qt.MouseButton.LeftButton)
            app.processEvents()
            self.assertIs(chart.selection, point)
            chart.reset_view()
            rect = chart.chart_rect()
            chart.zoom(8, QPointF(rect.left() + rect.width() * .25, rect.center().y()))
            QTest.mouseClick(chart, Qt.MouseButton.LeftButton, pos=chart.chart_rect().center().toPoint())
            self.assertTrue(chart.selection.interpolated)
            self.assertTrue(chart.view[0] <= chart.selection.distance <= chart.view[1])
            self.assertIn('Interpolated GPX:', chart.selection_text())
            chart.result = None
            self.assertIsNone(chart.selection)
            self.assertEqual(chart.accessibleDescription(), '')
            window.close()

    def test_overflowing_gpx_display_range_keeps_terrain_chart_usable(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        prepared = prepare(Track([Segment(np.array([[45.0, 5.0], [45.001, 5.0]]), np.array([-1e308, 1e308]))]))
        values = np.full(prepared.sample_count, 100.0)
        result = Result('extreme.gpx', prepared, Series(Source.IGN, values, True, []), compute(prepared, values))
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(directory, restore=False)
            window.show_result(result)
            window.show()
            app.processEvents()
            self.assertEqual(window.chart.gpx_profiles, [])
            self.assertTrue(np.isfinite(window.chart.bounds).all())
            window.chart.zoom(2)
            self.assertTrue(np.isfinite(window.chart.view).all())
            self.assertFalse(window.chart.grab().isNull())
            window.close()

    def test_fullscreen_chart_restores_same_zoom_language_and_widget(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'test.gpx'
            path.write_bytes(SYNTHETIC_GPX)
            prepared = prepare(parse_gpx(path))
            values = 100 + .1 * prepared.segments[0].distance
            result = Result(path.name, prepared, Series(Source.IGN, values, False, [], cache_warning='disk full'),
                            compute(prepared, values))
            window = MainWindow(root, restore=False)
            window.language_picker.setCurrentIndex(0)
            self.assertFalse(window.fullscreen_button.isEnabled())
            window.show_result(result)
            window.show()
            app.processEvents()
            chart = window.chart
            height = chart.height()
            chart.zoom(2)
            view = chart.view
            QTest.mouseClick(window.fullscreen_button, Qt.MouseButton.LeftButton)
            app.processEvents()
            self.assertTrue(window.chart_fullscreen.isFullScreen())
            self.assertIs(window.chart, chart)
            self.assertEqual(chart.view, view)
            self.assertGreater(chart.height(), height)
            window.language_picker.setCurrentIndex(1)
            self.assertEqual(window.fullscreen_exit.text(), 'Exit full screen')
            self.assertIn('offline use cannot be guaranteed', window.details.toPlainText())
            QTest.mouseClick(window.fullscreen_zoom_in, Qt.MouseButton.LeftButton)
            zoomed = chart.view
            QTest.mouseClick(window.fullscreen_exit, Qt.MouseButton.LeftButton)
            app.processEvents()
            self.assertIsNone(window.chart_fullscreen)
            self.assertIs(chart.parentWidget(), window.scroll_area.widget())
            self.assertEqual(chart.view, zoomed)
            self.assertTrue(chart.isVisible())
            window.open_chart_fullscreen()
            QTest.keyClick(window.chart_fullscreen, Qt.Key.Key_Escape)
            app.processEvents()
            self.assertIsNone(window.chart_fullscreen)
            self.assertEqual(chart.view, zoomed)
            window.close()

    def test_native_gpx_overlay_gaps_stops_segments_and_common_scale(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        first = Segment(np.array([[45, 5], [45, 5], [45.001, 5], [45.002, 5], [45.003, 5]]),
                        np.array([100, 130, np.nan, 400, 450]))
        singleton = Segment(np.array([[46, 5]]), np.array([500]))
        stop = Segment(np.array([[46, 5], [46, 5]]), np.array([510, 530]))
        last = Segment(np.array([[47, 5], [47.001, 5]]), np.array([600, 620]))
        prepared = prepare(Track([first, singleton, stop, last]))
        values = np.full(prepared.sample_count, 200.0)
        result = Result("segments.gpx", prepared, Series(Source.IGN, values, True, []), compute(prepared, values))
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(directory, restore=False)
            window.language_picker.setCurrentIndex(0)
            window.show_result(result)
            window.show()
            app.processEvents()
            chart = window.chart
            self.assertEqual(len(chart.gpx_profiles), 5)
            np.testing.assert_array_equal(chart.gpx_profiles[0].distance, [0, 0])
            np.testing.assert_array_equal(chart.gpx_profiles[0].elevations, [100, 130])
            np.testing.assert_allclose(chart.gpx_profiles[1].distance, distances(first.coordinates)[3:])
            for profile in chart.gpx_profiles[2:]:
                self.assertAlmostEqual(profile.distance[0], distances(first.coordinates)[-1])
            self.assertAlmostEqual(chart.gpx_profiles[-1].distance[-1], prepared.length)
            self.assertEqual((chart.minimum, chart.maximum), (100, 620))
            np.testing.assert_allclose((result.computed.minimum, result.computed.maximum), (200, 200))
            image = chart.grab().toImage()
            # Both series must be visibly painted inside the plot, beyond the legend.
            colors = {image.pixelColor(x, y).name() for x in range(65, image.width() - 23)
                      for y in range(43, image.height() - 40)}
            self.assertIn("#176c59", colors)
            self.assertIn("#b86a22", colors)
            window.close()

    def test_chart_wheel_drag_reset_and_detail_after_zoom(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'test.gpx'
            path.write_bytes(SYNTHETIC_GPX)
            prepared = prepare(parse_gpx(path))
            ProfileCache(root / 'profiles').save(Source.IGN, prepared.coordinates, 100 + .1 * prepared.segments[0].distance)
            result = calculate(path, root, online=False)
            window = MainWindow(root, restore=False)
            window.show_result(result)
            window.show()
            app.processEvents()
            chart = window.chart
            full = chart.bounds
            center = chart.chart_rect().center()
            wheel = QWheelEvent(center, QPointF(chart.mapToGlobal(center.toPoint())), QPoint(), QPoint(0, 120),
                                Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
            app.sendEvent(chart, wheel)
            self.assertLess(chart.view[1] - chart.view[0], full[1] - full[0])
            zoomed = chart.view
            QTest.mousePress(chart, Qt.MouseButton.LeftButton, pos=center.toPoint())
            QTest.mouseMove(chart, (center + QPointF(20, 10)).toPoint())
            QTest.mouseRelease(chart, Qt.MouseButton.LeftButton, pos=(center + QPointF(20, 10)).toPoint())
            self.assertNotEqual(chart.view, zoomed)
            chart.pan(100000, -100000)
            self.assertGreaterEqual(chart.view[0], full[0])
            self.assertLessEqual(chart.view[1], full[1])
            self.assertGreaterEqual(chart.view[2], full[2])
            self.assertLessEqual(chart.view[3], full[3])
            view = chart.view
            window.language_picker.setCurrentIndex(1 - window.language_picker.currentIndex())
            self.assertEqual(chart.view, view)
            QTest.mouseClick(window.reset_view_button, Qt.MouseButton.LeftButton)
            self.assertEqual(chart.view, full)
            self.assertFalse(window.reset_view_button.isEnabled())
            # Zoomed drawing uses all native observations in view, rather than a fixed overview.
            dense = Profile(np.arange(10000.0), np.sin(np.arange(10000.0)))
            detail = chart.display_points(dense, 5000, 5010)
            np.testing.assert_array_equal(detail[:, 0], np.arange(4999, 5012))
            window.close()

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
