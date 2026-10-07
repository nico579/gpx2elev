import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from gpx2elev.ui import DesktopApplication, MainWindow
from gpx2elev import __version__
from gpx2elev.updates import UpdateCancelled, UpdateClient
from test_updates import metadata, Response, Session, zip_bundle


class UpdateUiTests(unittest.TestCase):
    def await_idle(self, app, dialog):
        deadline = time.monotonic() + 5
        while dialog.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.005)
        app.processEvents()
        self.assertIsNone(dialog.worker)

    def test_button_checks_downloads_verifies_and_opens_folder_in_source_mode(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "fixture.zip"
            zip_bundle(archive)
            payload = archive.read_bytes()
            version_parts = [int(n) for n in __version__.split(".")]
            version_parts[-1] += 1
            next_version = ".".join(map(str, version_parts))
            client = UpdateClient(session=Session([Response(json.dumps(metadata(version=next_version, contents=payload)).encode()), Response(payload)]))
            window = MainWindow(root / "data", restore=False)
            window.language_picker.setCurrentIndex(0)
            window.show()
            with patch("gpx2elev.update_ui.UpdateClient", return_value=client), patch("gpx2elev.updates.platform_name", return_value="windows-x64"):
                QTest.mouseClick(window.updates_button, Qt.MouseButton.LeftButton)
                dialog = window.update_dialog
                self.await_idle(app, dialog)
                self.assertIn(next_version, dialog.status_label.text())
                self.assertEqual(dialog.action_button.text(), "Télécharger")
                window.language_picker.setCurrentIndex(1)
                self.assertEqual(dialog.windowTitle(), "Updates")
                self.assertIn("available", dialog.status_label.text())
                with patch("gpx2elev.update_ui.extract_bundle", side_effect=lambda archive, destination, **kw:
                           __import__("gpx2elev.updates", fromlist=["extract_bundle"]).extract_bundle(archive, destination, system="win32", **kw)):
                    QTest.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)
                    self.await_idle(app, dialog)
                self.assertEqual(dialog.action_button.text(), "Open folder")
                folder = dialog.prepared["folder"]
                self.assertEqual((folder / "gpx2elev.exe").read_bytes(), b"new binary")
                with patch("gpx2elev.update_ui.QDesktopServices.openUrl", return_value=True) as open_url:
                    QTest.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)
                    self.assertEqual(Path(open_url.call_args.args[0].toLocalFile()), folder.parent)
            dialog.reject()
            app.processEvents()
            self.assertIsNone(window.update_dialog)
            window.close()

    def test_latest_version_and_network_failure_offer_an_explicit_retry(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(directory, restore=False)
            window.language_picker.setCurrentIndex(1)
            with patch("gpx2elev.update_ui.UpdateClient.check", return_value=None):
                window.open_updates()
                dialog = window.update_dialog
                self.await_idle(app, dialog)
                self.assertIn("latest published version", dialog.status_label.text())
                self.assertFalse(dialog.action_button.isVisible())
            import requests
            with patch("gpx2elev.update_ui.UpdateClient.check", side_effect=requests.ConnectionError()):
                dialog.check()
                self.await_idle(app, dialog)
                self.assertIn("Check your Internet connection", dialog.status_label.text())
                self.assertTrue(dialog.check_button.isEnabled())
                self.assertIsNone(dialog.prepared)
            dialog.reject()
            window.close()

    def test_window_close_cancels_worker_before_destroying_dialog(self):
        app = DesktopApplication.instance() or DesktopApplication(["gpx2elev-test"])
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(directory, restore=False)
            window.show()
            def slow_check(client, *args):
                deadline = time.monotonic() + 5
                while not client.cancel.is_set() and time.monotonic() < deadline:
                    time.sleep(.005)
                raise UpdateCancelled()
            with patch.object(UpdateClient, "check", slow_check):
                window.open_updates()
                dialog = window.update_dialog
                window.close()
                self.await_idle(app, dialog)
            app.processEvents()
            self.assertFalse(window.isVisible())
            self.assertIsNone(window.update_dialog)
