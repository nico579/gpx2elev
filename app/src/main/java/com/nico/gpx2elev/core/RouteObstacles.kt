package com.nico.gpx2elev.core

import kotlin.math.*

enum class TravelMode(val tag: String, val label: String) { FOOT("foot", "À pied"), BICYCLE("bicycle", "Vélo"), MOTOR_VEHICLE("motor_vehicle", "Véhicule") }
enum class ObstacleLevel { BLOCKED, UNCERTAIN }
data class OsmBarrier(val id: String, val points: List<GeoPoint>, val tags: Map<String, String>, val nodeIds: List<Long> = emptyList())
data class OsmRoad(val points: List<GeoPoint>, val nodeIds: List<Long>, val tags: Map<String, String>)
data class ObstacleData(val barriers: List<OsmBarrier>, val roads: List<OsmRoad> = emptyList())
data class RouteObstacle(val id: String, val position: GeoPoint, val segment: Int, val distance: Double, val localDistance: Double,
    val level: ObstacleLevel, val label: String, val reason: String)
data class ObstacleReport(val events: List<RouteObstacle>, val reverse: Boolean, val mode: TravelMode, val length: Double) {
    val blocked get() = events.count { it.level == ObstacleLevel.BLOCKED }
    val uncertain get() = events.count { it.level == ObstacleLevel.UNCERTAIN }
}

