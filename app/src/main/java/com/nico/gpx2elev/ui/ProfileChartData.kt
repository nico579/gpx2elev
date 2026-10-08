package com.nico.gpx2elev.ui

import com.nico.gpx2elev.core.ElevationMath
import com.nico.gpx2elev.core.PreparedTrack
import com.nico.gpx2elev.core.Profile
import com.nico.gpx2elev.core.TrackPoint
import java.time.Instant
import java.time.ZoneId
import java.time.DateTimeException
import java.time.format.DateTimeFormatter
import kotlin.math.abs
import kotlin.math.roundToLong
import kotlin.math.max
import kotlin.math.min

internal data class ProfileChartData(
    val terrain: List<Profile>,
    val gpx: List<Profile>,
    val minAltitude: Double,
    val maxAltitude: Double,
    val observations: List<ProfileObservation> = emptyList(),
)

internal data class ProfileObservation(val distance: Double, val point: TrackPoint, val segment: Int, val terrain: Int)
internal data class ProfileSelection(val distance: Double, val time: Instant?, val terrain: Double?, val gpx: Double?, val interpolated: Boolean = false)

/** GPX observations keep their native distances, with a separate path for every gap and segment. */
internal fun profileChartData(prepared: PreparedTrack, terrain: List<Profile>): ProfileChartData {
    val observations = mutableListOf<Profile>()
    val native = mutableListOf<ProfileObservation>()
    var distanceOffset = 0.0
    var terrainIndex = 0
    for ((segmentIndex, segment) in prepared.track.segments.withIndex()) {
        if (segment.isEmpty()) continue
        val distances = DoubleArray(segment.size)
        for (i in 1 until segment.size) {
            distances[i] = distances[i - 1] + ElevationMath.distance(segment[i - 1].position, segment[i].position)
        }
        val profileIndex = if (distances.last() > 0) terrainIndex++ else -1
        for (i in segment.indices) native += ProfileObservation(distances[i] + distanceOffset, segment[i], segmentIndex, profileIndex)
        val runDistances = mutableListOf<Double>()
        val runElevations = mutableListOf<Double>()
        fun finishRun() {
            if (runDistances.isNotEmpty()) {
                observations += Profile(runDistances.toDoubleArray(), runElevations.toDoubleArray())
                runDistances.clear()
                runElevations.clear()
            }
        }
        for (i in segment.indices) {
            val altitude = segment[i].elevation
            if (altitude == null || !altitude.isFinite()) {
                finishRun()
            } else {
                runDistances += distances[i] + distanceOffset
                runElevations += altitude
            }
        }
        finishRun()
        // Single points and stationary segments consume no distance but remain visible observations.
        distanceOffset += distances.last()
    }
    val allProfiles = terrain + observations
    val minimum = allProfiles.minOf { it.elevation.minOrNull()!! }
    val maximum = allProfiles.maxOf { it.elevation.maxOrNull()!! }
    if (!(maximum - minimum).isFinite()) {
        return ProfileChartData(terrain, emptyList(),
            terrain.minOf { it.elevation.minOrNull()!! }, terrain.maxOf { it.elevation.maxOrNull()!! }, native)
    }
    return ProfileChartData(terrain, observations, minimum, maximum, native)
}

private fun observationBoundary(points: List<ProfileObservation>, value: Double, inclusive: Boolean): Int {
    var lo = 0
    var hi = points.size
    while (lo < hi) {
        val mid = (lo + hi) / 2
        if (points[mid].distance < value || (inclusive && points[mid].distance == value)) lo = mid + 1 else hi = mid
    }
    return lo
}

/** Time ticks never bridge missing timestamps, segment boundaries or clock reversals. */
internal fun profileTimeAt(chart: ProfileChartData, distance: Double): Instant? {
    val points = chart.observations
    val end = observationBoundary(points, distance, true)
    if (end > 0 && points[end - 1].distance == distance) return points[end - 1].point.time
    if (end == 0 || end == points.size) return null
    val a = points[end - 1]
    val b = points[end]
    val start = a.point.time ?: return null
    val finish = b.point.time ?: return null
    if (a.segment != b.segment || finish < start) return null
    val fraction = (distance - a.distance) / (b.distance - a.distance)
    return Instant.ofEpochMilli((start.toEpochMilli() + fraction * (finish.toEpochMilli() - start.toEpochMilli())).roundToLong())
}

