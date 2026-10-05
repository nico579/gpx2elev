package com.nico.gpxdenivele.data

import android.graphics.BitmapFactory
import com.nico.gpxdenivele.core.GeoPoint
import org.json.JSONObject
import java.io.*
import java.nio.ByteBuffer
import java.util.Locale
import java.util.concurrent.CancellationException
import java.util.zip.ZipInputStream
import kotlin.math.*

enum class ElevationSource(val label: String, val configuration: String) {
    IGN("IGN LiDAR HD", "ign_lidar_hd_mnt_mono_wld-7dec-v1"),
    MAPTERHORN("Mapterhorn", "terrarium-z13-parent-bilinear-v1"),
    FABDEM("FABDEM 1.2", "FABDEM_V1-2-bilinear-seamless-v1"),
    COPERNICUS("Copernicus GLO-30", "GLO30-2021-bilinear-seamless-v1"),
    SRTM("SRTM90", "SRTM3-v2.1-bilinear-v1");
}
data class SourceFailure(val source: ElevationSource, val reason: String)
data class ElevationSeries(val source: ElevationSource, val values: DoubleArray, val fromCache: Boolean, val fallbacks: List<SourceFailure>)
class MissingCoverage(message: String) : IOException(message)
data class Progress(val message: String, val completed: Int, val total: Int)

interface ModelReader {
    fun read(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit): DoubleArray
}

/** Select one complete source for the entire GPX, in the measured metropolitan ranking. */
class ElevationRepository(private val profiles: File, private val reader: ModelReader) {
    companion object { val RANKING = ElevationSource.entries.toList() }

    private fun file(source: ElevationSource, points: List<GeoPoint>): File {
        val digest = java.security.MessageDigest.getInstance("SHA-256")
        digest.update(source.configuration.toByteArray(Charsets.UTF_8))
        val bytes = ByteBuffer.allocate(16)
        for (p in points) {
            bytes.clear(); bytes.putDouble(p.lat); bytes.putDouble(p.lon); digest.update(bytes.array())
        }
        val key = digest.digest().joinToString("") { "%02x".format(it.toInt() and 255) }
        return File(profiles, "${source.name}_$key.profile")
    }

    private fun cached(file: File, expected: Int): DoubleArray? {
        if (!file.exists() || file.length() != 8L + expected * 8L + 32) return null
        return try {
            val bytes = file.readBytes()
            val content = bytes.copyOfRange(0, bytes.size - 32)
            val checksum = java.security.MessageDigest.getInstance("SHA-256").digest(content)
            if (!checksum.contentEquals(bytes.copyOfRange(bytes.size - 32, bytes.size))) return null
            DataInputStream(ByteArrayInputStream(content)).use { input ->
                if (input.readInt() != 0x47505831 || input.readInt() != expected) return null
                val result = DoubleArray(expected) { input.readDouble() }
                if (!result.all { it.isFinite() && it in -1000.0..9000.0 }) return null
                file.setLastModified(System.currentTimeMillis())
                result
            }
        } catch (_: IOException) { null }
    }

    private fun save(file: File, values: DoubleArray) {
        val data = ByteArrayOutputStream()
        DataOutputStream(data).use { output ->
            output.writeInt(0x47505831); output.writeInt(values.size)
            values.forEach { output.writeDouble(it) }
        }
        val bytes = data.toByteArray()
        atomicBytes(file, bytes + java.security.MessageDigest.getInstance("SHA-256").digest(bytes))
    }

    fun obtain(points: List<GeoPoint>, online: Boolean, progress: (Progress) -> Unit): ElevationSeries {
        require(points.isNotEmpty())
        val failures = mutableListOf<SourceFailure>()
        for (source in RANKING) {
            progress(Progress("Recherche des altitudes · ${source.label}", 0, points.size))
            val file = file(source, points)
            cached(file, points.size)?.let { return ElevationSeries(source, it, true, failures) }
            if (!online) {
                failures += SourceFailure(source, "Altitudes absentes du cache hors connexion.")
                continue
            }
            try {
                val z = reader.read(source, points, progress)
                require(z.size == points.size) { "Nombre d'altitudes incorrect." }
                val missing = z.count { !it.isFinite() || it !in -1000.0..9000.0 }
                if (missing > 0) throw MissingCoverage("$missing positions sans altitude utilisable sur ${points.size}.")
                save(file, z)
                return ElevationSeries(source, z, false, failures)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) {
                failures += SourceFailure(source, e.message?.take(220) ?: "Lecture des altitudes impossible.")
            }
        }
        throw IOException(if (!online) "Cette trace n'est pas encore disponible hors connexion. Activez Internet pour son premier calcul."
            else "Aucun modèle n'a pu fournir un profil complet.\n" + failures.joinToString("\n") { "${it.source.label} : ${it.reason}" })
    }
}

