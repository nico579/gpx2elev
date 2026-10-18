"""Deterministic obstacle geometry and cache tests."""
import json
import tempfile
import threading
import unittest
from unittest.mock import patch

import numpy as np

from gpx2elev.core import Segment, Track, prepare
from gpx2elev import obstacles
from gpx2elev.providers import Cancelled

METERS = 111195.08


def coordinate(x, y=0):
    return (y / METERS, x / METERS)


def track(*segments):
    return prepare(Track([Segment(np.array([coordinate(*p) for p in points]),
                                  np.zeros(len(points))) for points in segments]))


def node(osm_id, x, y=0, **tags):
    lat, lon = coordinate(x, y)
    return {"type": "node", "id": osm_id, "lat": lat, "lon": lon, "tags": tags}


def way(osm_id, points, nodes=None, **tags):
    return {"type": "way", "id": osm_id, "nodes": nodes or list(range(100, 100 + len(points))),
            "geometry": [dict(zip(("lat", "lon"), coordinate(*p))) for p in points], "tags": tags}


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.route = track([(0, 0), (100, 0)])

    def test_conditional_oneway_is_not_a_definite_block(self):
        parent = {"oneway": "yes", "oneway:conditional": "no @ (Sa-Su)"}
        self.assertEqual(obstacles.status({"barrier": "gate", "bicycle": "yes"}, "bicycle", "backward", parent)[0], "uncertain")
        self.assertEqual(obstacles.status({"barrier": "gate", "foot": "yes"}, "foot", "backward", parent)[0], "passable")
        parent = {"oneway:foot": "yes", "oneway:foot:conditional": "no @ (Sa-Su)"}
        self.assertEqual(obstacles.status({"barrier": "gate", "foot": "yes"}, "foot", "backward", parent)[0], "uncertain")

    def test_crossed_fence_is_blocked_with_local_red_interval(self):
        events = obstacles.analyze(self.route, [way(1, [(40, -20), (40, 20)], barrier="fence")])
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event["status"], "blocked")
        self.assertEqual(event["segment"], 0)
        self.assertAlmostEqual(event["distance_m"], 40, delta=.01)
        self.assertAlmostEqual(event["start_m"], 15, delta=.01)
        self.assertAlmostEqual(event["end_m"], 65, delta=.01)

    def test_parallel_fence_does_not_block(self):
        for points in ([(10, 2), (80, 2)], [(10, 0), (80, 0)]):
            with self.subTest(points=points):
                self.assertEqual(obstacles.analyze(self.route, [way(1, points, barrier="fence")]), [])

    def test_crossing_at_sample_vertex_is_not_duplicated(self):
        events = obstacles.analyze(self.route, [way(1, [(50, -20), (50, 20)], barrier="fence")])
        self.assertEqual(len(events), 1)

    def test_permitted_gate_on_fence_supersedes_solid_geometry(self):
        fence = way(1, [(40, -20), (40, 0), (40, 20)], nodes=[100, 2, 101], barrier="fence")
        gate = node(2, 40, barrier="gate", foot="yes")
        self.assertEqual(obstacles.analyze(self.route, [fence, gate]), [])

    def test_locked_gate_on_fence_remains_a_block(self):
        fence = way(1, [(40, -20), (40, 0), (40, 20)], nodes=[100, 2, 101], barrier="fence")
        gate = node(2, 40, barrier="gate", locked="yes")
        events = obstacles.analyze(self.route, [fence, gate])
        self.assertEqual([(e["osm_id"], e["status"]) for e in events], [(2, "blocked")])

    def test_unknown_gate_on_fence_remains_uncertain(self):
        fence = way(1, [(40, -20), (40, 20)], barrier="fence")
        gate = node(2, 40, barrier="gate")
        events = obstacles.analyze(self.route, [fence, gate])
        self.assertEqual([(e["osm_id"], e["status"]) for e in events], [(2, "uncertain")])

    def test_nearby_gate_off_fence_does_not_erase_crossing(self):
        fence = way(1, [(40, -20), (40, 20)], barrier="fence")
        gate = node(2, 42, barrier="gate", foot="yes")
        events = obstacles.analyze(self.route, [fence, gate])
        self.assertEqual([(e["osm_id"], e["status"]) for e in events], [(1, "blocked")])

    def test_sealed_entrance_does_not_erase_fence(self):
        fence = way(1, [(40, -20), (40, 0), (40, 20)], nodes=[100, 2, 101], barrier="fence")
        entrance = node(2, 40, entrance="no", foot="yes")
        events = obstacles.analyze(self.route, [fence, entrance])
        self.assertEqual({e["osm_id"] for e in events if e["status"] == "blocked"}, {1, 2})

    def test_limited_entrances_are_uncertain(self):
        for value in ("exit", "entrance", "emergency", "yes"):
            with self.subTest(value=value):
                events = obstacles.analyze(self.route, [node(2, 40, entrance=value)])
                self.assertEqual([e["status"] for e in events], ["uncertain"])

    def test_proximity_over_three_metres_is_uncertain_and_over_eight_ignored(self):
        event = obstacles.analyze(self.route, [node(1, 40, 4, barrier="gate", foot="no")])[0]
        self.assertEqual(event["status"], "uncertain")
        self.assertAlmostEqual(event["separation_m"], 4, places=5)
        self.assertEqual(obstacles.analyze(self.route, [node(1, 40, 9, barrier="gate", foot="no")]), [])

    def test_same_barrier_is_reported_at_each_visit_in_travel_order(self):
        route = track([(0, 0), (100, 0), (0, 0)])
        events = obstacles.analyze(route, [node(1, 30, barrier="gate", foot="no")])
        self.assertEqual(len(events), 2)
        np.testing.assert_allclose([e["distance_m"] for e in events], [30, 170], atol=.02)

    def test_disjoint_gpx_segments_are_not_joined(self):
        route = track([(0, 0), (20, 0)], [(80, 0), (100, 0)])
        self.assertEqual(obstacles.analyze(route, [way(1, [(50, -20), (50, 20)], barrier="fence")]), [])
        view = obstacles.route_view(route)
        self.assertEqual(len(view["segments"]), 2)
        self.assertAlmostEqual(view["segments"][1][0][2], 20, delta=.01)
        self.assertAlmostEqual(view["length_m"], 40, delta=.01)

    def test_short_out_and_back_keeps_both_crossings(self):
        route = track([(0, 0), (34, 0), (0, 0)])
        events = obstacles.analyze(route, [node(1, 30, barrier="gate", foot="no")])
        self.assertEqual(len(events), 2)
        np.testing.assert_allclose([e["distance_m"] for e in events], [30, 38], atol=.02)

    def test_local_interval_stays_inside_its_gpx_segment(self):
        route = track([(0, 0), (20, 0)], [(80, 0), (100, 0)])
        event = obstacles.analyze(route, [node(1, 85, barrier="gate", foot="no")])[0]
        self.assertEqual(event["segment"], 1)
        self.assertAlmostEqual(event["start_m"], 20, delta=.01)
        self.assertAlmostEqual(event["end_m"], 40, delta=.01)

    def test_reversing_changes_encounter_order_and_distance(self):
        barriers = [node(1, 20, barrier="gate", foot="no"), node(2, 70, barrier="gate", foot="no")]
        forward = obstacles.analyze(self.route, barriers)
        backward = obstacles.analyze(self.route, barriers, reverse=True)
        self.assertEqual([e["osm_id"] for e in backward], [2, 1])
        np.testing.assert_allclose([e["distance_m"] for e in backward], [30, 80], atol=.02)
        self.assertAlmostEqual(backward[0]["route_distance_m"], forward[1]["route_distance_m"], places=6)
        self.assertEqual(backward[0]["start_m"], forward[1]["start_m"])

    def test_tangential_touch_and_start_on_fence_are_uncertain(self):
        fence = way(1, [(50, -20), (50, 20)], barrier="fence")
        routes = (track([(0, 0), (50, 0), (0, 0)]), track([(50, 0), (100, 0)]))
        for route in routes:
            with self.subTest(route_length=route.length):
                events = obstacles.analyze(route, [fence])
                self.assertTrue(all(e["status"] == "uncertain" for e in events))

    def test_unknown_crossing_level_is_uncertain(self):
        event = obstacles.analyze(self.route, [way(1, [(40, -20), (40, 20)], barrier="fence", layer="1")])[0]
        self.assertEqual(event["status"], "uncertain")

    def test_antimeridian_crossing_uses_short_local_distance(self):
        route = prepare(Track([Segment(np.array([[0, 179.9995], [0, -179.9995]]), np.zeros(2))]))
        fence = {"type": "way", "id": 1, "tags": {"barrier": "fence"},
                 "geometry": [{"lat": -.0002, "lon": 180}, {"lat": .0002, "lon": 180}]}
        events = obstacles.analyze(route, [fence])
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "blocked")
        self.assertAlmostEqual(events[0]["distance_m"], route.length / 2, places=3)
        self.assertAlmostEqual(abs(events[0]["lon"]), 180, places=6)