/** Snap to a native measurement, using the tap elevation to distinguish points at a stop. */
internal fun selectProfilePoint(chart: ProfileChartData, distance: Double, elevation: Double, viewport: ProfileViewport? = null): ProfileSelection? {
    val points = chart.observations
    if (points.isEmpty() || !distance.isFinite() || !elevation.isFinite()) return null
    val at = observationBoundary(points, distance, false)
    val neighbours = listOf(at.coerceIn(points.indices), (at - 1).coerceIn(points.indices))
    val closest = neighbours.minOf { abs(points[it].distance - distance) }
    val candidates = neighbours.filter { abs(points[it].distance - distance) <= closest + 1e-9 }
        .map { points[it].distance }.distinct().flatMap { x ->
            (observationBoundary(points, x, false) until observationBoundary(points, x, true)).toList()
        }
    val index = candidates.minWith(compareBy<Int> {
        points[it].point.elevation?.takeIf(Double::isFinite)?.let { z -> abs(z - elevation) } ?: Double.POSITIVE_INFINITY
    }.thenByDescending { it })
    val selected = points[index]
    if (viewport != null && selected.distance !in viewport.minDistance..viewport.maxDistance) {
        val end = observationBoundary(points, distance, true)
        if (end in 1 until points.size && points[end - 1].segment == points[end].segment) {
            val a = points[end - 1]
            val b = points[end]
            val f = (distance - a.distance) / (b.distance - a.distance)
            val az = a.point.elevation?.takeIf(Double::isFinite)
            val bz = b.point.elevation?.takeIf(Double::isFinite)
            return ProfileSelection(distance, profileTimeAt(chart, distance),
                chart.terrain.getOrNull(a.terrain)?.let { profileAltitudeAt(it, distance) },
                if (az != null && bz != null) (1 - f) * az + f * bz else null, interpolated = true)
        }
    }
    val profile = chart.terrain.getOrNull(selected.terrain)
    val terrain = profile?.let { profileAltitudeAt(it, selected.distance) }
    return ProfileSelection(selected.distance, selected.point.time, terrain,
        selected.point.elevation?.takeIf(Double::isFinite))
}

private fun profileAltitudeAt(profile: Profile, distance: Double): Double {
    val x = profile.distance
    val index = x.binarySearch(distance)
    if (index >= 0) return profile.elevation[index]
    val right = (-index - 1).coerceIn(1, x.lastIndex)
    val f = ((distance - x[right - 1]) / (x[right] - x[right - 1])).coerceIn(0.0, 1.0)
    return (1 - f) * profile.elevation[right - 1] + f * profile.elevation[right]
}

internal fun profileTimeLabel(time: Instant?, seconds: Boolean = false, language: String = "fr",
    zone: ZoneId = ZoneId.systemDefault(), date: Boolean = false): String {
    if (time == null) return "—"
    val prefix = if (!date) "" else if (language == "fr") "dd/MM/yyyy " else "yyyy-MM-dd "
    return try { DateTimeFormatter.ofPattern(prefix + if (seconds) "HH:mm:ss" else "HH:mm").withZone(zone).format(time) }
        catch (_: DateTimeException) { "—" }
}

internal data class ProfileViewport(
    val minDistance: Double,
    val maxDistance: Double,
    val minAltitude: Double,
    val maxAltitude: Double,
) {
    val distanceSpan get() = maxDistance - minDistance
    val altitudeSpan get() = maxAltitude - minAltitude
}

internal fun fullProfileViewport(chart: ProfileChartData, length: Double): ProfileViewport {
    val range = chart.maxAltitude - chart.minAltitude
    val padding = (max(20.0, range) - range) / 2
    return ProfileViewport(0.0, length, chart.minAltitude - padding, chart.maxAltitude + padding)
}

/** Fractions use plot coordinates; positive screen panning moves the observations with the gesture. */
internal fun transformProfileViewport(
    current: ProfileViewport,
    full: ProfileViewport,
    zoom: Double,
    anchorX: Double = .5,
    anchorY: Double = .5,
    panX: Double = 0.0,
    panY: Double = 0.0,
): ProfileViewport {
    if (!zoom.isFinite() || zoom <= 0 || !panX.isFinite() || !panY.isFinite() || !anchorX.isFinite() || !anchorY.isFinite()) return current
    val width = (current.distanceSpan / zoom).coerceIn(full.distanceSpan / 200, full.distanceSpan)
    val height = (current.altitudeSpan / zoom).coerceIn(full.altitudeSpan / 200, full.altitudeSpan)
    val left = (current.minDistance + anchorX.coerceIn(0.0, 1.0) * (current.distanceSpan - width) - panX * width)
        .coerceIn(full.minDistance, max(full.minDistance, full.maxDistance - width))
    val bottom = (current.minAltitude + anchorY.coerceIn(0.0, 1.0) * (current.altitudeSpan - height) + panY * height)
        .coerceIn(full.minAltitude, max(full.minAltitude, full.maxAltitude - height))
    return ProfileViewport(left, left + width, bottom, bottom + height)
}

/** Re-select native points after every viewport change, keeping neighbours and narrow extrema. */
internal fun visibleProfilePoints(profile: Profile, viewport: ProfileViewport, buckets: Int = 600): List<Pair<Double, Double>> {
    val x = profile.distance
    val z = profile.elevation
    if (x.isEmpty() || x.last() < viewport.minDistance || x.first() > viewport.maxDistance) return emptyList()
    fun boundary(target: Double, inclusive: Boolean): Int {
        var lo = 0
        var hi = x.size
        while (lo < hi) {
            val mid = (lo + hi) / 2
            if (x[mid] < target || (inclusive && x[mid] == target)) lo = mid + 1 else hi = mid
        }
        return lo
    }
    val first = max(0, boundary(viewport.minDistance, false) - 1)
    val last = min(x.lastIndex, boundary(viewport.maxDistance, true))
    val stride = max(1, (last - first + 1) / max(1, buckets))
    val indices = mutableSetOf(first, last)
    for (start in first..last step stride) {
        val end = min(last + 1, start + stride)
        indices += (start until end).minBy { z[it] }
        indices += (start until end).maxBy { z[it] }
    }
    return indices.sorted().map { x[it] to z[it] }
}
