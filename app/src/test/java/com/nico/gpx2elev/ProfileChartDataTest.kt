package com.nico.gpx2elev

import com.nico.gpx2elev.core.*
import com.nico.gpx2elev.ui.profileChartData
import com.nico.gpx2elev.ui.ProfileViewport
import com.nico.gpx2elev.ui.transformProfileViewport
import com.nico.gpx2elev.ui.visibleProfilePoints
import com.nico.gpx2elev.ui.profileTimeAt
import com.nico.gpx2elev.ui.profileTimeLabel
import com.nico.gpx2elev.ui.selectProfilePoint
import java.time.Instant
import java.time.ZoneOffset
import org.junit.Assert.*
import org.junit.Test

class ProfileChartDataTest {
    @Test fun parserReadsAbsoluteTimesOffsetsAndIgnoresMissingOrForeignTimes() {
        val xml = """<gpx xmlns="http://www.topografix.com/GPX/1/1"><trk><trkseg>
            <trkpt lat="45" lon="5"><time>2026-10-08T10:00:00.123Z</time><extensions><time>1999-01-01T00:00:00Z</time></extensions></trkpt>
            <trkpt lat="45" lon="5.001"><time>2026-10-08T12:00:00.123+02:00</time></trkpt>
            <trkpt lat="45" lon="5.002"><time>2026-10-08T10:00:00</time></trkpt>
            <trkpt lat="45" lon="5.003"><x:time xmlns:x="urn:foreign">2026-10-08T10:00:00Z</x:time></trkpt>
            </trkseg></trk></gpx>"""
        val points = GpxParser.parse(xml.byteInputStream()).segments.single()
        assertEquals(Instant.parse("2026-10-08T10:00:00.123Z"), points[0].time)
        assertEquals(points[0].time, points[1].time)
        assertNull(points[2].time)
        assertNull(points[3].time)
    }

    @Test fun timeTicksNeverBridgeMissingTimesSegmentsOrClockReversals() {
        val start = Instant.parse("2026-10-08T10:00:00Z")
        val first = listOf(point(5.0, 10.0).copy(time = start), point(5.001, 20.0).copy(time = start.plusSeconds(60)), point(5.002, 30.0))
        val second = listOf(point(6.0, 40.0).copy(time = start.plusSeconds(120)), point(6.001, 50.0).copy(time = start.plusSeconds(90)))
        val prepared = ElevationMath.prepare(Track(listOf(first, second)))
        val chart = profileChartData(prepared, ElevationMath.compute(prepared, DoubleArray(prepared.sampleCount) { 100.0 }).profiles)
        val x = chart.observations.map { it.distance }
        assertEquals(start.plusSeconds(30), profileTimeAt(chart, x[1] / 2))
        assertNull(profileTimeAt(chart, (x[1] + x[2]) / 2))
        assertEquals(start.plusSeconds(120), profileTimeAt(chart, x[3]))
        assertNull(profileTimeAt(chart, (x[3] + x[4]) / 2))
        assertNull(profileTimeAt(chart, -1.0))
        assertNull(profileTimeAt(chart, prepared.length + 1))
    }

    @Test fun cursorKeepsRecordedStopsAndUsesTheMatchingTerrainSegment() {
        val start = Instant.parse("2026-10-08T10:00:00Z")
        val prepared = ElevationMath.prepare(Track(listOf(listOf(point(4.0, 9999.0)),
            listOf(point(5.0, 10.0).copy(time = start), point(5.0, 20.0).copy(time = start.plusSeconds(60)), point(5.001, 30.0).copy(time = start.plusSeconds(120))),
            listOf(point(6.0, 400.0).copy(time = start.plusSeconds(180)), point(6.001, 500.0)))))
        val split = prepared.segments[0].distance.size
        val chart = profileChartData(prepared, ElevationMath.compute(prepared, DoubleArray(prepared.sampleCount) { if (it < split) 100.0 else 200.0 }).profiles)
        val first = selectProfilePoint(chart, 0.0, 11.0)!!
        assertEquals(10.0, first.gpx!!, 0.0)
        assertEquals(start, first.time)
        assertEquals(100.0, first.terrain!!, 1e-9)
        assertNull(selectProfilePoint(chart, 0.0, 9999.0)!!.terrain)
        val second = selectProfilePoint(chart, chart.observations[4].distance, 400.0)!!
        assertEquals(400.0, second.gpx!!, 0.0)
        assertEquals(start.plusSeconds(180), second.time)
        assertEquals(200.0, second.terrain!!, 1e-9)
        val middle = prepared.segments[0].distance.last() / 2
        val interpolated = selectProfilePoint(chart, middle, 100.0, ProfileViewport(middle - 1, middle + 1, 0.0, 200.0))!!
        assertTrue(interpolated.interpolated)
        assertEquals(middle, interpolated.distance, 0.0)
        assertEquals(25.0, interpolated.gpx!!, 1e-9)
        assertEquals(start.plusSeconds(90), interpolated.time)
    }

    @Test fun missingValuesAndLocalDatesAcrossMidnightStayExplicit() {
        val prepared = ElevationMath.prepare(Track(listOf(listOf(point(5.0, null), point(5.001, null)))))
        val computed = ElevationMath.compute(prepared, DoubleArray(prepared.sampleCount) { 100.0 })
        val chart = profileChartData(prepared, computed.profiles)
        val point = selectProfilePoint(chart, 0.0, 100.0)!!
        assertEquals(100.0, point.terrain!!, 1e-9)
        assertNull(point.time)
        assertNull(point.gpx)
        assertEquals("—", profileTimeLabel(null))
        val instant = Instant.parse("2026-10-08T23:30:00Z")
        assertEquals("09/10/2026 01:30:00", profileTimeLabel(instant, seconds = true, date = true, zone = ZoneOffset.ofHours(2)))
        assertEquals("2026-10-09 01:30:00", profileTimeLabel(instant, seconds = true, date = true, zone = ZoneOffset.ofHours(2), language = "en"))
        assertEquals(0.0, computed.gain.up, 1e-9)
    }

