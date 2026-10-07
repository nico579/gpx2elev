package com.nico.gpx2elev

import com.nico.gpx2elev.core.*
import org.junit.Assert.*
import org.junit.Test

class GpxParserRegressionTest {
    private fun parse(xml: String) = xml.byteInputStream().use { GpxParser.parse(it) }
    private val points = "<trkpt lat='45' lon='5'><ele>100</ele></trkpt><trkpt lat='45.001' lon='5'><ele>200</ele></trkpt>"

    @Test fun acceptsTracksRoutesAndSegmentsWithSupportedNamespaces() {
        for (namespace in listOf("", "http://www.topografix.com/GPX/1/0", "http://www.topografix.com/GPX/1/1")) {
            for (prefixed in listOf(false, true)) {
                if (namespace.isEmpty() && prefixed) continue
                val body = "<gpx><trk><trkseg>$points</trkseg><trkseg>$points</trkseg></trk><rte>" +
                    points.replace("trkpt", "rtept") + "</rte></gpx>"
                val xml = if (prefixed) body.replace(Regex("<(\\/?)([a-z]+)"), "<$1g:$2")
                    .replace("<g:gpx>", "<g:gpx xmlns:g='$namespace'>")
                else body.replace("<gpx>", if (namespace.isEmpty()) "<gpx>" else "<gpx xmlns='$namespace'>")
                val track = parse(xml)
                assertEquals(6, track.pointCount)
                assertEquals(3, track.segments.size)
                assertTrue(track.segments.all { it.map(TrackPoint::elevation) == listOf(100.0, 200.0) })
                assertEquals(3, ElevationMath.prepare(track).segments.size)
            }
        }
    }

    @Test fun foreignPointExtensionCannotReplaceTheNativeElevation() {
        val xml = "<gpx xmlns:x='urn:foreign'><trk><trkseg>" +
            "<trkpt lat='45' lon='5'><ele>100</ele><extensions><x:trkpt><ele>999</ele></x:trkpt></extensions></trkpt>" +
            "<trkpt lat='45.001' lon='5'><ele>200</ele></trkpt></trkseg></trk></gpx>"
        val track = parse(xml)
        assertEquals(2, track.pointCount)
        assertEquals(listOf(100.0, 200.0), track.segments.single().map(TrackPoint::elevation))
    }

    @Test fun gpxNamedElementsInsideExtensionsCannotAlterTheCurrentPointOrSegment() {
        val nested = "<extensions><trk><trkseg><trkpt lat='NaN' lon='5'><ele>999</ele></trkpt>" +
            "<trkpt lat='45' lon='5'/></trkseg></trk><rte><rtept lat='NaN' lon='5'/></rte></extensions>"
        val xml = "<gpx><trk><trkseg><trkpt lat='45' lon='5'><ele>100</ele>$nested</trkpt>" +
            "<trkpt lat='45.001' lon='5'><ele>200</ele></trkpt></trkseg></trk></gpx>"
        val track = parse(xml)
        assertEquals(1, track.segments.size)
        assertEquals(2, track.pointCount)
        assertEquals(listOf(100.0, 200.0), track.segments.single().map(TrackPoint::elevation))
    }

    @Test fun foreignParentsCannotSupplyGpxSegmentsOrPoints() {
        for (body in listOf(
            "<x:trk><trkseg>$points</trkseg></x:trk>",
            "<trk><x:trkseg>$points</x:trkseg></trk>",
            "<x:rte>${points.replace("trkpt", "rtept")}</x:rte>",
            "<extensions><trk><trkseg>$points</trkseg></trk></extensions>",
        )) {
            try {
                parse("<gpx xmlns:x='urn:foreign'>$body</gpx>")
                fail("A foreign or nested parent must not create a usable GPX track")
            } catch (_: IllegalArgumentException) { }
        }
    }

    @Test fun ignoresForeignElevationAndKeepsMissingAltitudeSupport() {
        val track = parse("<gpx xmlns:x='urn:foreign'><rte>" +
            "<rtept lat='45' lon='5'><x:ele>999</x:ele></rtept>" +
            "<rtept lat='45.001' lon='5'><ele> 200 </ele><x:ele>999</x:ele></rtept></rte></gpx>")
        assertNull(track.segments.single().first().elevation)
        assertEquals(200.0, track.segments.single().last().elevation!!, 0.0)
        assertNull(ElevationMath.prepare(track).segments.single().gpxElevation)
    }

    @Test fun anotherSupportedNamespaceCannotMasqueradeAsTheDocumentNamespace() {
        for (foreign in listOf("", "http://www.topografix.com/GPX/1/0")) {
            val xml = "<gpx xmlns='http://www.topografix.com/GPX/1/1'><trk><trkseg>" +
                "<trkpt lat='45' lon='5'><ele>100</ele><ele xmlns='$foreign'>999</ele></trkpt>" +
                "<trkpt lat='45.001' lon='5'><ele>200</ele></trkpt></trkseg></trk>" +
                "<trk xmlns='$foreign'><trkseg><trkpt lat='NaN' lon='5'/></trkseg></trk></gpx>"
            val track = parse(xml)
            assertEquals(2, track.pointCount)
            assertEquals(listOf(100.0, 200.0), track.segments.single().map(TrackPoint::elevation))
        }
    }
}