/** Local intersections only: a fence beside the path never blocks it. GPX segment gaps are excluded. */
object RouteObstacles {
    const val HIGHLIGHT_METERS = 25.0
    private const val NODE_TOLERANCE = 8.0
    private val openings = setOf("gate", "lift_gate", "swing_gate", "kissing_gate", "stile", "entrance", "gap", "sally_port", "cycle_barrier")
    private val solid = setOf("fence", "wall", "retaining_wall", "hedge", "city_wall", "jersey_barrier")
    private val allowed = setOf("yes", "designated", "official", "permissive")
    private fun kind(tags: Map<String, String>) = tags["barrier"] ?: if (tags.containsKey("entrance")) "entrance" else "inconnu"
    private data class XY(val x: Double, val y: Double) {
        operator fun minus(other: XY) = XY(x - other.x, y - other.y)
        operator fun plus(other: XY) = XY(x + other.x, y + other.y)
        operator fun times(scale: Double) = XY(x * scale, y * scale)
        fun dot(other: XY) = x * other.x + y * other.y
        fun cross(other: XY) = x * other.y - y * other.x
        fun norm() = hypot(x, y)
    }
    private data class Edge(val barrier: Int, val a: XY, val b: XY)
    private fun closest(point: XY, a: XY, b: XY): Pair<Double, Double> {
        val ab = b - a
        val t = if (ab.dot(ab) == 0.0) 0.0 else ((point - a).dot(ab) / ab.dot(ab)).coerceIn(0.0, 1.0)
        return t to (point - (a + ab * t)).norm()
    }
    private fun intersection(a: XY, b: XY, c: XY, d: XY): Double? {
        val ab = b - a; val cd = d - c; val cross = ab.cross(cd)
        if (abs(cross) < 1e-8 * max(1.0, ab.norm() * cd.norm())) return null
        val t = (c - a).cross(cd) / cross; val u = (c - a).cross(ab) / cross
        return t.takeIf { it >= -1e-7 && it <= 1.0000001 && u >= -1e-7 && u <= 1.0000001 }?.coerceIn(0.0, 1.0)
    }
    private fun label(barrier: OsmBarrier): String = barrier.tags["name"] ?: when (kind(barrier.tags)) {
        "fence" -> "Clôture"; "wall", "city_wall", "retaining_wall" -> "Mur"; "hedge" -> "Haie"
        "gate", "swing_gate" -> "Portail"; "lift_gate" -> "Barrière levante"; "stile" -> "Échalier"
        "cycle_barrier" -> "Chicane"; "bollard" -> "Borne"; else -> "Obstacle (" + (barrier.tags["barrier"] ?: "inconnu") + ")"
    }
    private fun decision(tags: Map<String, String>, mode: TravelMode, direction: String?, parent: Map<String, String> = emptyMap()): Pair<ObstacleLevel, String>? {
        val kind = kind(tags)
        if (tags["entrance"] == "no") return ObstacleLevel.BLOCKED to "Ouverture condamnée selon OpenStreetMap."
        if (kind in setOf("no", "kerb", "flush", "lowered")) return null
        val keys = when (mode) {
            TravelMode.FOOT -> listOf("foot", "access")
            TravelMode.BICYCLE -> listOf("bicycle", "vehicle", "access")
            TravelMode.MOTOR_VEHICLE -> listOf("motor_vehicle", "vehicle", "access")
        }
        val combined = parent + tags
        // The obstacle's own access rules take precedence; roads supply missing rules.
        fun access(source: Map<String, String>) = keys.firstNotNullOfOrNull { key -> direction?.let { source[key + ":" + it] } ?: source[key] }
        val source = if (access(tags) != null) tags else parent
        val value = access(source)
        val forbidden = value in setOf("no", "private", "use_sidepath")
        val rank = keys.indexOfFirst { key -> (direction != null && source.containsKey(key + ":" + direction)) || source.containsKey(key) }
            .let { if (it < 0) keys.size else it }
        val conditions = combined.keys.filter { it.substringBefore(':') in keys && it.endsWith(":conditional") }
            .map { keys.indexOf(it.substringBefore(':')) }
        // An explicit prohibition only yields to a condition on a key at least as specific as the one that sets it:
        // opening hours or a general access:conditional never lift foot=no.
        val doubtful = if (forbidden) conditions.any { it <= rank } else conditions.isNotEmpty() ||
            combined.containsKey("opening_hours") || combined.containsKey("oneway:" + mode.tag + ":conditional") ||
            (mode != TravelMode.FOOT && (combined.containsKey("oneway:conditional") || combined.containsKey("oneway:vehicle:conditional")))
        if (doubtful) return ObstacleLevel.UNCERTAIN to "Accès conditionnel : vérifier les conditions sur place."
        if (direction == null && combined.keys.any { it.substringBefore(':') in keys && (it.endsWith(":forward") || it.endsWith(":backward")) })
            return ObstacleLevel.UNCERTAIN to "Restriction selon le sens ; orientation OSM indéterminée."
        val oneway = combined["oneway:" + mode.tag] ?: if (mode != TravelMode.FOOT) combined["oneway"] else null
        if (oneway in setOf("yes", "1", "true", "-1")) {
            if (direction == null) return ObstacleLevel.UNCERTAIN to "Restriction selon le sens ; orientation OSM indéterminée."
            if ((oneway == "-1" && direction == "forward") || (oneway != "-1" && direction == "backward"))
                return ObstacleLevel.BLOCKED to "Sens interdit pour ce mode de déplacement selon OpenStreetMap."
        }
        if (forbidden) return ObstacleLevel.BLOCKED to ("Accès " + value + " pour " + mode.label.lowercase() + " dans ce sens.")
        if (kind == "entrance" && tags["entrance"] in setOf("emergency", "exit", "entrance"))
            return ObstacleLevel.UNCERTAIN to "Ouverture réservée ou à sens limité : vérifier le passage."
        if (tags["locked"] == "yes") return if (mode != TravelMode.MOTOR_VEHICLE && value in allowed)
            ObstacleLevel.UNCERTAIN to "Accès autorisé mais obstacle indiqué verrouillé : vérifier le passage."
            else ObstacleLevel.BLOCKED to "Verrouillé selon OpenStreetMap."
        if (value in allowed) return null
        if (value != null) return ObstacleLevel.UNCERTAIN to ("Accès soumis à une restriction : " + value + ".")
        if (kind in solid) return ObstacleLevel.BLOCKED to "Le tracé traverse un obstacle continu sans ouverture cartographiée."
        if (kind == "entrance" && !tags.containsKey("barrier")) return ObstacleLevel.UNCERTAIN to "Entrée cartographiée ; passage à vérifier."
        if (kind in setOf("entrance", "gap")) return null
        if (kind == "bollard" && mode != TravelMode.MOTOR_VEHICLE) return null
        if (kind in setOf("cycle_barrier", "kissing_gate", "stile") && mode == TravelMode.FOOT) return null
        if (kind in setOf("bollard", "block", "cycle_barrier", "stile", "kissing_gate") && mode == TravelMode.MOTOR_VEHICLE)
            return ObstacleLevel.BLOCKED to "Obstacle physique au passage d'un véhicule."
        return ObstacleLevel.UNCERTAIN to "Passage et ouverture non confirmés dans OpenStreetMap."
    }

