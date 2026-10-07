package com.nico.gpx2elev

import com.nico.gpx2elev.core.GeoPoint
import com.nico.gpx2elev.data.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.math.*

class RepositoryRegressionTest {
    @get:Rule val temporary = TemporaryFolder()
    private val point = GeoPoint(43.639722222222225, 5.336666666666667)
    private fun fixture(name: String) = javaClass.getResourceAsStream("/$name")!!.use { it.readBytes() }

    private class Response(url: URL, private val data: ByteArray, private val ranged: Boolean) : HttpURLConnection(url) {
        private fun interval(): IntRange {
            val range = getRequestProperty("Range")?.removePrefix("bytes=") ?: return data.indices
            return if (range.startsWith('-')) max(0, data.size - range.drop(1).toInt()) until data.size
            else range.substringBefore('-').toInt()..min(data.lastIndex, range.substringAfter('-').toInt())
        }
        override fun connect() { }
        override fun disconnect() { }
        override fun usingProxy() = false
        override fun getResponseCode() = if (ranged) 206 else 200
        override fun getContentLengthLong() = interval().count().toLong()
        override fun getHeaderField(name: String): String? = if (name.equals("Content-Range", true) && ranged) {
            val interval = interval(); "bytes ${interval.first}-${interval.last}/${data.size}"
        } else null
        override fun getInputStream() = ByteArrayInputStream(data.copyOfRange(interval().first, interval().last + 1))
    }

    private fun archive(tiff: ByteArray): ByteArray {
        val output = ByteArrayOutputStream()
        ZipOutputStream(output).use { zip ->
            zip.putNextEntry(ZipEntry("nested/N43E005_FABDEM_V1-2.tif"))
            zip.write(tiff); zip.closeEntry()
        }
        return output.toByteArray()
    }

    @Test fun validProfileSurvivesUnwritableCacheWithoutTryingLowerModels() {
        val blocked = temporary.newFile()
        val calls = mutableListOf<ElevationSource>()
        val repository = ElevationRepository(blocked, object : ModelReader {
            override fun read(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit): DoubleArray {
                calls += source; return DoubleArray(points.size) { 123.0 }
            }
        })
        val result = repository.obtain(listOf(point), true) {}
        assertArrayEquals(doubleArrayOf(123.0), result.values, 0.0)
        assertEquals(listOf(ElevationSource.IGN), calls)
        assertFalse(result.fromCache); assertTrue(result.fallbacks.isEmpty())
        assertNotNull(result.cacheWarning)
    }

    private val mapPoint = GeoPoint(Math.toDegrees(atan(sinh(PI * (1 - 2 * 4200.5 / 8192)))), 4200.5 / 8192 * 360 - 180)
    private fun mapDecode(bytes: ByteArray): RgbTile {
        if (!bytes.contentEquals("valid".toByteArray())) throw IOException("Tuile Mapterhorn illisible.")
        return RgbTile(256, IntArray(256 * 256) { (32768 + 123) shl 8 })
    }

    @Test fun corruptMapterhornCacheIsReplacedAndReusedWithoutAnotherDownload() {
        val directory = temporary.newFolder()
        val path = directory.resolve("mapterhorn_13_4200_4200.webp")
        path.writeText("corrupt")
        var requests = 0
        val reader = PublicModels(directory, HttpTransport { url ->
            requests++; Response(url, "valid".toByteArray(), false)
        }, ::mapDecode)
        repeat(2) { assertArrayEquals(doubleArrayOf(123.0), reader.read(ElevationSource.MAPTERHORN, listOf(mapPoint)) {}, 0.0) }
        assertEquals(1, requests); assertEquals("valid", path.readText())
    }

    @Test fun invalidMapterhornDownloadNeverBecomesPersistentCache() {
        val directory = temporary.newFolder()
        var requests = 0
        val reader = PublicModels(directory, HttpTransport { url ->
            requests++; Response(url, "invalid".toByteArray(), false)
        }, ::mapDecode)
        repeat(2) {
            try { reader.read(ElevationSource.MAPTERHORN, listOf(mapPoint)) {}; fail() } catch (_: IOException) { }
            assertFalse(directory.resolve("mapterhorn_13_4200_4200.webp").exists())
        }
        assertEquals(2, requests)
    }

    @Test fun mapterhornWorksWhenDiskCacheCannotBeWritten() {
        val directory = temporary.newFolder()
        // An existing directory at the temporary file location simulates a disk write failure.
        directory.resolve("mapterhorn_13_4200_4200.webp.part").mkdir()
        val reader = PublicModels(directory, HttpTransport { url -> Response(url, "valid".toByteArray(), false) }, ::mapDecode)
        assertArrayEquals(doubleArrayOf(123.0), reader.read(ElevationSource.MAPTERHORN, listOf(mapPoint)) {}, 0.0)
    }

