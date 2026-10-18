package com.nico.gpx2elev.data

import com.nico.gpx2elev.core.*
import org.json.JSONObject
import java.io.File
import java.net.URLEncoder
import java.util.Locale
import java.util.concurrent.CancellationException
import kotlin.math.cos

data class ObstacleSnapshot(val data: ObstacleData, val fetchedAt: Long, val cached: Boolean, val notice: String? = null)

/** Bounded public OSM lookup. Cache is independent of elevation data and never stores incomplete replies. */
class ObstacleRepository(private val directory: File, private val http: HttpTransport = HttpTransport(),
    private val fetch: ((String) -> ByteArray)? = null, private val now: () -> Long = System::currentTimeMillis) {
    fun obtain(prepared: PreparedTrack, online: Boolean, refresh: Boolean = false): ObstacleSnapshot {
        val query = query(prepared.points)
        val file = File(directory, sha256("obstacles-v1:" + query) + ".json")
        val cached = try {
            if (file.isFile && file.length() <= MAX_BYTES) ObstacleSnapshot(parse(file.readText()), file.lastModified(), true) else null
        } catch (_: Exception) { null }
        if (cached != null && ((!refresh && now() - cached.fetchedAt <= MAX_AGE) || !online)) {
            return cached.copy(notice = if (!online && now() - cached.fetchedAt > MAX_AGE)
                "Hors connexion : données OSM anciennes (plus de 7 jours). Actualisez dès que possible."
                else if (!online) "Hors connexion : données OSM en cache." else null)
        }
        if (!online) error("Vérification indisponible hors connexion : aucune donnée OSM en cache pour ce parcours.")
        try {
            val url = "https://overpass-api.de/api/interpreter?data=" + URLEncoder.encode(query, "UTF-8")
            val bytes = fetch?.invoke(url) ?: http.bytes(url, maximum = MAX_BYTES).bytes
            require(bytes.size <= MAX_BYTES) { "Réponse OSM trop volumineuse." }
            val data = parse(bytes.toString(Charsets.UTF_8))
            var notice: String? = null
            try {
                atomicBytes(file, bytes)
                file.setLastModified(now())
                val entries = directory.listFiles()?.filter { it.extension == "json" }?.sortedByDescending { it.lastModified() }.orEmpty()
                var size = 0L
                for (entry in entries) { size += entry.length(); if (size > 48L * 1024 * 1024) entry.delete() }
            } catch (_: Exception) { notice = "Les obstacles sont affichés, mais leur cache n'a pas pu être enregistré." }
            return ObstacleSnapshot(data, now(), false, notice)
        } catch (e: CancellationException) { throw e }
        catch (e: Exception) {
            return cached?.copy(notice = "Actualisation OSM impossible : anciennes données en cache.") ?: throw e
        }
    }

    companion object {
        const val MAX_BYTES = 12 * 1024 * 1024
        const val MAX_AGE = 7L * 24 * 60 * 60 * 1000
        fun query(points: List<GeoPoint>): String {
            require(points.isNotEmpty())
            val south = points.minOf { it.lat }; val north = points.maxOf { it.lat }
            val west = points.minOf { it.lon }; val east = points.maxOf { it.lon }
            val longitudeScale = cos(Math.toRadians((south + north) / 2)).coerceAtLeast(.01)
            val height = (north - south) * 111.2; val width = (east - west) * 111.2 * longitudeScale
            require(north < 85 && south > -85 && east - west <= 2 && north - south <= 2 && width * height <= 2500) {
                "Zone trop étendue pour vérifier les obstacles (maximum 2 500 km²). Découpez le parcours."
            }
            val margin = .001 / longitudeScale
            val box = String.format(Locale.ROOT, "%.6f,%.6f,%.6f,%.6f", (south - .001).coerceAtLeast(-90.0),
                (west - margin).coerceAtLeast(-180.0), (north + .001).coerceAtMost(90.0), (east + margin).coerceAtMost(180.0))
            return "[out:json][timeout:25][maxsize:16000000];(node[\"barrier\"]($box);node[\"entrance\"]($box);)->.b;" +
                "(.b;way[\"barrier\"]($box);way(bn.b)[\"highway\"];);out body geom;"
        }
        fun parse(json: String): ObstacleData {
            val root = JSONObject(json)
            require(!root.has("remark")) { "Réponse OSM incomplète ; réessayez plus tard." }
            val elements = root.getJSONArray("elements")
            require(elements.length() <= 80000) { "Trop d'objets OSM dans cette zone." }
            val barriers = mutableListOf<OsmBarrier>(); val roads = mutableListOf<OsmRoad>()
            var coordinates = 0
            fun point(obj: JSONObject): GeoPoint {
                val lat = obj.getDouble("lat"); val lon = obj.getDouble("lon")
                require(lat.isFinite() && lon.isFinite() && lat in -90.0..90.0 && lon in -180.0..180.0) { "Coordonnées OSM invalides." }
                coordinates++
                require(coordinates <= 250000) { "Géométries OSM trop volumineuses." }
                return GeoPoint(lat, lon)
            }
            for (i in 0 until elements.length()) {
                val element = elements.getJSONObject(i)
                val tagObject = element.optJSONObject("tags") ?: continue
                val tags = tagObject.keys().asSequence().associateWith { tagObject.getString(it) }
                val type = element.getString("type"); val id = element.getLong("id")
                val points: List<GeoPoint>; val nodes: List<Long>
                if (type == "node") { points = listOf(point(element)); nodes = listOf(id) }
                else if (type == "way") {
                    val geometry = element.getJSONArray("geometry")
                    points = (0 until geometry.length()).map { point(geometry.getJSONObject(it)) }
                    val nodeArray = element.getJSONArray("nodes")
                    nodes = (0 until nodeArray.length()).map { nodeArray.getLong(it) }
                    require(points.size == nodes.size && points.size >= 2) { "Géométrie OSM incomplète." }
                } else continue
                if (tags.containsKey("barrier") || tags.containsKey("entrance")) barriers += OsmBarrier("$type/$id", points, tags, nodes)
                if (type == "way" && tags.containsKey("highway")) roads += OsmRoad(points, nodes, tags)
            }
            return ObstacleData(barriers, roads)
        }
    }
}
