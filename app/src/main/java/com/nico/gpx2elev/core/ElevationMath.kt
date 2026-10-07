package com.nico.gpx2elev.core

import kotlin.math.*

object Protocol {
    const val STEP = 5.0
    const val SIGMA = 20.0
    const val HYSTERESIS = 2.0
    const val MAX_POINTS = 250_000
    const val MAX_SAMPLES = 300_000
    const val MAX_GPX_BYTES = 20 * 1024 * 1024
    const val VERSION = "5m-gaussian20m-odd-extension-hysteresis2m-v1"
}

data class GeoPoint(val lat: Double, val lon: Double)
data class TrackPoint(val position: GeoPoint, val elevation: Double?)
data class Track(val segments: List<List<TrackPoint>>) {
    val pointCount get() = segments.sumOf { it.size }
}
data class SampledSegment(val distance: DoubleArray, val points: List<GeoPoint>, val gpxElevation: DoubleArray?)
data class PreparedTrack(val track: Track, val segments: List<SampledSegment>) {
    val points get() = segments.flatMap { it.points }
    val sampleCount get() = segments.sumOf { it.points.size }
    val length get() = segments.sumOf { it.distance.last() }
}
data class Gain(val up: Double, val down: Double) {
    operator fun plus(other: Gain) = Gain(up + other.up, down + other.down)
}
data class Profile(val distance: DoubleArray, val elevation: DoubleArray)
data class Computed(val gain: Gain, val profiles: List<Profile>, val gpxRaw: Gain?, val gpxFiltered: Gain?) {
    val minAltitude get() = profiles.minOf { it.elevation.minOrNull()!! }
    val maxAltitude get() = profiles.maxOf { it.elevation.maxOrNull()!! }
}

object ElevationMath {
    fun distance(a: GeoPoint, b: GeoPoint): Double {
        val lat1 = Math.toRadians(a.lat)
        val lat2 = Math.toRadians(b.lat)
        val dlat = Math.toRadians(b.lat - a.lat)
        val dlon = Math.toRadians(b.lon - a.lon)
        val h = sin(dlat / 2).pow(2) + cos(lat1) * cos(lat2) * sin(dlon / 2).pow(2)
        return 12_742_000 * asin(sqrt(h.coerceIn(0.0, 1.0)))
    }

    fun prepare(track: Track): PreparedTrack {
        val result = mutableListOf<SampledSegment>()
        var count = 0
        for (segment in track.segments) {
            if (segment.size < 2) continue
            val ds = DoubleArray(segment.size)
            for (i in 1 until segment.size) ds[i] = ds[i - 1] + distance(segment[i - 1].position, segment[i].position)
            // At a stationary point retain the last observation, as in the audited Python implementation.
            val kept = segment.indices.filter { it == segment.lastIndex || ds[it + 1] > ds[it] }
            if (kept.size < 2 || ds.last() == 0.0) continue
            val x = kept.map { ds[it] }.toDoubleArray()
            val lat = kept.map { segment[it].position.lat }.toDoubleArray()
            val lon = kept.map { segment[it].position.lon }.toDoubleArray()
            var crossesDateLine = false
            for (i in 1 until lon.size) {
                val rawDelta = segment[kept[i]].position.lon - segment[kept[i - 1]].position.lon
                if (abs(rawDelta) > 180) crossesDateLine = true
                var delta = rawDelta
                if (delta > 180) delta -= 360
                if (delta < -180) delta += 360
                lon[i] = lon[i - 1] + delta
            }
            val n = ceil(x.last() / Protocol.STEP).toInt()
            require(n > 0 && n < Protocol.MAX_SAMPLES && count + n + 1 <= Protocol.MAX_SAMPLES) {
                "Trace trop longue : maximum ${Protocol.MAX_SAMPLES} positions à 5 m."
            }
            val sampledX = DoubleArray(n + 1) { if (it == n) x.last() else it * Protocol.STEP }
            val points = sampledX.map {
                val longitude = interpolate(x, lon, it)
                GeoPoint(interpolate(x, lat, it), if (crossesDateLine) ((longitude + 180) % 360 + 360) % 360 - 180 else longitude)
            }
            val gps = if (kept.all { segment[it].elevation?.isFinite() == true }) {
                val nativeZ = kept.map { segment[it].elevation!! }.toDoubleArray()
                sampledX.map { interpolate(x, nativeZ, it) }.toDoubleArray().takeIf { values -> values.all { it.isFinite() } }
            } else null
            result += SampledSegment(sampledX, points, gps)
            count += points.size
        }
        require(result.isNotEmpty()) { "Le GPX ne contient aucun parcours avec deux positions distinctes." }
        return PreparedTrack(track, result)
    }

    fun interpolate(x: DoubleArray, y: DoubleArray, position: Double): Double {
        if (position <= x.first()) return y.first()
        if (position >= x.last()) return y.last()
        var lo = 0
        var hi = x.lastIndex
        while (hi - lo > 1) {
            val mid = (lo + hi) / 2
            if (x[mid] <= position) lo = mid else hi = mid
        }
        return y[lo] + (y[hi] - y[lo]) * ((position - x[lo]) / (x[hi] - x[lo]))
    }

