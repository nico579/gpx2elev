package com.nico.gpx2elev.data

import java.io.*
import java.net.HttpURLConnection
import java.net.ProtocolException
import java.net.URL
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.min

class HttpFailure(val status: Int, message: String) : IOException(message)
data class HttpBytes(val bytes: ByteArray, val totalSize: Long?)

/** Serial requests with bounded responses, cancellation and retry for transient failures. */
class HttpTransport(private val openConnection: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection }) {
    private val cancelled = AtomicBoolean(false)
    @Volatile private var current: HttpURLConnection? = null
    private var lastRequest = 0L

    fun cancel() { cancelled.set(true); current?.disconnect() }
    fun checkActive() { if (cancelled.get()) throw CancellationException("Calcul annulé") }
    fun pause(ms: Long) {
        val end = System.nanoTime() + ms * 1_000_000
        while (System.nanoTime() < end) { checkActive(); Thread.sleep(min(100, maxOf(1, (end - System.nanoTime()) / 1_000_000))) }
    }

    private fun <T> request(url: String, range: String?, body: ByteArray?, block: (HttpURLConnection) -> T): T {
        require(url.startsWith("https://"))
        var last: IOException? = null
        for (attempt in 0..2) {
            checkActive()
            // At most 3 requests/s, including retries, below the IGN 5 requests/s limit.
            val elapsed = (System.nanoTime() - lastRequest) / 1_000_000
            if (elapsed < 350) pause(350 - elapsed)
            val connection = openConnection(URL(url))
            current = connection
            try {
                checkActive()
                connection.connectTimeout = 12_000
                connection.readTimeout = 60_000
                connection.setRequestProperty("User-Agent", "gpx2elev/0.1 (personal elevation calculator)")
                connection.setRequestProperty("Accept-Encoding", "identity")
                range?.let { connection.setRequestProperty("Range", it) }
                if (body != null) {
                    connection.requestMethod = "POST"
                    connection.doOutput = true
                    connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                    connection.setFixedLengthStreamingMode(body.size)
                    connection.outputStream.use { it.write(body) }
                }
                lastRequest = System.nanoTime()
                val status = connection.responseCode
                if (status !in 200..299) throw HttpFailure(status, "Service indisponible (HTTP $status).")
                if (range != null && status != 206) throw IOException("Le serveur ne permet pas la lecture partielle des données.")
                return block(connection)
            } catch (exception: IOException) {
                checkActive()
                last = exception
                if (exception is ProtocolException) throw exception
                if (exception is HttpFailure && exception.status != 429 && exception.status < 500) throw exception
                if (attempt == 2) throw exception
                pause(1000L shl attempt)
            } finally {
                connection.disconnect()
                if (current === connection) current = null
            }
        }
        throw last ?: IOException("Échec réseau.")
    }

    private data class PartialResponse(val start: Long, val end: Long, val total: Long) {
        val length get() = end - start + 1
    }

    private fun verify(condition: Boolean, message: String) {
        if (!condition) throw ProtocolException(message)
    }

    private fun partialResponse(connection: HttpURLConnection, requested: String): PartialResponse {
        val header = connection.getHeaderField("Content-Range") ?: throw ProtocolException("Réponse partielle sans position.")
        val match = Regex("bytes (\\d+)-(\\d+)/(\\d+)", RegexOption.IGNORE_CASE).matchEntire(header.trim())
            ?: throw ProtocolException("Position de réponse incorrecte.")
        fun number(text: String) = text.toLongOrNull() ?: throw ProtocolException("Position de réponse incorrecte.")
        val response = PartialResponse(number(match.groupValues[1]), number(match.groupValues[2]), number(match.groupValues[3]))
        verify(response.start <= response.end && response.end < response.total, "Position de réponse incorrecte.")
        val explicit = Regex("bytes=(\\d+)-(\\d+)").matchEntire(requested)
        val suffix = Regex("bytes=-(\\d+)").matchEntire(requested)
        val expected = if (explicit != null) {
            val start = number(explicit.groupValues[1]); val end = number(explicit.groupValues[2])
            verify(start <= end && start < response.total, "Position de réponse incorrecte.")
            start to minOf(end, response.total - 1)
        } else if (suffix != null) {
            val length = number(suffix.groupValues[1])
            verify(length > 0, "Position de réponse incorrecte.")
            maxOf(0L, response.total - length) to (response.total - 1)
        } else throw ProtocolException("Plage HTTP non prise en charge.")
        verify(response.start == expected.first && response.end == expected.second, "Position de réponse incorrecte.")
        val declared = connection.contentLengthLong
        verify(declared < 0 || declared == response.length, "Lecture partielle incomplète.")
        return response
    }

    fun bytes(url: String, range: String? = null, body: ByteArray? = null, maximum: Int = 8 * 1024 * 1024): HttpBytes =
        request(url, range, body) { connection ->
            val declared = connection.contentLengthLong
            val partial = range?.let { partialResponse(connection, it) }
            require(partial == null || partial.length <= maximum) { "Réponse du serveur trop volumineuse." }
            require(declared < 0 || declared <= maximum) { "Réponse du serveur trop volumineuse." }
            val result = ByteArrayOutputStream()
            connection.inputStream.use { input ->
                val buffer = ByteArray(16 * 1024)
                while (true) {
                    checkActive()
                    val n = input.read(buffer)
                    if (n < 0) break
                    require(result.size() + n <= maximum) { "Réponse du serveur trop volumineuse." }
                    result.write(buffer, 0, n)
                }
            }
            verify(partial == null || result.size().toLong() == partial.length, "Lecture partielle incomplète.")
            HttpBytes(result.toByteArray(), partial?.total ?: declared.takeIf { it >= 0 })
        }