    @Test fun corruptFabdemMetadataIsRecoveredOnceThenAvailableFromDisk() {
        val directory = temporary.newFolder()
        val path = directory.resolve("N43E005_FABDEM_V1-2.tif")
        path.writeBytes(byteArrayOf())
        val tiff = fixture("fabdem.tif")
        val zip = archive(tiff)
        var requests = 0
        val reader = PublicModels(directory, HttpTransport { url -> requests++; Response(url, zip, true) })
        repeat(2) { assertEquals(302.9200134277344, reader.read(ElevationSource.FABDEM, listOf(point)) {}.single(), 1e-6) }
        assertEquals(2, requests); assertArrayEquals(tiff, path.readBytes())
        assertFalse(directory.listFiles()!!.any { it.name.endsWith(".part") })
    }

    @Test fun corruptFabdemCompressedBlockIsRecoveredInsteadOfPersisting() {
        val directory = temporary.newFolder()
        val path = directory.resolve("N43E005_FABDEM_V1-2.tif")
        val tiff = fixture("fabdem.tif")
        val corrupt = tiff.clone()
        val b = ByteBuffer.wrap(corrupt).order(ByteOrder.LITTLE_ENDIAN)
        val ifd = b.getInt(4)
        val entries = (0 until (b.getShort(ifd).toInt() and 65535)).associate {
            val entry = ifd + 2 + it * 12
            (b.getShort(entry).toInt() and 65535) to entry
        }
        fun integer(tag: Int, index: Int = 0): Int {
            val entry = entries.getValue(tag)
            val type = b.getShort(entry + 2).toInt() and 65535
            val count = b.getInt(entry + 4)
            val unit = if (type == 3) 2 else 4
            val offset = if (count * unit <= 4) entry + 8 else b.getInt(entry + 8)
            return if (type == 3) b.getShort(offset + index * unit).toInt() and 65535 else b.getInt(offset + index * unit)
        }
        // Damage the compressed block containing the actual sampled fixture pixel (12, 97).
        val block = 97 / integer(323) * ((integer(256) + integer(322) - 1) / integer(322)) + 12 / integer(322)
        val offset = integer(324, block)
        corrupt[offset] = 0; corrupt[offset + 1] = 0
        path.writeBytes(corrupt)
        val zip = archive(tiff)
        var requests = 0
        val reader = PublicModels(directory, HttpTransport { url -> requests++; Response(url, zip, true) })
        assertEquals(302.9200134277344, reader.read(ElevationSource.FABDEM, listOf(point)) {}.single(), 1e-6)
        assertEquals(2, requests); assertArrayEquals(tiff, path.readBytes())
    }

    @Test fun invalidFabdemDownloadIsNeverPublishedAsTile() {
        val directory = temporary.newFolder()
        val zip = archive("not a GeoTIFF".toByteArray())
        val reader = PublicModels(directory, HttpTransport { url -> Response(url, zip, true) })
        try { reader.read(ElevationSource.FABDEM, listOf(point)) {}; fail() } catch (_: IllegalStateException) { }
        assertFalse(directory.resolve("N43E005_FABDEM_V1-2.tif").exists())
        assertFalse(directory.listFiles()!!.any { it.name.endsWith(".part") })
    }

    @Test fun unsupportedFabdemEncodingIsPreservedWithoutRepeatedDownloads() {
        val directory = temporary.newFolder()
        val path = directory.resolve("N43E005_FABDEM_V1-2.tif")
        val tiff = fixture("fabdem.tif")
        val bytes = ByteBuffer.wrap(tiff).order(ByteOrder.LITTLE_ENDIAN)
        val ifd = bytes.getInt(4)
        val count = bytes.getShort(ifd).toInt() and 65535
        val compression = (0 until count).map { ifd + 2 + it * 12 }.first { (bytes.getShort(it).toInt() and 65535) == 259 }
        bytes.putShort(compression + 8, 5) // Supported TIFF, unsupported LZW compression.
        path.writeBytes(tiff)
        var requests = 0
        val reader = PublicModels(directory, HttpTransport { requests++; error("Must not download an unsupported format again") })
        repeat(2) {
            try { reader.read(ElevationSource.FABDEM, listOf(point)) {}; fail() } catch (_: UnsupportedRasterFormat) { }
        }
        assertEquals(0, requests); assertArrayEquals(tiff, path.readBytes())
    }
}