class PermissionTests(unittest.TestCase):
    def test_explicit_foot_permission_overrides_general_access(self):
        self.assertEqual(obstacles.status({"barrier": "gate", "access": "no", "foot": "yes"}, "foot")[0], "passable")
        self.assertEqual(obstacles.status({"barrier": "gate", "access": "yes", "foot": "no"}, "foot")[0], "blocked")

    def test_unspecified_gate_is_uncertain(self):
        self.assertEqual(obstacles.status({"barrier": "gate"}, "foot")[0], "uncertain")

    def test_conditional_and_opening_hours_are_uncertain(self):
        for extra in ({"foot:conditional": "no @ (sunset-sunrise)"}, {"opening_hours": "Mo-Fr 09:00-17:00"}):
            with self.subTest(extra=extra):
                self.assertEqual(obstacles.status({"barrier": "gate", "foot": "no", **extra}, "foot")[0], "uncertain")

    def test_barrier_effect_depends_on_transport_mode(self):
        tags = {"barrier": "bollard"}
        self.assertEqual(obstacles.status(tags, "foot")[0], "passable")
        self.assertEqual(obstacles.status(tags, "motor_vehicle")[0], "blocked")

    def test_parent_directional_permission_changes_when_reversed(self):
        route = track([(0, 0), (100, 0)])
        gate = node(2, 40, barrier="gate")
        road = way(3, [(0, 0), (40, 0), (100, 0)], nodes=[1, 2, 3], highway="path",
                   **{"foot:forward": "yes", "foot:backward": "no"})
        self.assertEqual(obstacles.analyze(route, [gate, road]), [])
        events = obstacles.analyze(route, [gate, road], reverse=True)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "blocked")
        self.assertAlmostEqual(events[0]["distance_m"], 60, delta=.01)

    def test_generic_oneway_does_not_block_pedestrians(self):
        route = track([(0, 0), (100, 0)])
        gate = node(2, 40, barrier="gate", foot="yes")
        road = way(3, [(0, 0), (40, 0), (100, 0)], nodes=[1, 2, 3], highway="residential", oneway="yes")
        self.assertEqual(obstacles.analyze(route, [gate, road], reverse=True), [])

    def test_explicit_pedestrian_oneway_is_respected(self):
        route = track([(0, 0), (100, 0)])
        gate = node(2, 40, barrier="gate", foot="yes")
        road = way(3, [(0, 0), (40, 0), (100, 0)], nodes=[1, 2, 3], highway="path", **{"oneway:foot": "yes"})
        events = obstacles.analyze(route, [gate, road], reverse=True)
        self.assertEqual(events[0]["status"], "blocked")

    def test_unresolved_direction_is_uncertain(self):
        self.assertEqual(obstacles.status({"barrier": "gate", "foot:forward": "no"}, "foot")[0], "uncertain")


