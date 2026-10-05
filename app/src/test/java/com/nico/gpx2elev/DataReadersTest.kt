package com.nico.gpx2elev

import com.nico.gpx2elev.core.GeoPoint
import com.nico.gpx2elev.data.*
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayInputStream
import java.util.concurrent.CancellationException

class DataReadersTest {
    @get:Rule val temporary = TemporaryFolder()
    private fun bytes(name: String) = javaClass.getResourceAsStream("/$name")!!.use { it.readBytes() }
    private fun source(bytes: ByteArray) = object : ByteSource {
        override fun read(offset: Long, length: Int) = bytes.copyOfRange(offset.toInt(), offset.toInt() + length)
    }

    @Test fun decodesRealFloatRastersPredictor2AndPredictor3() {
        for (name in listOf("copernicus", "fabdem")) {
            val raster = TiffRaster(source(bytes("$name.tif")), name, RasterBlocks())
            val lines = String(bytes("${name}_pixels.csv"), Charsets.UTF_8).lines().drop(1).filter { it.isNotBlank() }
            for (line in lines) {
                val values = line.split(',').map { it.toDouble() }
                val p = GeoPoint(values[2], values[3])
                assertEquals(values[4], raster.pixel(values[0].toInt(), values[1].toInt()), 0.0)
                val (x, y) = raster.grid(p)
                assertEquals(values[0], x, 1e-8); assertEquals(values[1], y, 1e-8)
                assertEquals(values[4], raster.bilinearInside(p), 1e-6)
            }
            raster.close()
        }
    }

    @Test fun readsZipAndZip64WithoutExtractingOtherMembers() {
        for (name in listOf("test.zip", "test64.zip")) {
            val archive = bytes(name)
            val reader = source(archive)
            val member = RemoteZip.members(reader, archive.size.toLong()).single()
            assertEquals("nested/N43E005_FABDEM_V1-2.tif", member.name)
            val offset = RemoteZip.dataOffset(reader, member)
            val file = temporary.newFolder().resolve("extracted.tif")
            RemoteZip.extract(ByteArrayInputStream(archive.copyOfRange(offset.toInt(), (offset + member.compressed).toInt())), member, file)
            assertArrayEquals(bytes("fabdem.tif"), file.readBytes())
        }
    }

    @Test fun followsRankingAndUsesOneSourceForWholeTrace() {
        val calls = mutableListOf<ElevationSource>()
        val reader = object : ModelReader {
            override fun read(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit): DoubleArray {
                calls += source
                return when (source) {
                    ElevationSource.IGN -> doubleArrayOf(500.0, Double.NaN)
                    ElevationSource.MAPTERHORN -> doubleArrayOf(Double.NaN, 900.0)
                    ElevationSource.FABDEM -> doubleArrayOf(100.0, 105.0)
                    else -> error("Lower-ranking model should not be needed")
                }
            }
        }
        val repository = ElevationRepository(temporary.newFolder(), reader)
        val points = listOf(GeoPoint(45.0, 5.0), GeoPoint(45.001, 5.0))
        val result = repository.obtain(points, true) {}
        assertEquals(listOf(ElevationSource.IGN, ElevationSource.MAPTERHORN, ElevationSource.FABDEM), calls)
        assertEquals(ElevationSource.FABDEM, result.source)
        assertArrayEquals(doubleArrayOf(100.0, 105.0), result.values, 0.0)
        assertEquals(2, result.fallbacks.size)
        calls.clear()
        val offline = repository.obtain(points, false) {}
        assertTrue(offline.fromCache); assertEquals(ElevationSource.FABDEM, offline.source); assertTrue(calls.isEmpty())
    }

    @Test fun rejectsCorruptedCacheAndNeverTreatsNoDataAsAltitude() {
        val dir = temporary.newFolder()
        var calls = 0
        val reader = object : ModelReader {
            override fun read(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit): DoubleArray {
                calls++
                return if (source == ElevationSource.IGN) doubleArrayOf(-99999.0, 100.0) else doubleArrayOf(100.0, 110.0)
            }
        }
        val repository = ElevationRepository(dir, reader)
        val points = listOf(GeoPoint(45.0, 5.0), GeoPoint(45.001, 5.0))
        assertEquals(ElevationSource.MAPTERHORN, repository.obtain(points, true) {}.source)
        val cache = dir.listFiles()!!.single()
        val content = cache.readBytes(); content[15] = (content[15].toInt() xor 1).toByte(); cache.writeBytes(content)
        calls = 0
        assertEquals(ElevationSource.MAPTERHORN, repository.obtain(points, true) {}.source)
        assertEquals(2, calls)
    }

    @Test fun cancellationStopsFallbackImmediately() {
        var calls = 0
        val repository = ElevationRepository(temporary.newFolder(), object : ModelReader {
            override fun read(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit): DoubleArray {
                calls++; throw CancellationException("Cancelled")
            }
        })
        try { repository.obtain(listOf(GeoPoint(45.0, 5.0)), true) {}; fail() } catch (_: CancellationException) { }
        assertEquals(1, calls)
    }
}
