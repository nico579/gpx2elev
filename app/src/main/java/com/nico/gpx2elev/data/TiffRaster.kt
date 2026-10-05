package com.nico.gpx2elev.data

import com.nico.gpx2elev.core.GeoPoint
import java.io.ByteArrayInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.InflaterInputStream
import kotlin.math.*

/** Shared decoded-block LRU: no complete 3600×3600 raster is kept in RAM. */
class RasterBlocks(private val maximumBytes: Int = 16 * 1024 * 1024) {
    private val items = LinkedHashMap<String, FloatArray>(16, .75f, true)
    private var bytes = 0
    fun obtain(key: String, load: () -> FloatArray): FloatArray {
        items[key]?.let { return it }
        val data = load()
        while (items.isNotEmpty() && bytes + data.size * 4 > maximumBytes) {
            val first = items.entries.iterator()
            bytes -= first.next().value.size * 4; first.remove()
        }
        items[key] = data; bytes += data.size * 4
        return data
    }
}

/** The float32, tiled, Deflate GeoTIFF encoding of FABDEM 1.2 and Copernicus GLO-30. */
class TiffRaster(private val source: ByteSource, private val key: String, private val blocks: RasterBlocks) : AutoCloseable {
    private data class Tag(val type: Int, val count: Int, val inline: ByteArray, val offset: Long)
    private val order: ByteOrder
    private val tags = mutableMapOf<Int, Tag>()
    val width: Int
    val height: Int
    private val tileWidth: Int
    private val tileHeight: Int
    private val predictor: Int
    private val compression: Int
    private val offsets: LongArray
    private val lengths: LongArray
    private val scaleX: Double
    private val scaleY: Double
    private val tieX: Double
    private val tieY: Double
    private val tieLon: Double
    private val tieLat: Double
    private val pixelOffset: Double
    private val noData: Double?

    init {
        val header = source.read(0, 8)
        order = when (String(header.copyOfRange(0, 2), Charsets.US_ASCII)) {
            "II" -> ByteOrder.LITTLE_ENDIAN
            "MM" -> ByteOrder.BIG_ENDIAN
            else -> error("En-tête GeoTIFF invalide.")
        }
        val hb = buffer(header)
        require((hb.getShort(2).toInt() and 65535) == 42) { "Format GeoTIFF non pris en charge." }
        val offset = hb.getInt(4).toLong() and 0xffffffffL
        val count = buffer(source.read(offset, 2)).short.toInt() and 65535
        require(count in 1..512)
        val entries = source.read(offset + 2, count * 12)
        val b = buffer(entries)
        for (i in 0 until count) {
            val p = i * 12
            val id = b.getShort(p).toInt() and 65535
            val type = b.getShort(p + 2).toInt() and 65535
            val n = b.getInt(p + 4)
            require(n in 0..1_000_000)
            tags[id] = Tag(type, n, entries.copyOfRange(p + 8, p + 12), b.getInt(p + 8).toLong() and 0xffffffffL)
        }
        width = ints(256).first().toInt(); height = ints(257).first().toInt()
        require(width in 1..10000 && height in 1..10000)
        require(ints(258).contentEquals(longArrayOf(32)) && ints(339).contentEquals(longArrayOf(3))) { "Raster attendu en float32." }
        require((tags[277]?.let { ints(277).first() } ?: 1L) == 1L) { "Raster attendu à une bande." }
        require((tags[274]?.let { ints(274).first() } ?: 1L) == 1L) { "Orientation raster inattendue." }
        tileWidth = ints(322).first().toInt(); tileHeight = ints(323).first().toInt()
        require(tileWidth in 1..2048 && tileHeight in 1..2048)
        predictor = tags[317]?.let { ints(317).first().toInt() } ?: 1
        compression = ints(259).first().toInt()
        require(predictor in 1..3 && compression in listOf(1, 8, 32946)) { "Compression raster inattendue." }
        offsets = ints(324); lengths = ints(325)
        val tileCount = ((width + tileWidth - 1) / tileWidth) * ((height + tileHeight - 1) / tileHeight)
        require(offsets.size == tileCount && lengths.size == tileCount)
        val scale = doubles(33550); val tie = doubles(33922)
        require(scale.size >= 2 && tie.size >= 6 && scale[0] > 0 && scale[1] > 0)
        scaleX = scale[0]; scaleY = scale[1]
        tieX = tie[0]; tieY = tie[1]; tieLon = tie[3]; tieLat = tie[4]
        val geo = ints(34735)
        require(geo.size >= 4 && geo.size == 4 + geo[3].toInt() * 4)
        fun geoValue(id: Long): Long? = (4 until geo.size step 4).firstOrNull { geo[it] == id && geo[it + 1] == 0L }?.let { geo[it + 3] }
        require(geoValue(2048) == 4326L) { "Projection raster différente de WGS84." }
        pixelOffset = if (geoValue(1025) == 2L) 0.0 else .5
        noData = tags[42113]?.let { String(bytes(42113), Charsets.US_ASCII).trimEnd('\u0000').toDoubleOrNull() }
    }

