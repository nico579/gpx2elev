import csv
import io
import json
import math
from pathlib import Path
import unittest

import numpy as np

from gpx2elev.core import (Gain, Track, Segment, anchors, compute, filtered_gain,
                          gaussian, parse_gpx, prepare, totals)

RESOURCES = Path(__file__).resolve().parents[2] / "app/src/test/resources"


class CoreTests(unittest.TestCase):
    def test_overflowing_gpx_interpolation_does_not_discard_valid_terrain(self):
        prepared = prepare(Track([Segment(np.array([[45, 5], [45.001, 5]]), np.array([-1e308, 1e308]))]))
        self.assertIsNone(prepared.segments[0].gpx_elevations)
        result = compute(prepared, np.full(prepared.sample_count, 100.0))
        self.assertIsNone(result.gpx_raw)
        self.assertIsNone(result.gpx_filtered)
        self.assertAlmostEqual(result.gain.up, 0.0, places=9)
        self.assertAlmostEqual(result.gain.down, 0.0, places=9)
        np.testing.assert_allclose(result.profiles[0].elevations, 100.0, atol=1e-9)

    def test_overflowing_raw_totals_and_gaussian_remain_optional_comparisons(self):
        coordinates = np.array([[45 + i * .001, 5] for i in range(7)])
        native = np.array([-8e307, 0, 8e307, 0, -8e307, 0, 8e307])
        prepared = prepare(Track([Segment(coordinates, native)]))
        result = compute(prepared, np.full(prepared.sample_count, 100.0))
        self.assertIsNone(result.gpx_raw)
        self.assertIsNone(result.gpx_filtered)
        self.assertAlmostEqual(result.minimum, 100.0, places=9)
        self.assertAlmostEqual(result.maximum, 100.0, places=9)
        constant = prepare(Track([Segment(coordinates[:2], np.array([1e308, 1e308]))]))
        result = compute(constant, np.full(constant.sample_count, 100.0))
        self.assertEqual(result.gpx_raw, Gain(0.0, 0.0))
        self.assertIsNone(result.gpx_filtered)

    def test_linear_and_constant_including_short_segments(self):
        for length in (1.3, 4.9, 5, 10.1, 79.9, 1003.7):
            x = np.unique(np.r_[np.arange(0, length, 5), length])
            for sigma in (0, 15, 20, 25, 50):
                np.testing.assert_allclose(gaussian(x, np.full(len(x), 100), sigma), 100, atol=1e-10)
                np.testing.assert_allclose(gaussian(x, 100 + .2 * x, sigma), 100 + .2 * x, atol=1e-10)

    def test_hysteresis_preserves_progressive_rise_and_confirms_reversals(self):
        np.testing.assert_array_equal(anchors(np.arange(101) * .1), [0, 100])
        z = np.array([0, 1, 2, 3, 2, 4, 2, 3, 1, 2, 3])
        np.testing.assert_array_equal(anchors(z), [0, 5, 8, 10])
        self.assertEqual(totals(z[anchors(z)]), Gain(6, 3))
        # Retain unconfirmed terminal movement, as in the Android/reference convention.
        self.assertEqual(totals(np.array([0, 1])[anchors([0, 1])]), Gain(1, 0))

    def test_separate_segments_no_vertical_jump_at_gap(self):
        track = Track([Segment(np.array([[45, 5], [45.001, 5]]), np.array([0, 10.])),
                       Segment(np.array([[46, 5], [46.001, 5]]), np.array([1000, 1010.]))])
        prepared = prepare(track)
        z = np.concatenate([s.gpx_elevations for s in prepared.segments])
        result = compute(prepared, z)
        self.assertAlmostEqual(result.gain.up, 20, places=8)
        self.assertAlmostEqual(result.gain.down, 0, places=8)
        self.assertEqual(result.gpx_raw, Gain(20, 0))

    def test_stationary_points_last_sample_raw_keeps_all(self):
        track = Track([Segment(np.array([[45, 5], [45, 5], [45.001, 5]]), np.array([100, 102, 112.]))])
        prepared = prepare(track)
        self.assertEqual(prepared.segments[0].gpx_elevations[0], 102)
        result = compute(prepared, prepared.segments[0].gpx_elevations)
        self.assertEqual(result.gpx_raw, Gain(12, 0))
        self.assertAlmostEqual(result.gpx_filtered.up, 10, places=9)

    def test_antimeridian_interpolation_stays_near_dateline(self):
        prepared = prepare(Track([Segment(np.array([[10, 179.999], [10, -179.999]]), np.array([0, 1.]))]))
        self.assertTrue(np.all(np.abs(prepared.coordinates[:, 1]) > 179.9))
        self.assertLess(prepared.length, 250)

    def test_parser_namespaces_routes_and_missing_altitude(self):
        data = b'<g:gpx xmlns:g="http://www.topografix.com/GPX/1/0"><g:rte><g:rtept lat="45" lon="5"><g:ele>-10</g:ele></g:rtept><g:rtept lat="45.001" lon="5"/></g:rte></g:gpx>'
        prepared = prepare(parse_gpx(data))
        result = compute(prepared, np.zeros(prepared.sample_count))
        self.assertIsNone(result.gpx_raw)
        self.assertIsNone(result.gpx_filtered)
        self.assertEqual(prepared.track.point_count, 2)

    def test_parser_rejects_invalid_xml_coordinate_and_dtd(self):
        for data in (b"<html/>", b'<!DOCTYPE gpx [<!ENTITY x "bad">]><gpx/>',
                     b'<gpx><trk><trkseg><trkpt lat="nan" lon="5"/><trkpt lat="45" lon="5"/></trkseg></trk></gpx>',
                     b'<gpx xmlns="urn:not-gpx"><rte><rtept lat="45" lon="5"/></rte></gpx>'):
            with self.assertRaises(ValueError):
                parse_gpx(data)

    def test_balance_and_reverse_on_nontrivial_profile(self):
        x = np.r_[np.arange(0, 1000, 5), 1003.7]
        z = 500 + 40 * np.sin(x / 45) + .02 * x
        gain, filtered = filtered_gain(x, z)
        self.assertAlmostEqual(gain.up - gain.down, filtered[-1] - filtered[0], places=10)
        reverse = totals(filtered[::-1][anchors(filtered[::-1])])
        self.assertAlmostEqual(reverse.up, gain.down, places=9)
        self.assertAlmostEqual(reverse.down, gain.up, places=9)

    @unittest.skipUnless((RESOURCES / "reference.gpx").exists(), "Trace personnelle locale absente")
    def test_complete_archived_android_and_python_reference(self):
        prepared = prepare(parse_gpx(RESOURCES / "reference.gpx"))
        with (RESOURCES / "reference.csv").open(encoding="utf-8") as stream:
            rows = list(csv.DictReader(stream))
        values = np.array([float(row["ign"]) for row in rows])
        expected = json.loads((RESOURCES / "reference_expected.json").read_text(encoding="utf-8"))
        result = compute(prepared, values)
        self.assertEqual(prepared.sample_count, expected["samples"])
        np.testing.assert_allclose(prepared.coordinates, [[float(r["lat"]), float(r["lon"])] for r in rows], atol=1e-11, rtol=0)
        np.testing.assert_allclose(result.profiles[0].elevations, [float(r["ign_filtered"]) for r in rows], atol=1e-8, rtol=0)
        self.assertAlmostEqual(prepared.length, expected["distance"], places=7)
        for actual, key in ((result.gain.up, "up"), (result.gain.down, "down"),
                            (result.gpx_raw.up, "raw_gpx_up"), (result.gpx_raw.down, "raw_gpx_down"),
                            (result.gpx_filtered.up, "filtered_gpx_up"), (result.gpx_filtered.down, "filtered_gpx_down")):
            self.assertAlmostEqual(actual, expected[key], places=7)


if __name__ == "__main__":
    unittest.main()
