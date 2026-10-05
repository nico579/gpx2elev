package com.nico.gpx2elev

import com.nico.gpx2elev.core.*
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import java.io.ByteArrayInputStream
import kotlin.math.abs

class ElevationMathTest {
    private fun parse(xml: String) = GpxParser.parse(ByteArrayInputStream(xml.toByteArray(Charsets.UTF_8)))

    @Test fun matchesAuditedPythonOnOctober4Trace() {
        assumeTrue("Banc d'essai personnel local", javaClass.getResource("/reference.gpx") != null && javaClass.getResource("/reference.csv") != null)
        val track = javaClass.getResourceAsStream("/reference.gpx")!!.use { GpxParser.parse(it) }
        assertEquals(1500, track.pointCount)
        val prepared = ElevationMath.prepare(track)
        val rows = javaClass.getResourceAsStream("/reference.csv")!!.bufferedReader().use { it.readLines() }.drop(1)
            .map { row -> row.split(',').map { it.toDouble() } }
        assertEquals(4467, prepared.sampleCount)
        assertEquals(22325.61987711584, prepared.length, 1e-6)
        val segment = prepared.segments.single()
        for (i in rows.indices) {
            assertEquals(rows[i][0], segment.distance[i], 1e-6)
            assertEquals(rows[i][1], segment.points[i].lat, 1e-10)
            assertEquals(rows[i][2], segment.points[i].lon, 1e-10)
        }
        val z = rows.map { it[3] }.toDoubleArray()
        val smooth = ElevationMath.gaussian(segment.distance, z)
        for (i in rows.indices) assertEquals("Gaussian point $i", rows[i][4], smooth[i], 1e-7)
        val result = ElevationMath.compute(prepared, z)
        assertEquals(735.1285660253573, result.gain.up, 1e-6)
        assertEquals(735.1495651743335, result.gain.down, 1e-6)
        assertEquals(3380.71, result.gpxRaw!!.up, 1e-7)
        assertEquals(3380.89, result.gpxRaw!!.down, 1e-7)
        assertEquals(1165.4629988478032, result.gpxFiltered!!.up, 1e-5)
        assertEquals(1165.6437051934863, result.gpxFiltered!!.down, 1e-5)
    }

    @Test fun preservesLinearRampAndOffGridEndForShortAndLongSegments() {
        for (x in listOf(doubleArrayOf(0.0, 1.2), doubleArrayOf(0.0, 5.0, 7.3), DoubleArray(202) { if (it == 201) 1002.7 else it * 5.0 })) {
            val z = x.map { 100.0 + .3 * it }.toDoubleArray()
            val smooth = ElevationMath.gaussian(x, z)
            for (i in x.indices) assertEquals(z[i], smooth[i], 1e-9)
        }
    }

    @Test fun hysteresisKeepsSuccessiveSubThresholdRises() {
        val z = DoubleArray(101) { 500 + .2 * it }
        val gain = ElevationMath.totals(ElevationMath.anchors(z).map { z[it] }.toDoubleArray())
        assertEquals(20.0, gain.up, 1e-10); assertEquals(0.0, gain.down, 0.0)
    }

    @Test fun hysteresisConfirmsReversalsAndRetainsFinalRemainder() {
        val z = doubleArrayOf(100.0, 101.0, 100.5, 104.0, 103.0, 102.0, 99.0, 101.0, 100.0)
        val anchors = ElevationMath.anchors(z)
        assertArrayEquals(intArrayOf(0, 3, 6, 7, 8), anchors)
        val gain = ElevationMath.totals(anchors.map { z[it] }.toDoubleArray())
        assertEquals(6.0, gain.up, 0.0); assertEquals(6.0, gain.down, 0.0)
    }

    @Test fun disjointSegmentsNeverCreateArtificialClimb() {
        val track = parse("<gpx><trk><trkseg><trkpt lat='45' lon='5'/><trkpt lat='45' lon='5.001'/></trkseg><trkseg><trkpt lat='45' lon='6'/><trkpt lat='45' lon='6.001'/></trkseg></trk></gpx>")
        val prepared = ElevationMath.prepare(track)
        val first = prepared.segments.first().points.size
        val z = DoubleArray(prepared.sampleCount) { if (it < first) 100.0 else 1100.0 }
        val result = ElevationMath.compute(prepared, z)
        assertEquals(0.0, result.gain.up, 1e-9); assertEquals(0.0, result.gain.down, 1e-9)
        assertEquals(2, result.profiles.size)
    }

    @Test fun stopsKeepLastAltitudeForResamplingButAllValuesForRawSum() {
        val track = parse("<gpx><rte><rtept lat='45' lon='5'><ele>1</ele></rtept><rtept lat='45' lon='5'><ele>3</ele></rtept><rtept lat='45' lon='5.001'><ele>8</ele></rtept></rte></gpx>")
        val prepared = ElevationMath.prepare(track)
        assertEquals(3.0, prepared.segments.single().gpxElevation!!.first(), 0.0)
        val result = ElevationMath.compute(prepared, DoubleArray(prepared.sampleCount) { 100.0 })
        assertEquals(7.0, result.gpxRaw!!.up, 0.0)
        assertEquals(5.0, result.gpxFiltered!!.up, 1e-8)
    }

    @Test fun crossesDateLineAlongShortArc() {
        val prepared = ElevationMath.prepare(parse("<gpx><rte><rtept lat='0' lon='179.999'/><rtept lat='0' lon='-179.999'/></rte></gpx>"))
        assertTrue(prepared.length in 220.0..225.0)
        assertTrue(prepared.points.all { abs(it.lon) > 179.99 })
    }

    @Test fun acceptsNamespaceAndMissingElevations() {
        val track = parse("<g:gpx xmlns:g='http://www.topografix.com/GPX/1/1'><g:trk><g:trkseg><g:trkpt lat='45' lon='5'/><g:trkpt lat='45' lon='5.001'><g:ele>abc</g:ele></g:trkpt></g:trkseg></g:trk></g:gpx>")
        val prepared = ElevationMath.prepare(track)
        val result = ElevationMath.compute(prepared, DoubleArray(prepared.sampleCount) { 100.0 })
        assertNull(result.gpxRaw); assertNull(result.gpxFiltered)
    }

    @Test fun rejectsInvalidCoordinatesAndDtd() {
        for (xml in listOf("<gpx><rte><rtept lat='NaN' lon='5'/><rtept lat='45' lon='5.1'/></rte></gpx>",
            "<gpx><rte><rtept lat='91' lon='5'/><rtept lat='45' lon='5.1'/></rte></gpx>",
            "<!DOCTYPE gpx [<!ENTITY leak SYSTEM 'file:///invalid'>]><gpx>&leak;</gpx>", "<html/>")) {
            try { parse(xml); fail("Should reject invalid GPX") } catch (_: Exception) { }
        }
    }
}
