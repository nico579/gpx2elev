from datetime import timedelta, timezone
import unittest

import numpy as np

from gpx2elev.chart_data import ChartObservations, local_time
from gpx2elev.core import Segment, Track, compute, parse_gpx, parse_time, prepare


class ChartDataTests(unittest.TestCase):
    def test_parser_reads_utc_offsets_fractional_and_missing_times(self):
        track = parse_gpx(b'''<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
            <trkpt lat="45" lon="5"><time>2026-10-08T10:00:00.123Z</time><extensions><time>1999-01-01T00:00:00Z</time></extensions></trkpt>
            <trkpt lat="45" lon="5.001"><time>2026-10-08T12:00:00.123+02:00</time></trkpt>
            <trkpt lat="45" lon="5.002"><time>2026-10-08T10:00:00</time></trkpt>
            <trkpt lat="45" lon="5.003"><x:time xmlns:x="urn:foreign">2026-10-08T10:00:00Z</x:time></trkpt>
            </trkseg></trk></gpx>''')
        times = track.segments[0].times
        self.assertEqual(times[0], times[1])
        self.assertAlmostEqual(times[0], parse_time("2026-10-08T10:00:00Z") + .123, places=5)
        self.assertTrue(np.isnan(times[2:]).all())
        for bad in (None, "bad", "2026-02-30T00:00:00Z", "2026-10-08T10:00:00+25:00"):
            self.assertTrue(np.isnan(parse_time(bad)))

    def test_time_ticks_do_not_bridge_gaps_segments_or_clock_reversals(self):
        start = parse_time("2026-10-08T10:00:00Z")
        segments = [Segment(np.array([[45., 5], [45., 5.001], [45., 5.002]]), np.array([10., 20, 30]),
                            np.array([start, start + 60, np.nan])),
                    Segment(np.array([[45., 6], [45., 6.001]]), np.array([40., 50]), np.array([start + 120, start + 90]))]
        prepared = prepare(Track(segments))
        chart = ChartObservations(prepared, compute(prepared, np.full(prepared.sample_count, 100.)).profiles)
        self.assertTrue(chart.has_time)
        self.assertEqual(chart.time_at(chart.distance[1] / 2), start + 30)
        self.assertIsNone(chart.time_at((chart.distance[1] + chart.distance[2]) / 2))
        self.assertEqual(chart.time_at(chart.distance[3]), start + 120)
        self.assertIsNone(chart.time_at((chart.distance[3] + chart.distance[4]) / 2))
        self.assertIsNone(chart.time_at(-1))
        self.assertIsNone(chart.time_at(prepared.length + 1))

    def test_cursor_selects_real_stops_and_the_matching_terrain_segment(self):
        start = parse_time("2026-10-08T10:00:00Z")
        track = Track([Segment(np.array([[45., 4]]), np.array([9999.])),
            Segment(np.array([[45., 5], [45., 5], [45., 5.001]]), np.array([10., 20, 30]), np.array([start, start + 60, start + 120])),
            Segment(np.array([[45., 6], [45., 6.001]]), np.array([400., 500]), np.array([start + 180, start + 240]))])
        prepared = prepare(track)
        values = np.r_[np.full(len(prepared.segments[0].distance), 100.), np.full(len(prepared.segments[1].distance), 200.)]
        chart = ChartObservations(prepared, compute(prepared, values).profiles)
        first = chart.select(0, 11)
        self.assertEqual((first.gpx, first.time), (10., start))
        self.assertAlmostEqual(first.terrain, 100., places=9)
        self.assertEqual(chart.select(0, 9999).terrain, None)
        second = chart.select(chart.distance[4], 400)
        self.assertEqual((second.gpx, second.time), (400., start + 180))
        self.assertAlmostEqual(second.terrain, 200., places=9)
        selected = chart.select(chart.distance[-1] - .1, 500)
        self.assertEqual(selected.distance, chart.distance[-1])
        self.assertEqual(selected.gpx, 500.)
        middle = prepared.segments[0].distance[-1] / 2
        interpolated = chart.select(middle, 100., visible=(middle - 1, middle + 1))
        self.assertTrue(interpolated.interpolated)
        self.assertEqual(interpolated.distance, middle)
        self.assertAlmostEqual(interpolated.gpx, 25., places=9)
        self.assertEqual(interpolated.time, start + 90)

    def test_missing_values_and_midnight_local_date_remain_explicit(self):
        prepared = prepare(Track([Segment(np.array([[45., 5], [45., 5.001]]), np.array([np.nan, np.nan]))]))
        computed = compute(prepared, np.full(prepared.sample_count, 100.))
        chart = ChartObservations(prepared, computed.profiles)
        point = chart.select(0, 100)
        self.assertAlmostEqual(point.terrain, 100., places=9)
        self.assertIsNone(point.time)
        self.assertIsNone(point.gpx)
        self.assertFalse(chart.has_time)
        self.assertEqual(local_time(None), "—")
        time = parse_time("2026-10-08T23:30:00Z")
        zone = timezone(timedelta(hours=2))
        self.assertEqual(local_time(time, seconds=True, date=True, zone=zone), "09/10/2026 01:30:00")
        self.assertEqual(local_time(time, seconds=True, date=True, zone=zone, language="en"), "2026-10-09 01:30:00")
        self.assertEqual(computed.gain.up, 0.)
