package com.nico.gpx2elev

import com.nico.gpx2elev.core.*
import com.nico.gpx2elev.data.ObstacleRepository
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ObstacleRepositoryTest {
    @get:Rule val temporary = TemporaryFolder()
    private val route = ElevationMath.prepare(Track(listOf(listOf(TrackPoint(GeoPoint(45.0, 5.0), null), TrackPoint(GeoPoint(45.001, 5.001), null)))))
    private val response = """{"elements":[{"type":"node","id":1,"lat":45,"lon":5,"tags":{"barrier":"gate"}}]}""".toByteArray()

    @Test fun cachesOfflineAndRefreshFailureKeepsThePreviousData() {
        var calls = 0; var fail = false; var now = 1000000000L
        val repository = ObstacleRepository(temporary.newFolder(), fetch = { calls++; if (fail) error("network down"); response }, now = { now })
        assertFalse(repository.obtain(route, true).cached)
        assertTrue(repository.obtain(route, false).cached)
        assertEquals(1, calls)
        now += ObstacleRepository.MAX_AGE + 1
        assertTrue(repository.obtain(route, false).notice!!.contains("plus de 7 jours"))
        fail = true
        val old = repository.obtain(route, true)
        assertTrue(old.cached)
        assertTrue(old.notice!!.contains("impossible"))
        assertEquals(2, calls)
    }
    @Test fun missingOfflineDataIsNotReportedAsAClearRoute() {
        val repository = ObstacleRepository(temporary.newFolder(), fetch = { fail("No network request offline"); response })
        try { repository.obtain(route, false); fail("Must report unavailable") } catch (e: IllegalStateException) { assertTrue(e.message!!.contains("hors connexion")) }
    }
    @Test fun partialReplyAndInvalidGeometryAreRejected() {
        for (json in listOf("""{"remark":"runtime error","elements":[]}""", """{"elements":[{"type":"node","id":1,"lat":95,"lon":5,"tags":{"barrier":"gate"}}]}""")) {
            try { ObstacleRepository.parse(json); fail("Invalid response accepted") } catch (_: IllegalArgumentException) { }
        }
    }
    @Test fun parentWayNodeOrderIsPreservedForDirection() {
        val data = ObstacleRepository.parse("""{"elements":[{"type":"way","id":7,"nodes":[9,1],"geometry":[{"lat":45,"lon":5.01},{"lat":45,"lon":5}],"tags":{"highway":"path","foot:forward":"no"}}]}""")
        assertEquals(listOf(9L, 1L), data.roads.single().nodeIds)
        assertEquals("no", data.roads.single().tags["foot:forward"])
    }
    @Test fun oversizedAreasAndDatelineCrossingsAreExplicitlyRejected() {
        for (points in listOf(listOf(GeoPoint(45.0, 5.0), GeoPoint(48.0, 8.0)), listOf(GeoPoint(45.0, 179.9), GeoPoint(45.0, -179.9)))) {
            try { ObstacleRepository.query(points); fail("Unbounded query") } catch (_: IllegalArgumentException) { }
        }
        assertTrue(ObstacleRepository.query(route.points).contains("way(bn.b)"))
    }
}
