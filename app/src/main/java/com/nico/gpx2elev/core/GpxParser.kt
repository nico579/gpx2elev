package com.nico.gpx2elev.core

import org.xml.sax.Attributes
import org.xml.sax.InputSource
import org.xml.sax.SAXException
import org.xml.sax.SAXNotRecognizedException
import org.xml.sax.SAXNotSupportedException
import org.xml.sax.ext.DefaultHandler2
import java.io.InputStream
import java.time.OffsetDateTime
import java.time.Instant
import java.time.format.DateTimeParseException
import javax.xml.parsers.SAXParserFactory

object GpxParser {
    private val timePattern = Regex("\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}(?:\\.\\d{1,9})?(?:Z|[+-]\\d{2}:\\d{2})")
    fun parse(input: InputStream): Track {
        val handler = Handler()
        val reader = SAXParserFactory.newInstance().apply { isNamespaceAware = true }.newSAXParser().xmlReader
        for (feature in listOf("http://xml.org/sax/features/external-general-entities", "http://xml.org/sax/features/external-parameter-entities")) {
            try { reader.setFeature(feature, false) }
            catch (_: SAXNotRecognizedException) { }
            catch (_: SAXNotSupportedException) { }
        }
        // Reject DTDs at their declaration, before any entity resolution, on Android and the JVM.
        reader.setProperty("http://xml.org/sax/properties/lexical-handler", handler)
        reader.contentHandler = handler
        reader.entityResolver = handler
        reader.errorHandler = handler
        reader.parse(InputSource(input))
        require(handler.rootSeen) { "Ce fichier n'est pas un GPX." }
        require(handler.segments.any { it.size >= 2 }) { "Le GPX ne contient pas de trace ou de route utilisable." }
        return Track(handler.segments)
    }

    private class Handler : DefaultHandler2() {
        val segments = mutableListOf<List<TrackPoint>>()
        var rootSeen = false
        private data class Element(val uri: String, val name: String)
        private val stack = mutableListOf<Element>()
        private var segment: MutableList<TrackPoint>? = null
        private var point: GeoPoint? = null
        private var elevation: Double? = null
        private var time: Instant? = null
        private var count = 0
        private var text = StringBuilder()
        private fun supported(uri: String) = uri.isEmpty() || uri == "http://www.topografix.com/GPX/1/1" || uri == "http://www.topografix.com/GPX/1/0"
        // Names alone are insufficient: extensions may contain foreign or nested GPX homonyms.
        private fun atPath(vararg names: String) = stack.size == names.size && stack.indices.all {
            stack[it].name == names[it] && stack[it].uri == stack.first().uri
        }
        private fun atSegment() = atPath("gpx", "trk", "trkseg") || atPath("gpx", "rte")
        private fun atPoint() = atPath("gpx", "trk", "trkseg", "trkpt") || atPath("gpx", "rte", "rtept")
        private fun atElevation() = atPath("gpx", "trk", "trkseg", "trkpt", "ele") || atPath("gpx", "rte", "rtept", "ele")
        private fun atTime() = atPath("gpx", "trk", "trkseg", "trkpt", "time") || atPath("gpx", "rte", "rtept", "time")

        override fun startElement(uri: String, localName: String, qName: String, attributes: Attributes) {
            val name = if (localName.isNotEmpty()) localName else qName.substringAfter(':')
            if (stack.isEmpty()) {
                require(name == "gpx" && supported(uri)) { "Ce fichier n'est pas un GPX 1.0 ou 1.1." }
                rootSeen = true
            }
            stack += Element(uri, name)
            when {
                atSegment() -> segment = mutableListOf()
                atPoint() -> {
                    count++
                    require(count <= Protocol.MAX_POINTS) { "Le GPX dépasse ${Protocol.MAX_POINTS} points." }
                    val lat = attributes.getValue("lat")?.toDoubleOrNull()
                    val lon = attributes.getValue("lon")?.toDoubleOrNull()
                    require(lat != null && lon != null && lat.isFinite() && lon.isFinite() && lat in -90.0..90.0 && lon in -180.0..180.0) {
                        "Coordonnées invalides au point $count."
                    }
                    point = GeoPoint(lat, lon)
                    elevation = null
                    time = null
                }
                atElevation() || atTime() -> text = StringBuilder()
            }
        }

        override fun characters(ch: CharArray, start: Int, length: Int) {
            if ((atElevation() || atTime()) && text.length < 128) text.append(ch, start, minOf(length, 128 - text.length))
        }

        override fun endElement(uri: String, localName: String, qName: String) {
            when {
                atElevation() -> elevation = text.toString().trim().toDoubleOrNull()?.takeIf { it.isFinite() }
                atTime() -> {
                    val value = text.toString().trim()
                    time = if (timePattern.matches(value)) try { OffsetDateTime.parse(value).toInstant() } catch (_: DateTimeParseException) { null } else null
                }
                atPoint() -> {
                    point?.let { segment?.add(TrackPoint(it, elevation, time)) }
                    point = null
                }
                atSegment() -> {
                    segment?.takeIf { it.isNotEmpty() }?.let { segments += it }
                    segment = null
                }
            }
            if (stack.isNotEmpty()) stack.removeAt(stack.lastIndex)
        }

        override fun startDTD(name: String?, publicId: String?, systemId: String?) { throw SAXException("Les déclarations DTD ne sont pas acceptées dans un GPX.") }
        override fun resolveEntity(publicId: String?, systemId: String?): InputSource { throw SAXException("Référence XML externe refusée.") }
    }
}