    fun consumeRange(url: String, offset: Long, length: Long, consume: (InputStream) -> Unit) {
        require(offset >= 0 && length in 1..150_000_000 && offset <= Long.MAX_VALUE - length)
        request(url, "bytes=$offset-${offset + length - 1}", null) { connection ->
            val partial = partialResponse(connection, "bytes=$offset-${offset + length - 1}")
            verify(partial.length == length, "Lecture partielle incomplète.")
            connection.inputStream.use { input ->
                var consumed = 0L
                val counted = object : FilterInputStream(input) {
                    private fun count(n: Int): Int {
                        if (n > 0) consumed += n
                        verify(consumed <= length, "Réponse partielle trop longue.")
                        return n
                    }
                    override fun read(): Int { checkActive(); return super.read().also { if (it >= 0) count(1) } }
                    override fun read(buffer: ByteArray, offset: Int, size: Int): Int {
                        checkActive(); return count(input.read(buffer, offset, size))
                    }
                    override fun skip(n: Long): Long {
                        val buffer = ByteArray(16 * 1024)
                        var skipped = 0L
                        while (skipped < n) {
                            val read = read(buffer, 0, minOf(buffer.size.toLong(), n - skipped).toInt())
                            if (read < 0) break
                            skipped += read
                        }
                        return skipped
                    }
                    // The transport owns the underlying stream, including validation after the callback.
                    override fun close() { }
                }
                consume(counted)
                val buffer = ByteArray(16 * 1024)
                while (counted.read(buffer) >= 0) { }
                verify(consumed == length, "Lecture partielle incomplète.")
            }
        }
    }
}

interface ByteSource : Closeable {
    fun read(offset: Long, length: Int): ByteArray
    override fun close() { }
}

class FileByteSource(file: File) : ByteSource {
    private val data = RandomAccessFile(file, "r")
    override fun read(offset: Long, length: Int): ByteArray {
        require(offset >= 0 && length >= 0 && offset + length <= data.length()) { "Fichier raster tronqué." }
        return ByteArray(length).also { data.seek(offset); data.readFully(it) }
    }
    override fun close() = data.close()
}

fun sha256(text: String): String = java.security.MessageDigest.getInstance("SHA-256")
    .digest(text.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it.toInt() and 255) }

fun atomicBytes(file: File, bytes: ByteArray) {
    file.parentFile?.mkdirs()
    val temporary = File(file.parentFile, file.name + ".part")
    try {
        temporary.outputStream().use { it.write(bytes); it.fd.sync() }
        if (!temporary.renameTo(file)) {
            if (file.exists()) file.delete()
            check(temporary.renameTo(file)) { "Impossible d'enregistrer le cache." }
        }
    } finally { temporary.delete() }
}

class RemoteByteSource(private val url: String, private val http: HttpTransport, private val directory: File) : ByteSource {
    // Ignore entries written before Content-Range validation was introduced.
    private val prefix = sha256("verified-range-v2:$url")
    private var totalSize: Long? = null
    private val pages = object : LinkedHashMap<Long, ByteArray>(8, .75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<Long, ByteArray>?) = size > 8
    }
    private fun exact(offset: Long, length: Int, page: Boolean = false): ByteArray {
        http.checkActive()
        val available = totalSize?.let { it - offset }
        if (available != null && (available <= 0 || (!page && length > available))) throw EOFException("Lecture au-delà de la fin du fichier.")
        val requested = if (page && available != null) minOf(length.toLong(), available).toInt() else length
        val file = File(directory, "${prefix}_${offset}_$requested.bin")
        if (file.exists() && file.length() == requested.toLong()) {
            file.setLastModified(System.currentTimeMillis())
            return file.readBytes()
        }
        val response = http.bytes(url, "bytes=$offset-${offset + requested - 1}", maximum = requested)
        val size = response.totalSize ?: throw ProtocolException("Taille du fichier inconnue.")
        if (totalSize != null && totalSize != size) throw ProtocolException("La taille du fichier distant a changé.")
        totalSize = size
        val data = response.bytes
        if (!page && data.size != requested) throw EOFException("Lecture au-delà de la fin du fichier.")
        try {
            atomicBytes(File(directory, "${prefix}_${offset}_${data.size}.bin"), data)
        } catch (_: IOException) {
            // A verified range remains usable when the disk cache is unavailable.
        } catch (_: IllegalStateException) {
            // atomicBytes reports a failed final rename with check().
        }
        return data
    }
    override fun read(offset: Long, length: Int): ByteArray {
        require(offset >= 0 && length in 0..8 * 1024 * 1024 && offset <= Long.MAX_VALUE - length)
        if (length == 0) return byteArrayOf()
        val page = offset / 16384 * 16384
        return if (length <= 1024 && offset + length <= page + 16384) {
            val bytes = pages.getOrPut(page) { exact(page, 16384, page = true) }
            val start = (offset - page).toInt()
            if (start + length > bytes.size) throw EOFException("Lecture au-delà de la fin du fichier.")
            bytes.copyOfRange(start, start + length)
        } else exact(offset, length)
    }
}
