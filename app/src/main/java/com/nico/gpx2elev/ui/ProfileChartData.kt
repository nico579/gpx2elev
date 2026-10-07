package com.nico.gpx2elev.ui

import com.nico.gpx2elev.core.ElevationMath
import com.nico.gpx2elev.core.PreparedTrack
import com.nico.gpx2elev.core.Profile
import kotlin.math.max
import kotlin.math.min

internal data class ProfileChartData(
    val terrain: List<Profile>,
    val gpx: List<Profile>,
    val minAltitude: Double,
    val maxAltitude: Double,
)

/** GPX observations keep their native distances, with a separate path for every gap and segment. */
internal fun profileChartData(prepared: PreparedTrack, terrain: List<Profile>): ProfileChartData {
    val observations = mutableListOf<Profile>()
    var distanceOffset = 0.0
    for (segment in prepared.track.segments) {
        if (segment.isEmpty()) continue
        val distances = DoubleArray(segment.size)
        for (i in 1 until segment.size) {
            distances[i] = distances[i - 1] + ElevationMath.distance(segment[i - 1].position, segment[i].position)
        }
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
            terrain.minOf { it.elevation.minOrNull()!! }, terrain.maxOf { it.elevation.maxOrNull()!! })
    }
    return ProfileChartData(terrain, observations, minimum, maximum)
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
