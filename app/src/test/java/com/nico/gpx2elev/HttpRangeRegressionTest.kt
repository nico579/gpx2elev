package com.nico.gpx2elev

import com.nico.gpx2elev.core.GeoPoint
import com.nico.gpx2elev.data.*
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.EOFException
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.SocketException
import java.net.ProtocolException
import java.net.URL
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** Real HTTP responses replayed locally; production still requires HTTPS. */
class HttpRangeRegressionTest {
    @get:Rule val temporary = TemporaryFolder()
    private lateinit var server: ServerSocket
    private lateinit var serving: Thread
    @Volatile private var data = ByteArray(50_000) { (it % 251).toByte() }
    @Volatile private var overrideHeader: String? = null
    @Volatile private var overrideBody: ByteArray? = null
    @Volatile private var chunked = false
    private val requests = java.util.Collections.synchronizedList(mutableListOf<String>())
    private val url = "https://replay.example/raster"

    @Before fun startServer() {
        server = ServerSocket().apply { bind(InetSocketAddress("127.0.0.1", 0)) }
        serving = Thread {
          while (!server.isClosed) {
            try { server.accept().use { socket ->
            socket.soTimeout = 3000
            val input = socket.getInputStream().bufferedReader(Charsets.US_ASCII)
            input.readLine()
            val headers = mutableMapOf<String, String>()
            while (true) {
                val line = input.readLine() ?: break
                if (line.isEmpty()) break
                headers[line.substringBefore(':').lowercase()] = line.substringAfter(':').trim()
            }
            val requested = headers.getValue("range")
            requests.add(requested)
            val range = requested.removePrefix("bytes=")
            val start = if (range.startsWith('-')) maxOf(0, data.size - range.drop(1).toInt()) else range.substringBefore('-').toInt()
            val end = if (range.startsWith('-')) data.lastIndex else minOf(data.lastIndex, range.substringAfter('-').toInt())
            val body = overrideBody ?: data.copyOfRange(start, end + 1)
            val header = overrideHeader ?: "bytes $start-$end/${data.size}"
            val length = if (chunked) "Transfer-Encoding: chunked" else "Content-Length: ${body.size}"
            val output = socket.getOutputStream().buffered()
            output.write("HTTP/1.1 206 Partial Content\r\nContent-Range: $header\r\n$length\r\nConnection: close\r\n\r\n".toByteArray(Charsets.US_ASCII))
            if (chunked) output.write("${body.size.toString(16)}\r\n".toByteArray(Charsets.US_ASCII))
            output.write(body)
            if (chunked) output.write("\r\n0\r\n\r\n".toByteArray(Charsets.US_ASCII))
            output.flush()
            } } catch (e: SocketException) { if (!server.isClosed) throw e }
          }
        }.apply { isDaemon = true; start() }
        }
    @After fun stopServer() { server.close(); serving.join(3000) }
    private fun transport() = HttpTransport { request ->
        URL("http://127.0.0.1:${server.localPort}${request.path}").openConnection() as HttpURLConnection
    }

    @Test fun wrongPositionOfSameLengthIsRejectedBeforeCaching() {
        val directory = temporary.newFolder()
        overrideHeader = "bytes 0-16383/50000"
        val source = RemoteByteSource(url, transport(), directory)
        try { source.read(16384, 8); fail() } catch (_: ProtocolException) { }
        assertEquals(listOf("bytes=16384-32767"), requests)
        assertTrue(directory.listFiles()!!.isEmpty())
    }

    @Test fun invalidEndTotalAndBodyLengthAreRejected() {
        for (header in listOf("bytes 16384-32766/50000", "bytes 16384-32767/32767",
            "bytes 16384-32767/*", "bytes 16384-32767/9223372036854775808", "invalid")) {
            overrideHeader = header
            val directory = temporary.newFolder()
            try { RemoteByteSource(url, transport(), directory).read(16384, 8); fail(header) } catch (_: ProtocolException) { }
            assertTrue(directory.listFiles()!!.isEmpty())
        }
        overrideHeader = "bytes 16384-32767/50000"
        overrideBody = ByteArray(16383)
        try { RemoteByteSource(url, transport(), temporary.newFolder()).read(16384, 8); fail() } catch (_: ProtocolException) { }
    }

    @Test fun validSuffixResponseCanBeShorterThanRequestedForSmallArchives() {
        val response = transport().bytes(url, "bytes=-65557")
        assertEquals(50_000L, response.totalSize)
        assertArrayEquals(data, response.bytes)
        assertEquals(listOf("bytes=-65557"), requests)
    }

