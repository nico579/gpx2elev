package com.nico.gpx2elev.core

import org.xml.sax.Attributes
import org.xml.sax.InputSource
import org.xml.sax.SAXException
import org.xml.sax.SAXNotRecognizedException
import org.xml.sax.SAXNotSupportedException
import org.xml.sax.ext.DefaultHandler2
import java.io.InputStream
import javax.xml.parsers.SAXParserFactory

object GpxParser {
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
        private val stack = mutableListOf<String>()
        private var segment: MutableList<TrackPoint>? = null
        private var point: GeoPoint? = null
        private var elevation: Double? = null
        private var count = 0
        private var text = StringBuilder()
        private fun supported(uri: String) = uri.isEmpty() || uri == "http://www.topografix.com/GPX/1/1" || uri == "http://www.topografix.com/GPX/1/0"

        override fun startElement(uri: String, localName: String, qName: String, attributes: Attributes) {
            val name = if (localName.isNotEmpty()) localName else qName.substringAfter(':')
            if (stack.isEmpty()) {
                require(name == "gpx" && supported(uri)) { "Ce fichier n'est pas un GPX 1.0 ou 1.1." }
                rootSeen = true
            }
            val parent = stack.lastOrNull()
            if (supported(uri)) {
                if ((name == "trkseg" && parent == "trk") || (name == "rte" && parent == "gpx")) {
                    segment = mutableListOf()
                } else if ((name == "trkpt" && parent == "trkseg") || (name == "rtept" && parent == "rte")) {
                    count++
                    require(count <= Protocol.MAX_POINTS) { "Le GPX dépasse ${Protocol.MAX_POINTS} points." }
                    val lat = attributes.getValue("lat")?.toDoubleOrNull()
                    val lon = attributes.getValue("lon")?.toDoubleOrNull()
                    require(lat != null && lon != null && lat.isFinite() && lon.isFinite() && lat in -90.0..90.0 && lon in -180.0..180.0) {
                        "Coordonnées invalides au point $count."
                    }
                    point = GeoPoint(lat, lon)
                    elevation = null
                }
            }
            stack += name
            if (name == "ele" && (parent == "trkpt" || parent == "rtept") && supported(uri)) text = StringBuilder()
        }

        override fun characters(ch: CharArray, start: Int, length: Int) {
            if (stack.lastOrNull() == "ele" && text.length < 128) text.append(ch, start, minOf(length, 128 - text.length))
        }

        override fun endElement(uri: String, localName: String, qName: String) {
            val name = if (localName.isNotEmpty()) localName else qName.substringAfter(':')
            val parent = stack.getOrNull(stack.size - 2)
            if (supported(uri)) {
                if (name == "ele" && (parent == "trkpt" || parent == "rtept")) {
                    elevation = text.toString().trim().toDoubleOrNull()?.takeIf { it.isFinite() }
                } else if ((name == "trkpt" && parent == "trkseg") || (name == "rtept" && parent == "rte")) {
                    point?.let { segment?.add(TrackPoint(it, elevation)) }
                    point = null
                } else if ((name == "trkseg" && parent == "trk") || (name == "rte" && parent == "gpx")) {
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