    private fun point(longitude: Double, altitude: Double?) = TrackPoint(GeoPoint(45.0, longitude), altitude)

    @Test fun nativeObservationsKeepStopsAndGapsWithoutConnectingSegments() {
        val first = listOf(point(5.0, 0.0), point(5.0, 20.0), point(5.0002, null),
            point(5.0005, 450.0), point(5.001, Double.NaN), point(5.0012, 300.0))
        val second = listOf(point(6.0, 500.0), point(6.001, 600.0))
        val track = Track(listOf(listOf(point(4.0, 9999.0)),
            listOf(point(4.0, -9999.0), point(4.0, -9999.0)), first, second))
        val prepared = ElevationMath.prepare(track)
        val computed = ElevationMath.compute(prepared, DoubleArray(prepared.sampleCount) { 100.0 })
        val chart = profileChartData(prepared, computed.profiles)

        assertEquals(6, chart.gpx.size)
        assertArrayEquals(doubleArrayOf(9999.0), chart.gpx[0].elevation, 0.0)
        assertArrayEquals(doubleArrayOf(-9999.0, -9999.0), chart.gpx[1].elevation, 0.0)
        assertArrayEquals(doubleArrayOf(0.0, 0.0), chart.gpx[1].distance, 0.0)
        assertArrayEquals(doubleArrayOf(0.0, 20.0), chart.gpx[2].elevation, 0.0)
        assertArrayEquals(doubleArrayOf(0.0, 0.0), chart.gpx[2].distance, 0.0)
        assertArrayEquals(doubleArrayOf(450.0), chart.gpx[3].elevation, 0.0)
        assertArrayEquals(doubleArrayOf(300.0), chart.gpx[4].elevation, 0.0)
        val nativeThirdDistance = ElevationMath.distance(first[1].position, first[2].position) +
            ElevationMath.distance(first[2].position, first[3].position)
        assertEquals(nativeThirdDistance, chart.gpx[3].distance.single(), 1e-9)
        assertEquals(prepared.segments[0].distance.last(), chart.gpx[5].distance.first(), 0.0)
        assertEquals(prepared.length, chart.gpx[5].distance.last(), 1e-9)
        assertArrayEquals(doubleArrayOf(500.0, 600.0), chart.gpx[5].elevation, 0.0)
        assertEquals(-9999.0, chart.minAltitude, 0.0)
        assertEquals(9999.0, chart.maxAltitude, 0.0)
        // Display bounds must not alter the smoothed result or its elevation gain.
        assertEquals(100.0, computed.minAltitude, 1e-9)
        assertEquals(100.0, computed.maxAltitude, 1e-9)
        assertEquals(0.0, computed.gain.up, 1e-9)
    }

    @Test fun missingOrNonFiniteObservationsLeaveTerrainBoundsAvailable() {
        val prepared = ElevationMath.prepare(Track(listOf(listOf(point(5.0, null), point(5.001, Double.NaN)))))
        val computed = ElevationMath.compute(prepared, DoubleArray(prepared.sampleCount) { 100.0 })
        val chart = profileChartData(prepared, computed.profiles)
        assertTrue(chart.gpx.isEmpty())
        assertEquals(computed.minAltitude, chart.minAltitude, 0.0)
        assertEquals(computed.maxAltitude, chart.maxAltitude, 0.0)
    }

    @Test fun zoomKeepsGestureAnchorAndBoundsPanningAndScale() {
        val full = ProfileViewport(0.0, 1000.0, 100.0, 500.0)
        val zoomed = transformProfileViewport(full, full, 2.0, .25, .75)
        assertEquals(125.0, zoomed.minDistance, 0.0)
        assertEquals(625.0, zoomed.maxDistance, 0.0)
        assertEquals(250.0, zoomed.minAltitude, 0.0)
        assertEquals(450.0, zoomed.maxAltitude, 0.0)
        val panned = transformProfileViewport(zoomed, full, 1.0, panX = 10.0, panY = -10.0)
        assertEquals(0.0, panned.minDistance, 0.0)
        assertEquals(100.0, panned.minAltitude, 0.0)
        assertEquals(zoomed.distanceSpan, panned.distanceSpan, 0.0)
        val maximum = transformProfileViewport(zoomed, full, 1000.0)
        assertEquals(5.0, maximum.distanceSpan, 1e-9)
        assertEquals(2.0, maximum.altitudeSpan, 1e-9)
        assertEquals(full, transformProfileViewport(maximum, full, .00001))
    }

    @Test fun zoomRevealsNativeDetailAndRetainsNeighbouringSamples() {
        val profile = Profile(DoubleArray(10001) { it.toDouble() }, DoubleArray(10001) { it.toDouble() })
        val full = ProfileViewport(0.0, 10000.0, 0.0, 10000.0)
        val coarse = visibleProfilePoints(profile, full, buckets = 2)
        assertFalse(coarse.any { it.first == 5005.0 })
        val zoomed = visibleProfilePoints(profile, full.copy(minDistance = 5000.0, maxDistance = 5010.0))
        assertTrue(zoomed.any { it.first == 5005.0 && it.second == 5005.0 })
        assertEquals(4999.0, zoomed.first().first, 0.0)
        assertEquals(5011.0, zoomed.last().first, 0.0)
        assertTrue(visibleProfilePoints(profile, full.copy(minDistance = 20000.0, maxDistance = 21000.0)).isEmpty())
    }
}