class ResponseTests(unittest.TestCase):
    def test_server_remark_rejects_partial_data(self):
        with self.assertRaisesRegex(ValueError, "incomplète"):
            obstacles.validate_response({"remark": "runtime error: Query timed out", "elements": []})

    def test_incomplete_and_malformed_responses_are_rejected(self):
        responses = ({}, [], {"elements": {}},
                     {"elements": [{"type": "node", "id": 1, "tags": {"barrier": "gate"}}]},
                     {"elements": [node(1, 0, barrier=42)]},
                     {"elements": [{"type": "node", "id": 1, "lat": float("nan"), "lon": 0}]},
                     {"elements": [{"type": "way", "id": 1, "geometry": []}]})
        for response in responses:
            with self.subTest(response=response), self.assertRaises(ValueError):
                obstacles.validate_response(response)

    def test_empty_complete_response_is_valid(self):
        self.assertEqual(obstacles.validate_response({"elements": []}), {"elements": []})

    def test_queries_keep_disjoint_segments_separate(self):
        route = track([(0, 0), (20, 0)], [(1000, 0), (1020, 0)])
        queries = obstacles.queries(route)
        self.assertEqual(len(queries), 2)
        self.assertIn('node["barrier"]', queries[0])
        self.assertIn('way(bn.barriers)["highway"]', queries[0])
        self.assertIn("out body geom", queries[0])


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.route = track([(0, 0), (100, 0)])
        self.now = 1_800_000_000
        self.http_patch = patch("gpx2elev.obstacles.Http")
        self.http_class = self.http_patch.start()
        self.addCleanup(self.http_patch.stop)
        self.http = self.http_class.return_value
        self.http.fetch.return_value = (json.dumps({"elements": [node(1, 40, barrier="gate", foot="no")]}).encode(), {})
        self.clock_patch = patch("gpx2elev.obstacles.time.time", return_value=self.now)
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)

    def cache(self, age=0, **extra):
        data = {"fetched_at": self.now - age, "elements": [node(1, 20, barrier="gate", foot="no")], **extra}
        path = obstacles.cache_path(self.route, self.directory.name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def obtain(self, **options):
        return obstacles.obtain(self.route, self.directory.name, **options)

    def test_offline_without_cache_is_unavailable_and_never_fetches(self):
        result = self.obtain(online=False)
        self.assertEqual(result["state"], "unavailable")
        self.http.fetch.assert_not_called()
        self.http.close.assert_called_once()

    def test_fresh_cache_is_reused_and_direction_is_recomputed(self):
        self.cache()
        result = self.obtain(reverse=True)
        self.assertTrue(result["from_cache"])
        self.assertFalse(result["stale"])
        self.assertAlmostEqual(result["events"][0]["distance_m"], 80, delta=.01)
        self.http.fetch.assert_not_called()

    def test_stale_cache_is_marked_when_offline(self):
        self.cache(age=obstacles.TTL + 1)
        result = self.obtain(online=False)
        self.assertEqual(result["state"], "ready")
        self.assertTrue(result["stale"])
        self.http.fetch.assert_not_called()

    def test_stale_cache_is_refetched_with_form_post_when_online(self):
        self.cache(age=obstacles.TTL + 1)
        result = self.obtain()
        self.assertFalse(result["from_cache"])
        self.assertFalse(result["stale"])
        self.assertAlmostEqual(result["events"][0]["distance_m"], 40, delta=.01)
        self.http.fetch.assert_called_once()
        args, kwargs = self.http.fetch.call_args
        self.assertEqual(args, (obstacles.ENDPOINT,))
        self.assertEqual(kwargs["max_bytes"], obstacles.MAX_BYTES)
        self.assertEqual(kwargs["timeout"], (10, 40))
        self.assertEqual(kwargs["form"]["data"], obstacles.queries(self.route)[0])

    def test_refresh_forces_online_fetch_despite_fresh_cache(self):
        self.cache()
        self.assertFalse(self.obtain(refresh=True)["from_cache"])
        self.http.fetch.assert_called_once()

    def test_future_or_malformed_cache_is_not_treated_as_verified(self):
        for data in ({"fetched_at": self.now + 3600}, {"remark": "incomplete"}):
            with self.subTest(data=data):
                self.cache(**data)
                self.assertEqual(self.obtain(online=False)["state"], "unavailable")
        self.http.fetch.assert_not_called()

    def test_network_failure_does_not_replace_existing_cache(self):
        path = self.cache(age=obstacles.TTL + 1)
        old = path.read_bytes()
        self.http.fetch.side_effect = OSError("network unavailable")
        with self.assertRaises(OSError):
            self.obtain()
        self.assertEqual(path.read_bytes(), old)
        self.http.close.assert_called_once()

    def test_partial_overpass_response_is_not_saved(self):
        self.http.fetch.return_value = (b'{"elements": [], "remark": "timed out"}', {})
        with self.assertRaisesRegex(ValueError, "incomplète"):
            self.obtain()
        self.assertFalse(obstacles.cache_path(self.route, self.directory.name).exists())
        self.http.close.assert_called_once()

    def test_download_size_error_is_not_saved(self):
        self.http.fetch.side_effect = ValueError("Téléchargement trop volumineux.")
        with self.assertRaisesRegex(ValueError, "volumineux"):
            self.obtain()
        self.assertFalse(obstacles.cache_path(self.route, self.directory.name).exists())
        self.http.close.assert_called_once()

    def test_cancel_before_analysis_closes_http_without_fetch(self):
        cancel = threading.Event()
        cancel.set()
        self.http.check.side_effect = Cancelled("Calcul annulé.")
        with self.assertRaises(Cancelled):
            self.obtain(cancel=cancel)
        self.http_class.assert_called_once_with(cancel)
        self.http.fetch.assert_not_called()
        self.http.close.assert_called_once()

    def test_cancellation_during_analysis_propagates(self):
        self.cache()
        calls = 0

        def check():
            nonlocal calls
            calls += 1
            if calls == 4:
                raise Cancelled("Calcul annulé.")

        self.http.check.side_effect = check
        with self.assertRaises(Cancelled):
            self.obtain()
        self.http.close.assert_called_once()

    def test_cache_key_preserves_segment_boundaries(self):
        whole = track([(0, 0), (100, 0)])
        split = track([(0, 0), (50, 0)], [(50, 0), (100, 0)])
        self.assertNotEqual(obstacles.cache_path(whole, self.directory.name),
                            obstacles.cache_path(split, self.directory.name))


if __name__ == "__main__":
    unittest.main()
