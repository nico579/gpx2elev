package com.nico.gpxdenivele.data

import java.io.*
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.CRC32
import java.util.zip.Inflater
import java.util.zip.InflaterInputStream

data class ZipMember(val name: String, val method: Int, val crc: Long, val compressed: Long, val uncompressed: Long, val offset: Long)

/** ZIP/ZIP64 directory reader: download only the requested FABDEM GeoTIFF member. */
object RemoteZip {
    private fun b(data: ByteArray) = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
    private fun u16(buffer: ByteBuffer, offset: Int) = buffer.getShort(offset).toInt() and 65535
    private fun u32(buffer: ByteBuffer, offset: Int) = buffer.getInt(offset).toLong() and 0xffffffffL

    fun members(source: ByteSource, size: Long): List<ZipMember> {
        require(size >= 22)
        val length = minOf(65557L, size).toInt()
        val start = size - length
        val tail = source.read(start, length)
        val tb = b(tail)
        val end = (length - 22 downTo 0).firstOrNull {
            tb.getInt(it) == 0x06054b50 && it + 22 + u16(tb, it + 20) == length
        } ?: error("Fin d'archive ZIP introuvable.")
        require(u16(tb, end + 4) == 0 && u16(tb, end + 6) == 0) { "Archive ZIP multi-volume non prise en charge." }
        var directorySize = u32(tb, end + 12)
        var directoryOffset = u32(tb, end + 16)
        if (directorySize == 0xffffffffL || directoryOffset == 0xffffffffL || u16(tb, end + 10) == 65535) {
            require(end >= 20 && tb.getInt(end - 20) == 0x07064b50) { "Localisateur ZIP64 absent." }
            val zip64 = b(source.read(tb.getLong(end - 12), 56))
            require(zip64.getInt(0) == 0x06064b50 && zip64.getInt(16) == 0 && zip64.getInt(20) == 0)
            directorySize = zip64.getLong(40); directoryOffset = zip64.getLong(48)
        }
        require(directorySize in 1..4 * 1024 * 1024 && directoryOffset >= 0 && directoryOffset + directorySize <= size)
        val data = source.read(directoryOffset, directorySize.toInt())
        val db = b(data)
        var p = 0
        val result = mutableListOf<ZipMember>()
        while (p < data.size) {
            require(p + 46 <= data.size && db.getInt(p) == 0x02014b50) { "Répertoire ZIP invalide." }
            require(u16(db, p + 8) and 1 == 0) { "Archive ZIP chiffrée." }
            val method = u16(db, p + 10)
            var compressed = u32(db, p + 20)
            var uncompressed = u32(db, p + 24)
            val nameLength = u16(db, p + 28); val extraLength = u16(db, p + 30); val commentLength = u16(db, p + 32)
            var offset = u32(db, p + 42)
            require(p + 46 + nameLength + extraLength + commentLength <= data.size)
            val name = String(data, p + 46, nameLength, Charsets.UTF_8)
            var q = p + 46 + nameLength
            val extraEnd = q + extraLength
            while (q + 4 <= extraEnd) {
                val tag = u16(db, q); val n = u16(db, q + 2)
                require(q + 4 + n <= extraEnd)
                if (tag == 1) {
                    var v = q + 4
                    fun next(): Long { require(v + 8 <= q + 4 + n); return db.getLong(v).also { v += 8 } }
                    if (uncompressed == 0xffffffffL) uncompressed = next()
                    if (compressed == 0xffffffffL) compressed = next()
                    if (offset == 0xffffffffL) offset = next()
                }
                q += 4 + n
            }
            require(compressed >= 0 && uncompressed >= 0 && offset >= 0)
            result += ZipMember(name, method, u32(db, p + 16), compressed, uncompressed, offset)
            p += 46 + nameLength + extraLength + commentLength
        }
        return result
    }

    fun dataOffset(source: ByteSource, member: ZipMember): Long {
        val header = b(source.read(member.offset, 30))
        require(header.getInt(0) == 0x04034b50 && u16(header, 8) == member.method)
        return member.offset + 30 + u16(header, 26) + u16(header, 28)
    }

    fun extract(stream: InputStream, member: ZipMember, destination: File, checkActive: () -> Unit = {}) {
        require(member.method in listOf(0, 8) && member.uncompressed in 1..150_000_000 && member.compressed in 1..150_000_000)
        val inflater = if (member.method == 8) Inflater(true) else null
        val input = if (inflater != null) InflaterInputStream(stream, inflater) else stream
        destination.parentFile?.mkdirs()
        val temporary = File(destination.parentFile, destination.name + ".part")
        try {
            val crc = CRC32()
            var size = 0L
            temporary.outputStream().use { output ->
                val buffer = ByteArray(16384)
                while (true) {
                    checkActive()
                    val n = input.read(buffer)
                    if (n < 0) break
                    size += n
                    require(size <= member.uncompressed) { "Taille ZIP incorrecte." }
                    crc.update(buffer, 0, n); output.write(buffer, 0, n)
                }
                require(size == member.uncompressed && crc.value == member.crc) { "Données ZIP incomplètes ou corrompues." }
                output.fd.sync()
            }
            check(temporary.renameTo(destination)) { "Impossible d'enregistrer la tuile FABDEM." }
        } finally { inflater?.end(); temporary.delete() }
    }
}
