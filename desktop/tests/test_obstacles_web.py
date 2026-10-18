"""Obstacle lookup lifecycle must not invalidate the elevation result."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from gpx2elev.core import parse_gpx, prepare
from gpx2elev.providers import ProfileCache, Source
from gpx2elev.smoke import SYNTHETIC_GPX
from gpx2elev.web import Application


def idle(app):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        with app.lock:
            if not app.busy() and not app.obstacle_workers and app.obstacle_report["state"] != "loading":
                return
        time.sleep(.005)
    raise AssertionError(app.snapshot())


class ObstacleWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        path = self.root / "route.gpx"
        path.write_bytes(SYNTHETIC_GPX)
        prepared = prepare(parse_gpx(path))
        ProfileCache(self.root / "profiles").save(Source.IGN, prepared.coordinates, 100 + .1 * prepared.segments[0].distance)
        self.app = Application(self.root, online=False)
        self.app.open_path(path)
        idle(self.app)

    def tearDown(self):
        self.app.close()
        self.tmp.cleanup()

    def test_route_available_and_offline_is_unknown_not_clear(self):
        result = self.app.get_result()
        self.assertTrue(result["route"]["segments"])
        self.assertEqual(result["route"]["length_m"], result["summary"]["distance_m"])
        self.assertEqual(self.app.get_obstacles()["state"], "unavailable")
        self.assertTrue(self.app.snapshot()["has_result"])
        self.assertIn("obstacles", self.app.routes()[0])
        self.assertIn("obstacles", self.app.routes()[1])

    def test_bad_options_do_not_launch_a_job(self):
        for payload in ([], {"mode": "hovercraft"}, {"reverse": 1}, {"online": "yes"}, {"refresh": "yes"}):
            self.assertIn("error", self.app.check_obstacles(payload))
        self.assertFalse(self.app.obstacle_workers)

    def test_network_failure_preserves_elevation_and_reports_unknown(self):
        result = self.app.get_result()
        with patch("gpx2elev.web.obstacles.obtain", side_effect=OSError("network")):
            self.assertEqual(self.app.check_obstacles({"online": True}), {"ok": True})
            idle(self.app)
        self.assertEqual(self.app.get_result(), result)
        self.assertEqual(self.app.get_obstacles()["state"], "error")
        self.assertEqual(self.app.snapshot()["phase"], "done")

    def test_superseded_lookup_cannot_overwrite_new_direction(self):
        entered, release = threading.Event(), threading.Event()
        def obtain(prepared, directory, online, mode, reverse, cancel, refresh):
            if not reverse:
                entered.set()
                release.wait(2)
            return {"state": "ready", "events": [], "mode": mode, "reverse": reverse}
        with patch("gpx2elev.web.obstacles.obtain", side_effect=obtain):
            self.app.check_obstacles({"reverse": False})
            self.assertTrue(entered.wait(1))
            self.app.check_obstacles({"reverse": True})
            release.set()
            idle(self.app)
        self.assertTrue(self.app.get_obstacles()["reverse"])

    def test_clear_cache_waits_for_active_lookup_and_cancel_works(self):
        entered = threading.Event()
        def obtain(prepared, directory, online, mode, reverse, cancel, refresh):
            entered.set()
            cancel.wait(2)
            from gpx2elev.providers import Cancelled
            raise Cancelled()
        with patch("gpx2elev.web.obstacles.obtain", side_effect=obtain):
            self.app.check_obstacles({})
            self.assertTrue(entered.wait(1))
            self.assertIn("error", self.app.clear({"confirm": True}))
            self.app.cancel()
            idle(self.app)
        self.assertEqual(self.app.get_obstacles()["state"], "unavailable")
        self.assertIsNotNone(self.app.result)

    def test_close_waits_until_registered_thread_has_started(self):
        entered, release = threading.Event(), threading.Event()
        original_start = threading.Thread.start
        errors = []
        def delayed_start(worker):
            entered.set()
            release.wait(2)
            original_start(worker)
        def close():
            try:
                self.app.close()
            except Exception as exc:
                errors.append(exc)
        launcher = threading.Thread(target=lambda: self.app.check_obstacles({}))
        closer = threading.Thread(target=close)
        with patch("threading.Thread.start", autospec=True, side_effect=delayed_start):
            original_start(launcher)
            self.assertTrue(entered.wait(1))
            original_start(closer)
            release.set()
            launcher.join(3)
            closer.join(3)
        self.assertFalse(closer.is_alive())
        self.assertFalse(errors)
        self.assertIn("error", self.app.check_obstacles({}))


if __name__ == "__main__":
    unittest.main()
