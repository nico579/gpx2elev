package com.nico.gpx2elev.data

import java.io.*
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.math.min

class HttpFailure(val status: Int, message: String) : IOException(message)
data class HttpBytes(val bytes: ByteArray, val totalSize: Long?)

/** Serial requests with bounded responses, cancellation and retry for transient failures. */
class HttpTransport {
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
            val connection = URL(url).openConnection() as HttpURLConnection
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

    fun bytes(url: String, range: String? = null, body: ByteArray? = null, maximum: Int = 8 * 1024 * 1024): HttpBytes =
        request(url, range, body) { connection ->
            val declared = connection.contentLengthLong
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
            val total = connection.getHeaderField("Content-Range")?.substringAfterLast('/')?.toLongOrNull()
            HttpBytes(result.toByteArray(), total ?: declared.takeIf { range == null && it >= 0 })
        }

    fun consumeRange(url: String, offset: Long, length: Long, consume: (InputStream) -> Unit) {
        require(offset >= 0 && length in 1..150_000_000)
        request(url, "bytes=$offset-${offset + length - 1}", null) { connection ->
            val header = connection.getHeaderField("Content-Range") ?: throw IOException("Réponse partielle sans position.")
            require(header.startsWith("bytes $offset-")) { "Position de réponse incorrecte." }
            connection.inputStream.use { consume(it) }
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
    private val prefix = sha256(url)
    private val pages = object : LinkedHashMap<Long, ByteArray>(8, .75f, true) {
        override fun removeEldestEntry(eldest: MutableMap.MutableEntry<Long, ByteArray>?) = size > 8
    }
    private fun exact(offset: Long, length: Int): ByteArray {
        http.checkActive()
        val file = File(directory, "${prefix}_${offset}_$length.bin")
        if (file.exists() && file.length() == length.toLong()) {
            file.setLastModified(System.currentTimeMillis())
            return file.readBytes()
        }
        val data = http.bytes(url, "bytes=$offset-${offset + length - 1}").bytes
        require(data.size == length) { "Lecture partielle incomplète." }
        atomicBytes(file, data)
        return data
    }
    override fun read(offset: Long, length: Int): ByteArray {
        require(offset >= 0 && length in 0..8 * 1024 * 1024)
        if (length == 0) return byteArrayOf()
        val page = offset / 16384 * 16384
        return if (length <= 1024 && offset + length <= page + 16384) {
            val bytes = pages.getOrPut(page) { exact(page, 16384) }
            bytes.copyOfRange((offset - page).toInt(), (offset - page).toInt() + length)
        } else exact(offset, length)
    }
}
