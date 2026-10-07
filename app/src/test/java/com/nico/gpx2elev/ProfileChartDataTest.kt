package com.nico.gpx2elev

import com.nico.gpx2elev.core.*
import com.nico.gpx2elev.ui.profileChartData
import com.nico.gpx2elev.ui.ProfileViewport
import com.nico.gpx2elev.ui.transformProfileViewport
import com.nico.gpx2elev.ui.visibleProfilePoints
import org.junit.Assert.*
import org.junit.Test

class ProfileChartDataTest {
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