    fun analyze(prepared: PreparedTrack, data: ObstacleData, mode: TravelMode = TravelMode.FOOT, reverse: Boolean = false): ObstacleReport {
        val origin = prepared.segments.first().points.first()
        val scaleX = 111195.0 * cos(Math.toRadians(origin.lat)).coerceAtLeast(.000001)
        fun project(p: GeoPoint) = XY((((p.lon - origin.lon + 540) % 360) - 180) * scaleX, (p.lat - origin.lat) * 111195.0)
        fun point(p: XY) = GeoPoint(origin.lat + p.y / 111195.0, ((origin.lon + p.x / scaleX + 540) % 360) - 180)
        fun cell(x: Double) = floor(x / 100.0).toInt()
        val grid = HashMap<Pair<Int, Int>, MutableList<Edge>>()
        val positions = data.barriers.map { it.points.map(::project) }
        for ((index, coordinates) in positions.withIndex()) {
            val edges = if (coordinates.size == 1) listOf(Edge(index, coordinates[0], coordinates[0]))
                else coordinates.zipWithNext { a, b -> Edge(index, a, b) }
            for (edge in edges) {
                val steps = ceil((edge.b - edge.a).norm() / 75.0).toInt().coerceAtLeast(1)
                require(steps <= 20000) { "Géométrie OSM trop étendue." }
                val cells = HashSet<Pair<Int, Int>>()
                for (step in 0 until steps) {
                    val p = edge.a + (edge.b - edge.a) * (step.toDouble() / steps)
                    val q = edge.a + (edge.b - edge.a) * ((step + 1.0) / steps)
                    for (x in cell(min(p.x, q.x) - NODE_TOLERANCE)..cell(max(p.x, q.x) + NODE_TOLERANCE)) {
                        for (y in cell(min(p.y, q.y) - NODE_TOLERANCE)..cell(max(p.y, q.y) + NODE_TOLERANCE)) {
                            cells += x to y
                        }
                    }
                }
                cells.forEach { grid.getOrPut(it) { mutableListOf() }.add(edge) }
            }
        }
        val parentRoads = HashMap<Long, MutableList<OsmRoad>>()
        for (road in data.roads) {
            for (node in road.nodeIds) {
                parentRoads.getOrPut(node) { mutableListOf() }.add(road)
            }
        }
        val found = mutableListOf<RouteObstacle>()
        val lastCrossing = HashMap<Pair<Int, Int>, Pair<Double, XY>>()
        var offset = 0.0
        for ((segmentIndex, segment) in prepared.segments.withIndex()) {
            val xy = segment.points.map(::project)
            for (i in 0 until xy.lastIndex) {
                val a = xy[i]; val b = xy[i + 1]; val vector = b - a
                if (vector.norm() < 1e-8) continue
                val candidates = mutableSetOf<Edge>()
                for (x in cell(min(a.x, b.x) - NODE_TOLERANCE)..cell(max(a.x, b.x) + NODE_TOLERANCE)) {
                    for (y in cell(min(a.y, b.y) - NODE_TOLERANCE)..cell(max(a.y, b.y) + NODE_TOLERANCE)) {
                        grid[x to y]?.let { candidates.addAll(it) }
                    }
                }
                for (edge in candidates) {
                    val barrier = data.barriers[edge.barrier]
                    val t = if (barrier.points.size == 1) {
                        val near = closest(edge.a, a, b)
                        if (near.second > NODE_TOLERANCE) continue
                        if (near.first == 0.0 && i > 0 && closest(edge.a, xy[i - 1], a).second <= near.second) continue
                        if (near.first == 1.0 && i + 2 < xy.size && closest(edge.a, b, xy[i + 2]).second < near.second) continue
                        near.first
                    } else intersection(a, b, edge.a, edge.b) ?: continue
                    val crossing = a + vector * t
                    if (kind(barrier.tags) in solid && candidates.any { candidate ->
                        kind(data.barriers[candidate.barrier].tags) in openings &&
                            data.barriers[candidate.barrier].tags["entrance"] != "no" &&
                            data.barriers[candidate.barrier].points.size == 1 && (candidate.a - crossing).norm() <= 3.0 &&
                            (data.barriers[candidate.barrier].nodeIds.any { it in barrier.nodeIds } || closest(candidate.a, edge.a, edge.b).second <= .5)
                    }) continue
                    val local = segment.distance[i] + (segment.distance[i + 1] - segment.distance[i]) * t
                    val previous = lastCrossing[segmentIndex to edge.barrier]
                    if (previous != null && (abs(local - previous.first) < .05 ||
                        (barrier.points.size == 1 && abs(local - previous.first) <= NODE_TOLERANCE * 2 && previous.second.dot(vector) > 0))) continue
                    val contexts = mutableListOf<Pair<ObstacleLevel, String>?>()
                    for (road in barrier.nodeIds.flatMap { parentRoads[it].orEmpty() }.distinct()) {
                        val roadXY = road.points.map(::project)
                        val nearest = roadXY.zipWithNext().minByOrNull { closest(crossing, it.first, it.second).second } ?: continue
                        if (closest(crossing, nearest.first, nearest.second).second > 12.0) continue
                        val roadVector = nearest.second - nearest.first
                        val alignment = vector.dot(roadVector) / (vector.norm() * roadVector.norm()).coerceAtLeast(1e-10)
                        if (abs(alignment) < .7) continue
                        val direction = if ((alignment > 0) != reverse) "forward" else "backward"
                        contexts += decision(barrier.tags, mode, direction, road.tags)
                    }
                    var decision = when {
                        contexts.isEmpty() -> decision(barrier.tags, mode, null)
                        contexts.all { it == contexts.first() } -> contexts.first()
                        else -> ObstacleLevel.UNCERTAIN to "Restriction selon le sens ; orientation OSM indéterminée."
                    } ?: continue
                    if (barrier.points.size == 1 && closest(edge.a, a, b).second > 3.0)
                        decision = ObstacleLevel.UNCERTAIN to "Obstacle proche du tracé ; le franchissement reste à confirmer."
                    if (barrier.points.size > 1) {
                        val before = xy[maxOf(0, i - 1)] - edge.a
                        val after = xy[minOf(xy.lastIndex, i + 2)] - edge.a
                        val boundary = edge.b - edge.a
                        if (boundary.cross(before) * boundary.cross(after) >= 0 || (barrier.tags["layer"] ?: "0") != "0")
                            decision = ObstacleLevel.UNCERTAIN to "Intersection ou niveau de franchissement à confirmer"
                    }
                    lastCrossing[segmentIndex to edge.barrier] = local to vector
                    val distance = offset + local
                    found += RouteObstacle(barrier.id, point(crossing), segmentIndex, if (reverse) prepared.length - distance else distance,
                        local, decision.first, label(barrier), decision.second)
                }
            }
            offset += segment.distance.last()
        }
        return ObstacleReport(found.sortedBy { it.distance }, reverse, mode, prepared.length)
    }
}