    @Test fun shortFinalPageSupportsValidReadsAndRejectsActualEndOfFile() {
        data = javaClass.getResourceAsStream("/copernicus.tif")!!.use { it.readBytes() }
        val source = RemoteByteSource(url, transport(), temporary.newFolder())
        assertArrayEquals(data.copyOfRange(data.size - 4, data.size), source.read(data.size - 4L, 4))
        assertArrayEquals(data.copyOfRange(data.size - 4, data.size), source.read(data.size - 4L, 4))
        assertEquals(1, requests.size)
        try { source.read(data.size.toLong(), 1); fail() } catch (_: EOFException) { }
        assertEquals(1, requests.size)
    }

    private fun tinyTiff(): ByteArray {
        val bytes = ByteArray(938)
        val b = ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
        b.put('I'.code.toByte()).put('I'.code.toByte()).putShort(42).putInt(8)
        val tags = listOf(
            intArrayOf(256, 4, 1, 1), intArrayOf(257, 4, 1, 1), intArrayOf(258, 3, 1, 32),
            intArrayOf(259, 3, 1, 1), intArrayOf(277, 3, 1, 1), intArrayOf(317, 3, 1, 1),
            intArrayOf(322, 4, 1, 1), intArrayOf(323, 4, 1, 1), intArrayOf(324, 4, 1, 400),
            intArrayOf(325, 4, 1, 4), intArrayOf(339, 3, 1, 3), intArrayOf(33550, 12, 3, 256),
            intArrayOf(33922, 12, 6, 280), intArrayOf(34735, 3, 12, 328),
        )
        b.putShort(tags.size.toShort())
        for (tag in tags) b.putShort(tag[0].toShort()).putShort(tag[1].toShort()).putInt(tag[2]).putInt(tag[3])
        b.putInt(0)
        b.position(256); listOf(.001, .001, 0.0).forEach { b.putDouble(it) }
        b.position(280); listOf(0.0, 0.0, 0.0, 5.0, 45.0, 0.0).forEach { b.putDouble(it) }
        b.position(328); listOf(1, 1, 0, 2, 1025, 0, 1, 2, 2048, 0, 1, 4326).forEach { b.putShort(it.toShort()) }
        b.putFloat(400, 123f)
        return bytes
    }

    @Test fun valid938ByteGeoTiffIsReadableThroughRemotePages() {
        data = tinyTiff()
        TiffRaster(RemoteByteSource(url, transport(), temporary.newFolder()), "tiny", RasterBlocks()).use {
            assertEquals(123.0, it.bilinearInside(GeoPoint(45.0, 5.0)), 0.0)
        }
        assertEquals(listOf("bytes=0-16383"), requests)
    }

    @Test fun verifiedBytesRemainUsableWhenCacheDirectoryIsUnwritable() {
        val source = RemoteByteSource(url, transport(), temporary.newFile())
        assertArrayEquals(data.copyOfRange(100, 2148), source.read(100, 2048))
    }

    @Test fun streamedRangeChecksBothTruncationAndExtraBytesWithoutContentLength() {
        chunked = true
        overrideHeader = "bytes 100-109/50000"
        for (size in listOf(9, 11)) {
            overrideBody = ByteArray(size)
            try { transport().consumeRange(url, 100, 10) { it.readBytes() }; fail("size=$size") }
            catch (_: ProtocolException) { }
        }
        overrideBody = ByteArray(10) { it.toByte() }
        transport().consumeRange(url, 100, 10) { assertArrayEquals(overrideBody, it.readBytes()) }
    }

    @Test fun legacyUnverifiedCacheIsIgnored() {
        val directory = temporary.newFolder()
        directory.resolve("${sha256(url)}_0_16384.bin").writeBytes(ByteArray(16384) { 99 })
        val source = RemoteByteSource(url, transport(), directory)
        assertArrayEquals(data.copyOfRange(10, 18), source.read(10, 8))
        assertEquals(1, requests.size)
    }

    @Test fun changedRemoteSizeCannotMixPagesInTheSameReader() {
        val directory = temporary.newFolder()
        val source = RemoteByteSource(url, transport(), directory)
        source.read(0, 8)
        data = data.copyOf(50_001)
        try { source.read(16384, 8); fail() } catch (_: ProtocolException) { }
        assertEquals(1, directory.listFiles()!!.size)
    }
}