    fun gaussian(x: DoubleArray, z: DoubleArray, sigma: Double = Protocol.SIGMA, step: Double = Protocol.STEP): DoubleArray {
        require(x.isNotEmpty() && x.size == z.size && sigma.isFinite() && sigma >= 0 && step.isFinite() && step > 0)
        require(x.all { it.isFinite() } && z.all { it.isFinite() })
        require((1 until x.size).all { x[it] > x[it - 1] })
        if (x.size == 1 || sigma == 0.0) return z.copyOf()
        val length = x.last() - x.first()
        val radius = (4 * sigma / step + .5).toInt()
        val weights = DoubleArray(2 * radius + 1) { exp(-.5 * ((it - radius) * step / sigma).pow(2)) }
        val sum = weights.sum()
        for (i in weights.indices) weights[i] /= sum
        val last = ceil(length / step).toInt()
        // Odd extension preserves constant/linear profiles, including segments shorter than the kernel.
        fun extended(position: Double): Double {
            val q = position - x.first()
            if (q >= 0 && q <= length) return interpolate(x, z, position)
            val period = floor(q / (2 * length))
            val rem = q - period * 2 * length
            val forward = rem <= length
            val reflected = if (forward) rem else 2 * length - rem
            val inside = interpolate(x, z, x.first() + reflected)
            return (if (forward) inside else 2 * z.last() - inside) + 2 * period * (z.last() - z.first())
        }
        val extension = DoubleArray(last + 2 * radius + 1) { extended(x.first() + (it - radius) * step) }
        val filtered = DoubleArray(last + 1) { i ->
            var value = 0.0
            for (k in weights.indices) value += weights[k] * extension[i + k]
            value
        }
        val grid = DoubleArray(last + 1) { x.first() + it * step }
        return x.map { interpolate(grid, filtered, it) }.toDoubleArray()
    }

    fun anchors(z: DoubleArray, threshold: Double = Protocol.HYSTERESIS): IntArray {
        require(z.isNotEmpty() && z.all { it.isFinite() } && threshold.isFinite() && threshold >= 0)
        if (threshold == 0.0) return z.indices.toList().toIntArray()
        val result = mutableListOf(0)
        fun append(i: Int) { if (result.last() != i) result += i }
        var low = 0
        var high = 0
        var extreme = 0
        var direction = 0
        for (i in 1 until z.size) {
            when (direction) {
                0 -> {
                    if (z[i] <= z[low]) low = i
                    if (z[i] >= z[high]) high = i
                    if (z[i] - z[low] >= threshold) {
                        append(low); direction = 1; extreme = i
                    } else if (z[high] - z[i] >= threshold) {
                        append(high); direction = -1; extreme = i
                    }
                }
                1 -> if (z[i] >= z[extreme]) extreme = i else if (z[extreme] - z[i] >= threshold) {
                    append(extreme); direction = -1; extreme = i
                }
                -1 -> if (z[i] <= z[extreme]) extreme = i else if (z[i] - z[extreme] >= threshold) {
                    append(extreme); direction = 1; extreme = i
                }
            }
        }
        if (direction != 0) append(extreme)
        append(z.lastIndex)
        return result.toIntArray()
    }

    fun totals(z: DoubleArray): Gain {
        require(z.isNotEmpty() && z.all { it.isFinite() })
        // Compensated summation prevents small increments being lost on long traces.
        var up = 0.0; var down = 0.0; var upError = 0.0; var downError = 0.0
        for (i in 1 until z.size) {
            val delta = z[i] - z[i - 1]
            require(delta.isFinite()) { "Altitudes non finies." }
            if (delta > 0) {
                val adjusted = delta - upError
                val next = up + adjusted
                upError = (next - up) - adjusted; up = next
            } else {
                val adjusted = -delta - downError
                val next = down + adjusted
                downError = (next - down) - adjusted; down = next
            }
        }
        require(up.isFinite() && down.isFinite()) { "Altitudes non finies." }
        return Gain(up, down)
    }

    fun filteredGain(x: DoubleArray, z: DoubleArray): Pair<Gain, DoubleArray> {
        val smooth = gaussian(x, z)
        val gain = totals(anchors(smooth).map { smooth[it] }.toDoubleArray())
        check(abs(gain.up - gain.down - (smooth.last() - smooth.first())) < 1e-6)
        return gain to smooth
    }

    private fun comparisonGain(operation: () -> Gain): Gain? {
        return try {
            operation().takeIf { it.up.isFinite() && it.down.isFinite() }
        } catch (_: IllegalArgumentException) {
            null
        } catch (_: IllegalStateException) {
            null
        } catch (_: ArithmeticException) {
            null
        }
    }

    fun compute(prepared: PreparedTrack, elevations: DoubleArray): Computed {
        require(elevations.size == prepared.sampleCount && elevations.all { it.isFinite() })
        var offset = 0
        var distanceOffset = 0.0
        var gain = Gain(0.0, 0.0)
        var gpsFiltered: Gain? = Gain(0.0, 0.0)
        val profiles = mutableListOf<Profile>()
        for (segment in prepared.segments) {
            val z = elevations.copyOfRange(offset, offset + segment.points.size)
            val (partGain, filtered) = filteredGain(segment.distance, z)
            gain += partGain
            profiles += Profile(segment.distance.map { it + distanceOffset }.toDoubleArray(), filtered)
            offset += z.size
            distanceOffset += segment.distance.last()
            val previous = gpsFiltered
            gpsFiltered = if (previous != null && segment.gpxElevation != null) {
                comparisonGain { previous + filteredGain(segment.distance, segment.gpxElevation).first }
            } else null
        }
        val nativeSegments = prepared.track.segments.filter { it.size >= 2 }
        val raw = if (nativeSegments.all { segment -> segment.all { it.elevation?.isFinite() == true } }) {
            comparisonGain {
                nativeSegments.fold(Gain(0.0, 0.0)) { accumulator, segment ->
                    accumulator + totals(segment.map { it.elevation!! }.toDoubleArray())
                }
            }
        } else null
        return Computed(gain, profiles, raw, gpsFiltered)
    }
}
