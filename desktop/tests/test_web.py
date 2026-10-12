import base64
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

import numpy as np
from nico579_commons import serveweb, tray

from gpx2elev.core import parse_gpx, prepare
from gpx2elev.i18n import CATALOG, number, translate
from gpx2elev.providers import Cancelled, ProfileCache, Source
from gpx2elev.runtime import GUI, data_directory
from gpx2elev.service import calculate
from gpx2elev.smoke import SYNTHETIC_GPX, run_smoke
from gpx2elev.web import Application, start_server, tray_actions


def await_idle(app):
    deadline = time.monotonic() + 10
    while app.worker is not None and time.monotonic() < deadline:
        time.sleep(.005)
    assert app.worker is None, app.snapshot()


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.path = self.root / "original.gpx"
        self.path.write_bytes(SYNTHETIC_GPX)
        prepared = prepare(parse_gpx(self.path))
        ProfileCache(self.root / "profiles").save(Source.IGN, prepared.coordinates, 100 + .1 * prepared.segments[0].distance)
        self.app = Application(self.root, online=False)
        self.server, self.port = start_server(self.app)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.app.close()
        self.server.shutdown()
        self.server.server_close()
        self.temporary.cleanup()

    def request(self, route, payload=None, headers=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{route}",
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Content-Type": "application/json", **(headers or {})})
        with self.opener.open(request, timeout=5) as response:
            data = response.read()
            return json.loads(data) if route.startswith("/api/") else data

    def upload(self, data=SYNTHETIC_GPX, name="original.gpx"):
        result = self.request("/api/upload", {"name": name, "content": base64.b64encode(data).decode(), "online": False})
        self.assertTrue(result["ok"])
        await_idle(self.app)
        return self.request("/api/result")

    def test_http_upload_matches_the_same_calculation_and_exports_as_the_old_gui(self):
        expected = calculate(self.path, self.root, online=False)
        result = self.upload()
        self.assertEqual(result["summary"], expected.summary())
        self.assertEqual(result["chart"]["native"]["y"], [100, 110, 120])
        self.assertEqual(result["chart"]["terrain"][0]["x"], expected.computed.profiles[0].distance.tolist())
        x = result["chart"]["native"]["x"][1]
        cursor = self.request(f"/api/select?x={x}&y=110&left=0&right=300")
        self.assertEqual(cursor["gpx"], 110)
        self.assertIsNotNone(cursor["terrain"])
        self.assertEqual(cursor["time"], result["chart"]["native"]["time"][1])
        for kind, rows in (("summary", 3), ("profile", expected.prepared.sample_count)):
            export = self.request("/api/export?kind=" + kind)
            self.assertTrue(export["content"].startswith("\ufeff"))
            self.assertEqual(len(list(csv.DictReader(io.StringIO(export["content"].lstrip("\ufeff")), delimiter=";"))), rows)
        self.assertEqual(json.loads(self.request("/api/export?kind=json")["content"]), expected.summary())

    def test_restore_keeps_original_filename_and_never_needs_the_original_file(self):
        self.upload(name="../../randonnée.gpx")
        self.path.unlink()
        self.app.open_path(self.root / "last.gpx", online=False)
        await_idle(self.app)
        self.assertEqual(self.app.result.filename, "randonnée.gpx")
        self.assertTrue(self.app.result.series.from_cache)

    def test_clear_cache_requires_confirmation_and_preserves_result_settings_and_last_track(self):
        result = self.upload()
        self.request("/api/langue", {"code": "en"})
        settings = (self.root / "settings.json").read_bytes()
        self.assertIn("error", self.request("/api/clear-cache", {}))
        self.assertTrue(self.request("/api/clear-cache", {"confirm": True})["ok"])
        await_idle(self.app)
        self.assertEqual(sum(self.app.cache_bytes.values()), 0)
        self.assertEqual(self.request("/api/result"), result)
        self.assertEqual((self.root / "settings.json").read_bytes(), settings)
        self.assertEqual((self.root / "last.gpx").read_bytes(), SYNTHETIC_GPX)
        self.assertEqual(self.request("/api/export?kind=summary")["name"], "original_resultats.csv")

    def test_invalid_imports_are_errors_and_cannot_replace_the_last_valid_track(self):
        self.upload()
        for payload in ([], {"name": "a.txt", "content": ""}, {"name": "a.gpx", "content": "???"},
                        {"name": "a.gpx", "content": "", "online": "false"},
                        {"name": "a.gpx", "content": "", "model": "unknown"}):
            self.assertIn("error", self.request("/api/upload", payload))
        self.upload(b"<gpx><trk><trkseg>", "invalid.gpx")
        self.assertEqual(self.app.snapshot()["phase"], "error")
        self.assertFalse(self.app.snapshot()["has_result"])
        self.assertEqual((self.root / "last.gpx").read_bytes(), SYNTHETIC_GPX)
        self.assertIn("error", self.request("/api/select?x=bad&y=0&left=0&right=1"))

    def test_website_cannot_act_on_the_local_api_and_static_assets_are_all_served(self):
        for route in ("/api/state", "/api/langue"):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request(route, headers={"Origin": "https://example.com"})
            self.assertEqual(error.exception.code, 403)
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.request("/api/clear-cache", {"confirm": True}, {"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(error.exception.code, 403)
        for route in ("/", "/chart.js", "/style.css", "/app.js", "/web_bridge.js", "/nico579-langue.js", "/favicon.ico", "/NotoSans.ttf"):
            self.assertTrue(self.request(route))
        self.assertTrue(serveweb.instance_existante("gpx2elev", "127.0.0.1", self.port))
        self.assertFalse(serveweb.instance_existante("gpxsolar", "127.0.0.1", self.port))

    def test_cancellation_and_a_second_file_open_are_not_lost(self):
        entered = threading.Event()
        original = calculate

        def slow(path, directory, online, source, progress, cancel):
            if not entered.is_set():
                entered.set()
                cancel.wait(5)
                raise Cancelled()
            return original(path, directory, online, source, progress, cancel)

        with patch("gpx2elev.web.calculate", side_effect=slow):
            self.app.open_path(self.path)
            self.assertTrue(entered.wait(2))
            self.assertIn("error", self.request("/api/clear-cache", {"confirm": True}))
            self.assertIn("error", self.request("/api/recalculate", {}))
            second = self.root / "second.gpx"
            second.write_bytes(SYNTHETIC_GPX)
            self.assertTrue(self.request("/api/open", {"path": str(second), "online": False})["queued"])
            await_idle(self.app)
        self.assertEqual(self.app.result.filename, "second.gpx")
        self.assertEqual(self.app.snapshot()["phase"], "done")

    def test_language_uses_the_common_routes_and_preserves_other_settings(self):
        (self.root / "settings.json").write_text('{"other": 42, "language": "fr"}')
        self.assertEqual(self.request("/api/langue")["code"], "fr")
        self.request("/api/langue", {"code": "en"})
        self.assertEqual(json.loads((self.root / "settings.json").read_text()), {"language": "en", "other": 42})
        self.assertFalse(self.request("/api/langue", {"code": "xx"})["ok"])
        self.assertEqual(CATALOG, json.loads((Path(__file__).resolve().parents[2] / "app/src/main/assets/translations.json").read_text(encoding="utf-8")))
        self.assertEqual(translate("Coordonnées invalides au point 42.", "en"), "Invalid coordinates at point 42.")
        self.assertEqual(number(1234.5, 1, "fr"), "1\u202f234,5")

    def test_common_tray_has_the_same_entries_and_callbacks(self):
        actions = tray_actions(self.app, "http://127.0.0.1:8769/", ["python", "launcher.py"])
        self.assertIsInstance(actions, tray.Actions)
        fake = types.SimpleNamespace(MenuItem=lambda text, action, **kw: (text, action))
        entries = tray.entrees(actions, fake, lambda action: action())
        words = tray.libelles("fr")
        self.assertEqual([entry[0] for entry in entries], [words[k] for k in ("ouvrir", "redemarrer", "arreter", "raccourci")])
        with patch("webbrowser.open") as opened:
            actions.ouvrir()
            actions.mettre_a_jour()
            self.assertEqual(opened.call_args_list[0].args[0], "http://127.0.0.1:8769/")
            self.assertEqual(opened.call_args_list[1].args[0], "http://127.0.0.1:8769/?updates=1")
        with patch("nico579_commons.raccourci.creer") as shortcut:
            actions.creer_raccourci()
            self.assertEqual(shortcut.call_args.args[:2], ("gpx2elev", ["python", "launcher.py"]))
        with patch.object(self.app.version_checker, "disponible", return_value={"version": "9.0.0"}):
            self.app.updates.advertised = self.app.version_checker.disponible
            self.assertEqual(actions.version_disponible(), "9.0.0")
            entries = tray.entrees(actions, fake, lambda action: action())
            self.assertEqual(entries[1][0], words["maj"].format(version="9.0.0"))
        actions.redemarrer()
        self.assertTrue(self.app.restart_requested)
        self.assertTrue(self.app.stop_event.is_set())

    def test_headless_cli_has_no_qt_import_and_uses_the_existing_cache(self):
        from gpx2elev.__main__ import main
        output = self.root / "cli.json"
        with patch("sys.stdout", io.StringIO()):
            self.assertEqual(main([str(self.path), "--calculate", "--offline", "--data-dir", str(self.root), "--output", str(output)]), 0)
        self.assertEqual(json.loads(output.read_text())["terrain"], self.upload()["summary"]["terrain"])
        self.assertFalse(any(name.startswith(("PySide", "PyQt")) for name in sys.modules))

    def test_js_keeps_detail_extrema_segment_gaps_and_time_boundaries(self):
        subprocess.run(["node", str(Path(__file__).with_name("test_chart.js"))], check=True)

    def test_full_packaged_smoke_protocol(self):
        self.assertEqual(run_smoke(self.root / "report.json"), 0)


if __name__ == "__main__":
    unittest.main()