    private fun buffer(bytes: ByteArray) = ByteBuffer.wrap(bytes).order(order)
    private fun bytes(id: Int): ByteArray {
        val tag = tags[id] ?: error("GeoTIFF sans balise $id.")
        val unit = when (tag.type) { 1, 2, 6, 7 -> 1; 3, 8 -> 2; 4, 9, 11 -> 4; 5, 10, 12 -> 8; else -> error("Type TIFF inconnu.") }
        val length = Math.multiplyExact(tag.count, unit)
        require(length <= 8 * 1024 * 1024)
        return if (length <= 4) tag.inline.copyOf(length) else source.read(tag.offset, length)
    }
    private fun ints(id: Int): LongArray {
        val tag = tags[id] ?: error("GeoTIFF sans balise $id.")
        val b = buffer(bytes(id))
        return LongArray(tag.count) { when (tag.type) {
            3 -> b.short.toLong() and 65535L
            4 -> b.int.toLong() and 0xffffffffL
            else -> error("Balise TIFF non entière.")
        } }
    }
    private fun doubles(id: Int): DoubleArray {
        require(tags[id]?.type == 12)
        val b = buffer(bytes(id))
        return DoubleArray(tags[id]!!.count) { b.double }
    }

    fun grid(point: GeoPoint): Pair<Double, Double> =
        (tieX + (point.lon - tieLon) / scaleX - pixelOffset) to (tieY + (tieLat - point.lat) / scaleY - pixelOffset)
    fun position(col: Int, row: Int) = GeoPoint(tieLat - (row + pixelOffset - tieY) * scaleY, tieLon + (col + pixelOffset - tieX) * scaleX)

    fun pixel(col: Int, row: Int): Double {
        require(col in 0 until width && row in 0 until height)
        val block = row / tileHeight * ((width + tileWidth - 1) / tileWidth) + col / tileWidth
        val values = blocks.obtain("$key/$block") { decode(block) }
        val value = values[(row % tileHeight) * tileWidth + col % tileWidth].toDouble()
        return if (!value.isFinite() || (noData != null && value == noData)) Double.NaN else value
    }

    private fun decode(block: Int): FloatArray {
        val expected = tileWidth * tileHeight * 4
        require(lengths[block] in 1..8 * 1024 * 1024)
        val encoded = source.read(offsets[block], lengths[block].toInt())
        val raw = if (compression == 1) encoded else {
            InflaterInputStream(ByteArrayInputStream(encoded)).use { input ->
                val result = ByteArray(expected)
                var n = 0
                while (n < expected) {
                    val read = input.read(result, n, expected - n)
                    require(read > 0) { "Bloc raster tronqué." }; n += read
                }
                require(input.read() == -1) { "Bloc raster trop long." }
                result
            }
        }
        require(raw.size == expected)
        val values = FloatArray(tileWidth * tileHeight)
        if (predictor == 3) {
            // TIFF floating-point predictor: byte accumulation followed by MSB-first plane unshuffle.
            for (row in 0 until tileHeight) {
                val start = row * tileWidth * 4
                for (i in 1 until tileWidth * 4) raw[start + i] = ((raw[start + i].toInt() and 255) + (raw[start + i - 1].toInt() and 255)).toByte()
                for (col in 0 until tileWidth) {
                    var bits = 0
                    for (plane in 0..3) bits = (bits shl 8) or (raw[start + plane * tileWidth + col].toInt() and 255)
                    values[row * tileWidth + col] = Float.fromBits(bits)
                }
            }
        } else {
            val b = buffer(raw)
            for (row in 0 until tileHeight) {
                var previous = 0
                for (col in 0 until tileWidth) {
                    val bits = b.int + if (predictor == 2 && col > 0) previous else 0
                    values[row * tileWidth + col] = Float.fromBits(bits); previous = bits
                }
            }
        }
        return values
    }

    fun bilinearInside(point: GeoPoint): Double {
        val (cx, cy) = grid(point)
        if (cx < -1e-7 || cy < -1e-7 || cx > width - 1 + 1e-7 || cy > height - 1 + 1e-7) return Double.NaN
        val x = cx.coerceIn(0.0, width - 1.0); val y = cy.coerceIn(0.0, height - 1.0)
        val x0 = floor(x).toInt(); val y0 = floor(y).toInt()
        val dx = x - x0; val dy = y - y0
        var result = 0.0
        for ((col, row, weight) in corners(x0, y0, dx, dy)) {
            if (weight > 1e-12) result += weight * pixel(min(col, width - 1), min(row, height - 1))
        }
        return result
    }
    override fun close() = source.close()
}

data class Corner(val col: Int, val row: Int, val weight: Double)
fun corners(x: Int, y: Int, dx: Double, dy: Double) = listOf(
    Corner(x, y, (1 - dx) * (1 - dy)), Corner(x + 1, y, dx * (1 - dy)),
    Corner(x, y + 1, (1 - dx) * dy), Corner(x + 1, y + 1, dx * dy)
)