data class RgbTile(val size: Int, val pixels: IntArray)

/** Raster readers backed by public source data; no substitution by another dataset. */
class PublicModels(private val directory: File, private val http: HttpTransport,
                   private val decode: (ByteArray) -> RgbTile = ::decodeWebp) : ModelReader {
    companion object {
        private const val IGN_URL = "https://data.geopf.fr/altimetrie/1.0/calcul/alti/rest/elevation.json"
        private const val FAB_BASE = "https://data.bris.ac.uk/datasets/s5hqmjcdj8yo2ibzi9b4ew3sn/"
        fun decodeWebp(bytes: ByteArray): RgbTile {
            val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply { inScaled = false })
                ?: throw IOException("Tuile Mapterhorn illisible.")
            try {
                require(bitmap.width == bitmap.height && bitmap.width in listOf(256, 512))
                val pixels = IntArray(bitmap.width * bitmap.height)
                bitmap.getPixels(pixels, 0, bitmap.width, 0, 0, bitmap.width, bitmap.height)
                return RgbTile(bitmap.width, pixels)
            } finally { bitmap.recycle() }
        }
        fun tileName(lat: Int, lon: Int) = String.format(Locale.ROOT, "%s%02d%s%03d", if (lat >= 0) "N" else "S", abs(lat), if (lon >= 0) "E" else "W", abs(lon))
        fun wrapLon(lon: Double) = ((lon + 180) % 360 + 360) % 360 - 180
    }

    override fun read(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit): DoubleArray {
        directory.mkdirs()
        return when (source) {
            ElevationSource.IGN -> ign(points, progress)
            ElevationSource.MAPTERHORN -> mapterhorn(points, progress)
            ElevationSource.FABDEM, ElevationSource.COPERNICUS -> raster(source, points, progress)
            ElevationSource.SRTM -> srtm(points, progress)
        }
    }

    private fun ign(points: List<GeoPoint>, progress: (Progress) -> Unit): DoubleArray {
        val result = DoubleArray(points.size)
        for (start in points.indices step 5000) {
            http.checkActive()
            val batch = points.subList(start, min(start + 5000, points.size))
            val payload = JSONObject().put("resource", "ign_lidar_hd_mnt_mono_wld")
                .put("delimiter", "|").put("zonly", "true")
                .put("lat", batch.joinToString("|") { String.format(Locale.ROOT, "%.7f", it.lat) })
                .put("lon", batch.joinToString("|") { String.format(Locale.ROOT, "%.7f", it.lon) })
            val body = http.bytes(IGN_URL, body = payload.toString().toByteArray(Charsets.UTF_8)).bytes
            val array = JSONObject(String(body, Charsets.UTF_8)).getJSONArray("elevations")
            require(array.length() == batch.size) { "Réponse IGN incomplète." }
            for (i in batch.indices) {
                val raw = array.get(i)
                result[start + i] = if (raw is JSONObject) raw.optDouble("z", Double.NaN) else (raw as? Number)?.toDouble() ?: Double.NaN
            }
            progress(Progress("Altitudes IGN LiDAR HD", start + batch.size, points.size))
            if (batch.indices.any { !result[start + it].isFinite() || result[start + it] !in -1000.0..9000.0 }) {
                throw MissingCoverage("La trace sort de la couverture IGN LiDAR HD.")
            }
        }
        return result
    }

    private fun mapterhorn(points: List<GeoPoint>, progress: (Progress) -> Unit): DoubleArray {
        val cache = object : LinkedHashMap<String, RgbTile>(8, .75f, true) {
            override fun removeEldestEntry(eldest: MutableMap.MutableEntry<String, RgbTile>?) = size > 8
        }
        val missing = mutableSetOf<String>()
        fun tile(z: Int, x: Int, y: Int): RgbTile {
            val count = 1 shl z
            if (y !in 0 until count) throw MissingCoverage("Position hors de la couverture Mercator.")
            val xx = Math.floorMod(x, count)
            val key = "$z/$xx/$y"
            cache[key]?.let { return it }
            if (key in missing) throw HttpFailure(404, "Tuile Mapterhorn absente.")
            val path = File(directory, "mapterhorn_${z}_${xx}_$y.webp")
            val bytes = if (path.exists()) path.readBytes() else try {
                http.bytes("https://tiles.mapterhorn.com/$key.webp", maximum = 2 * 1024 * 1024).bytes.also { atomicBytes(path, it) }
            } catch (e: HttpFailure) { if (e.status == 404) missing += key; throw e }
            return decode(bytes).also { cache[key] = it }
        }
        fun sample(point: GeoPoint, zoom: Int): Double {
            require(abs(point.lat) <= 85.0511287) { "Latitude hors de la couverture Mapterhorn." }
            val tiles = (1 shl zoom).toDouble()
            val tx = (wrapLon(point.lon) + 180) / 360 * tiles
            val ty = (1 - asinh(tan(Math.toRadians(point.lat))) / PI) / 2 * tiles
            val center = try { tile(zoom, floor(tx).toInt(), floor(ty).toInt()) }
            catch (e: HttpFailure) {
                if (e.status == 404 && zoom > 0) return sample(point, zoom - 1)
                throw e
            }
            val size = center.size
            val gx = tx * size - .5; val gy = ty * size - .5
            val x0 = floor(gx).toInt(); val y0 = floor(gy).toInt()
            var value = 0.0
            for ((px, py, weight) in corners(x0, y0, gx - x0, gy - y0)) {
                if (weight <= 1e-12) continue
                val cornerTile = try { tile(zoom, Math.floorDiv(px, size), Math.floorDiv(py, size)) }
                catch (e: HttpFailure) {
                    if (e.status != 404 || zoom == 0) throw e
                    val lon = wrapLon((px + .5) / (tiles * size) * 360 - 180)
                    val lat = Math.toDegrees(atan(sinh(PI * (1 - 2 * (py + .5) / (tiles * size)))))
                    value += weight * sample(GeoPoint(lat, lon), zoom - 1)
                    continue
                }
                require(cornerTile.size == size) { "Dimensions de tuiles incohérentes." }
                val rgb = cornerTile.pixels[Math.floorMod(py, size) * size + Math.floorMod(px, size)]
                val elevation = ((rgb ushr 16) and 255) * 256.0 + ((rgb ushr 8) and 255) + (rgb and 255) / 256.0 - 32768
                if (elevation <= -32000) return Double.NaN
                value += weight * elevation
            }
            return value
        }
        return DoubleArray(points.size) { i ->
            http.checkActive()
            if (i % 128 == 0) progress(Progress("Altitudes Mapterhorn", i, points.size))
            sample(points[i], 13)
        }
    }

    private fun raster(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit): DoubleArray {
        val blocks = RasterBlocks()
        val rasters = mutableMapOf<Pair<Int, Int>, TiffRaster>()
        val archives = mutableMapOf<String, Pair<ByteSource, List<ZipMember>>>()
        fun open(lat: Int, lon: Int): TiffRaster {
            val key = lat to lon
            rasters[key]?.let { return it }
            val name = tileName(lat, lon)
            val bytes: ByteSource = if (source == ElevationSource.COPERNICUS) {
                val stem = "Copernicus_DSM_COG_10_${name.substring(0, 3)}_00_${name.substring(3)}_00_DEM"
                RemoteByteSource("https://copernicus-dem-30m.s3.amazonaws.com/$stem/$stem.tif", http, directory)
            } else {
                val path = File(directory, "${name}_FABDEM_V1-2.tif")
                if (!path.exists()) {
                    val a = floor(lat / 10.0).toInt() * 10; val b = floor(lon / 10.0).toInt() * 10
                    val archive = "${tileName(a, b)}-${tileName(a + 10, b + 10)}_FABDEM_V1-2.zip"
                    val url = FAB_BASE + archive
                    val (reader, members) = archives.getOrPut(url) {
                        val tail = http.bytes(url, "bytes=-65557")
                        val size = tail.totalSize ?: error("Taille de l'archive FABDEM inconnue.")
                        val remote = RemoteByteSource(url, http, directory)
                        val tailOffset = size - tail.bytes.size
                        val composite = object : ByteSource {
                            override fun read(offset: Long, length: Int) = if (offset >= tailOffset && offset + length <= size) {
                                tail.bytes.copyOfRange((offset - tailOffset).toInt(), (offset - tailOffset).toInt() + length)
                            } else remote.read(offset, length)
                        }
                        composite to RemoteZip.members(composite, size)
                    }
                    val member = members.firstOrNull { it.name.substringAfterLast('/') == path.name }
                        ?: throw MissingCoverage("Tuile FABDEM $name absente.")
                    val offset = RemoteZip.dataOffset(reader, member)
                    progress(Progress("Téléchargement de la tuile FABDEM $name", 0, points.size))
                    http.consumeRange(url, offset, member.compressed) { RemoteZip.extract(it, member, path, http::checkActive) }
                }
                FileByteSource(path)
            }
            return try { TiffRaster(bytes, source.name + name, blocks).also { rasters[key] = it } }
            catch (e: Exception) { bytes.close(); throw e }
        }
        try {
            return DoubleArray(points.size) { i ->
                http.checkActive()
                if (i % 128 == 0) progress(Progress("Altitudes ${source.label}", i, points.size))
                val p = GeoPoint(points[i].lat, wrapLon(points[i].lon))
                val raster = open(floor(p.lat).toInt(), floor(p.lon).toInt())
                val (gx, gy) = raster.grid(p)
                val x = floor(gx).toInt(); val y = floor(gy).toInt()
                var value = 0.0
                for ((col, row, weight) in corners(x, y, gx - x, gy - y)) {
                    if (weight <= 1e-12) continue
                    val z = if (col in 0 until raster.width && row in 0 until raster.height) raster.pixel(col, row) else {
                        val q = raster.position(col, row)
                        val wrapped = GeoPoint(q.lat, wrapLon(q.lon))
                        val neighbor = open(floor(q.lat - 1e-10).toInt(), floor(wrapped.lon + 1e-10).toInt())
                        neighbor.bilinearInside(wrapped)
                    }
                    value += weight * z
                }
                value
            }
        } finally { rasters.values.forEach { it.close() }; archives.values.forEach { it.first.close() } }
    }

    private fun srtm(points: List<GeoPoint>, progress: (Progress) -> Unit): DoubleArray {
        val opened = mutableMapOf<String, RandomAccessFile>()
        val regions = listOf("Eurasia", "Africa", "North_America", "South_America", "Australia", "Islands")
        fun tile(lat: Int, lon: Int): RandomAccessFile {
            val name = tileName(lat, lon)
            opened[name]?.let { return it }
            val path = File(directory, "$name.hgt")
            if (!path.exists() || path.length() != 1201L * 1201 * 2) {
                var found = false
                val hint = when {
                    lon < -30 && lat >= 0 -> "North_America"
                    lon < -30 -> "South_America"
                    lon > 100 && lat < 0 -> "Australia"
                    lat < 38 && lon in -30..60 -> "Africa"
                    else -> "Eurasia"
                }
                for (region in listOf(hint) + regions.filter { it != hint }) {
                    val encoded = try { http.bytes("https://srtm.kurviger.de/SRTM3/$region/$name.hgt.zip").bytes }
                    catch (e: HttpFailure) { if (e.status == 404) continue else throw e }
                    val bytes = ZipInputStream(ByteArrayInputStream(encoded)).use { zip ->
                        val entry = zip.nextEntry ?: throw IOException("Archive SRTM vide.")
                        require(!entry.isDirectory && entry.name.substringAfterLast('/') == "$name.hgt")
                        val result = ByteArray(1201 * 1201 * 2)
                        var n = 0
                        while (n < result.size) {
                            val read = zip.read(result, n, result.size - n)
                            require(read > 0) { "Tuile SRTM tronquée." }; n += read
                        }
                        require(zip.read() == -1)
                        result
                    }
                    atomicBytes(path, bytes); found = true; break
                }
                if (!found) throw MissingCoverage("Tuile SRTM $name absente.")
            }
            return RandomAccessFile(path, "r").also { opened[name] = it }
        }
        try {
            return DoubleArray(points.size) { i ->
                http.checkActive()
                if (i % 128 == 0) progress(Progress("Altitudes SRTM90", i, points.size))
                val p = points[i]; val lat = floor(p.lat).toInt(); val lon = floor(wrapLon(p.lon)).toInt()
                if (lat !in -56 until 60) throw MissingCoverage("Latitude hors de la couverture SRTM90.")
                val file = tile(lat, lon)
                val x = (wrapLon(p.lon) - lon) * 1200; val y = (lat + 1 - p.lat) * 1200
                val x0 = floor(x).toInt(); val y0 = floor(y).toInt()
                var value = 0.0
                for ((col, row, weight) in corners(x0, y0, x - x0, y - y0)) {
                    if (weight <= 1e-12) continue
                    file.seek((min(row, 1200) * 1201L + min(col, 1200)) * 2)
                    val z = file.readShort().toInt()
                    if (z == -32768) return@DoubleArray Double.NaN
                    value += weight * z
                }
                value
            }
        } finally { opened.values.forEach { it.close() } }
    }
}
