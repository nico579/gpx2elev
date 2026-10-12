import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from gpx2elev import __version__
from gpx2elev.update_web import UpdateManager
from gpx2elev.updates import UpdateCancelled, UpdateClient
from test_updates import metadata, Response, Session, zip_bundle


def await_idle(updates):
    deadline = time.monotonic() + 5
    while updates.worker is not None and time.monotonic() < deadline:
        time.sleep(.005)
    assert updates.worker is None, updates.snapshot()


class WebUpdateTests(unittest.TestCase):
    def test_source_mode_checks_and_downloads_the_verified_bundle_off_thread(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "fixture.zip"
            zip_bundle(archive)
            payload = archive.read_bytes()
            parts = [int(n) for n in __version__.split(".")]
            parts[-1] += 1
            version = ".".join(map(str, parts))
            client = UpdateClient(session=Session([Response(json.dumps(metadata(version=version, contents=payload)).encode()), Response(payload)]))
            updates = UpdateManager(root, lambda: None, lambda: False)
            with patch("gpx2elev.update_web.UpdateClient", return_value=client), patch("gpx2elev.updates.platform_name", return_value="windows-x64"):
                self.assertTrue(updates.check()["ok"])
                await_idle(updates)
                self.assertEqual(updates.snapshot()["release"]["version"], version)
                with patch("gpx2elev.update_web.extract_bundle", side_effect=lambda a, d, **kw:
                    __import__("gpx2elev.updates", fromlist=["extract_bundle"]).extract_bundle(a, d, system="win32", **kw)):
                    self.assertTrue(updates.download()["ok"])
                    await_idle(updates)
                self.assertEqual(updates.snapshot()["prepared"], "folder")
                self.assertEqual((updates.prepared["folder"] / "gpx2elev.exe").read_bytes(), b"new binary")
                with patch("webbrowser.open") as opened:
                    self.assertTrue(updates.open_folder()["ok"])
                    self.assertTrue(opened.call_args.args[0].startswith("file:"))
            updates.close()

    def test_cancelled_check_and_network_failure_allow_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            updates = UpdateManager(directory, lambda: None, lambda: False)
            entered = threading.Event()

            def slow(client, *args):
                entered.set()
                client.cancel.wait(3)
                raise UpdateCancelled()

            with patch.object(UpdateClient, "check", slow):
                updates.check()
                self.assertTrue(entered.wait(1))
                self.assertIn("error", updates.check())
                updates.cancel()
                await_idle(updates)
                self.assertEqual(updates.snapshot()["phase"], "cancelled")
            import requests
            with patch.object(UpdateClient, "check", side_effect=requests.ConnectionError()):
                updates.check()
                await_idle(updates)
                self.assertEqual(updates.snapshot()["phase"], "error")
            with patch.object(UpdateClient, "check", return_value=None):
                updates.check()
                await_idle(updates)
                self.assertEqual(updates.snapshot()["phase"], "latest")
            updates.close()

    def test_install_requires_confirmation_idle_calculation_and_ready_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            stopped = []
            busy = [True]
            updates = UpdateManager(directory, lambda: stopped.append(True), lambda: busy[0])
            updates.prepared = {"plan": Path(directory) / "plan.json"}
            with patch("gpx2elev.update_web.launch_helper") as helper:
                self.assertIn("error", updates.install({}))
                self.assertIn("error", updates.install({"confirm": True}))
                helper.assert_not_called()
                busy[0] = False
                self.assertTrue(updates.install({"confirm": True})["ok"])
                helper.assert_called_once_with(updates.prepared["plan"])
                self.assertEqual(stopped, [True])
                self.assertEqual(updates.pending_update, updates.prepared["plan"])
                self.assertIn("error", updates.install({"confirm": True}))
            updates.close()
