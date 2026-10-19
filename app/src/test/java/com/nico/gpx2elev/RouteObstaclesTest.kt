package com.nico.gpx2elev

import com.nico.gpx2elev.core.*
import org.junit.Assert.*
import org.junit.Test

class RouteObstaclesTest {
    private fun p(x: Double, y: Double = 0.0) = GeoPoint(45.0 + y / 111195.0, 5.0 + x / 78626.0)
    private fun track(vararg parts: List<GeoPoint>) = ElevationMath.prepare(Track(parts.map { points -> points.map { TrackPoint(it, null) } }))
    private fun gate(x: Double, y: Double = 0.0, tags: Map<String, String> = emptyMap()) = OsmBarrier("node/1", listOf(p(x, y)), mapOf("barrier" to "gate") + tags, listOf(1))
    private val route get() = track(listOf(p(0.0), p(200.0)))
    private fun fence() = OsmBarrier("way/2", listOf(p(80.0, -20.0), p(80.0, 20.0)), mapOf("barrier" to "fence"))
    private fun analyze(vararg barriers: OsmBarrier) = RouteObstacles.analyze(route, ObstacleData(barriers.toList()))

    @Test fun crossingFenceBlocksButParallelFenceDoesNot() {
        assertEquals(1, analyze(fence()).blocked)
        val parallel = OsmBarrier("way/3", listOf(p(0.0, 1.0), p(200.0, 1.0)), mapOf("barrier" to "fence"))
        assertTrue(analyze(parallel).events.isEmpty())
    }
    @Test fun unknownGateIsUncertainAndFootPermissionOverridesGenericDenial() {
        assertEquals(1, analyze(gate(80.0)).uncertain)
        assertTrue(analyze(gate(80.0, tags = mapOf("access" to "no", "foot" to "yes"))).events.isEmpty())
        assertEquals(1, analyze(gate(80.0, tags = mapOf("foot" to "no"))).blocked)
    }
    @Test fun openingSuppressesOnlyTheFenceItActuallyBelongsTo() {
        assertTrue(analyze(fence(), gate(80.0, tags = mapOf("foot" to "yes"))).events.isEmpty())
        assertEquals(1, analyze(fence(), gate(82.0, tags = mapOf("foot" to "yes"))).blocked)
        assertEquals(1, analyze(fence(), gate(80.0)).uncertain)
    }
    @Test fun nearbyGateIsNotClaimedToBlockTheRoute() {
        assertEquals(1, analyze(gate(80.0, 6.0, mapOf("access" to "no"))).uncertain)
        assertTrue(analyze(gate(80.0, 12.0)).events.isEmpty())
    }
    @Test fun touchingFenceAndDifferentLevelRemainUncertain() {
        val touching = track(listOf(p(0.0), p(80.0), p(0.0)))
        val peakLongitude = touching.points.maxOf { it.lon }
        val tangentFence = fence().copy(points = fence().points.map { GeoPoint(it.lat, peakLongitude) })
        val report = RouteObstacles.analyze(touching, ObstacleData(listOf(tangentFence)))
        assertEquals(0, report.blocked)
        assertTrue(report.uncertain > 0)
        assertEquals(1, analyze(fence().copy(tags = mapOf("barrier" to "fence", "layer" to "1"))).uncertain)
    }
    @Test fun cycleBarrierIsAMappedPedestrianOpening() {
        val opening = gate(80.0, tags = mapOf("barrier" to "cycle_barrier"))
        assertTrue(analyze(fence(), opening).events.isEmpty())
        val block = gate(80.0, tags = mapOf("barrier" to "block"))
        assertEquals(0, analyze(block).blocked)
        assertEquals(1, RouteObstacles.analyze(route, ObstacleData(listOf(block)), TravelMode.MOTOR_VEHICLE).blocked)
    }
    @Test fun repeatedVisitsRemainAndReverseReordersDistance() {
        val outAndBack = track(listOf(p(0.0), p(200.0), p(0.0)))
        val data = ObstacleData(listOf(gate(80.0, tags = mapOf("access" to "no"))))
        val report = RouteObstacles.analyze(outAndBack, data)
        assertEquals(2, report.events.size)
        assertEquals(80.0, report.events.first().distance, .1)
        assertEquals(320.0, report.events.last().distance, .1)
        val reversed = RouteObstacles.analyze(route, data, reverse = true)
        assertEquals(120.0, reversed.events.single().distance, .1)
        assertEquals(80.0, reversed.events.single().localDistance, .1)
    }
    @Test fun disjointGpxSegmentsAreNotConnectedAcrossABarrier() {
        val disconnected = track(listOf(p(0.0), p(50.0)), listOf(p(100.0), p(200.0)))
        assertTrue(RouteObstacles.analyze(disconnected, ObstacleData(listOf(fence()))).events.isEmpty())
    }
    @Test fun directionalRestrictionUsesParentWayOrientationAndReverses() {
        val barrier = gate(80.0, tags = mapOf("foot:forward" to "no", "foot:backward" to "yes"))
        val road = OsmRoad(listOf(p(0.0), p(80.0), p(200.0)), listOf(7, 1, 9), mapOf("highway" to "path"))
        val data = ObstacleData(listOf(barrier), listOf(road))
        assertEquals(1, RouteObstacles.analyze(route, data).blocked)
        assertTrue(RouteObstacles.analyze(route, data, reverse = true).events.isEmpty())
        assertEquals(1, RouteObstacles.analyze(route, ObstacleData(listOf(barrier))).uncertain)
    }
    @Test fun travelModeChangesPhysicalPassabilityAndConditionalAccessStaysUncertain() {
        val bollard = OsmBarrier("node/3", listOf(p(80.0)), mapOf("barrier" to "bollard"))
        assertTrue(analyze(bollard).events.isEmpty())
        assertEquals(1, RouteObstacles.analyze(route, ObstacleData(listOf(bollard)), TravelMode.MOTOR_VEHICLE).blocked)
        assertEquals(1, analyze(gate(80.0, tags = mapOf("foot" to "yes", "foot:conditional" to "no @ (sunset-sunrise)"))).uncertain)
        assertEquals(1, analyze(gate(80.0, tags = mapOf("foot" to "yes", "locked" to "yes"))).uncertain)
    }
    @Test fun sharedVertexAndLongDiagonalGridEdgesOnlyYieldOneCrossing() {
        val diagonal = OsmBarrier("way/2", listOf(p(-250.0, -340.0), p(410.0, 340.0)), mapOf("barrier" to "fence"))
        assertEquals(1, analyze(diagonal).blocked)
        val vertex = OsmBarrier("way/3", listOf(p(80.0, -20.0), p(80.0), p(80.0, 20.0)), mapOf("barrier" to "fence"))
        assertEquals(1, analyze(vertex).blocked)
    }
    @Test fun genericOnewayDoesNotRestrictFootAndModeSpecificDirectionDoesRestrictCycling() {
        val barrier = gate(80.0, tags = mapOf("foot" to "yes", "bicycle" to "yes"))
        val road = OsmRoad(listOf(p(0.0), p(80.0), p(200.0)), listOf(7, 1, 9), mapOf("highway" to "path", "oneway" to "yes"))
        val data = ObstacleData(listOf(barrier), listOf(road))
        assertTrue(RouteObstacles.analyze(route, data, reverse = true).events.isEmpty())
        assertTrue(RouteObstacles.analyze(route, data, TravelMode.BICYCLE).events.isEmpty())
        assertEquals(1, RouteObstacles.analyze(route, data, TravelMode.BICYCLE, reverse = true).blocked)
    }
    @Test fun sealedEntranceDoesNotOpenFenceAndLimitedEntrancesStayUncertain() {
        val sealed = OsmBarrier("node/1", listOf(p(80.0)), mapOf("entrance" to "no"))
        assertEquals(2, analyze(fence(), sealed).blocked)
        for (value in listOf("exit", "entrance", "emergency", "yes")) {
            val entrance = sealed.copy(tags = mapOf("entrance" to value))
            assertEquals(1, analyze(fence(), entrance).uncertain)
            assertEquals(0, analyze(fence(), entrance).blocked)
        }
    }
    @Test fun aVeryShortReturnKeepsBothPassages() {
        val route = track(listOf(p(0.0), p(84.0), p(0.0)))
        val data = ObstacleData(listOf(gate(80.0)))
        assertEquals(2, RouteObstacles.analyze(route, data).events.size)
    }
    @Test fun conditionalOnewayIsUncertainOnlyForTheModesItAppliesTo() {
        val barrier = gate(80.0, tags = mapOf("foot" to "yes", "bicycle" to "yes"))
        val road = OsmRoad(listOf(p(0.0), p(80.0), p(200.0)), listOf(7, 1, 9),
            mapOf("highway" to "path", "oneway" to "yes", "oneway:conditional" to "no @ (Sa-Su)"))
        val data = ObstacleData(listOf(barrier), listOf(road))
        assertTrue(RouteObstacles.analyze(route, data, reverse = true).events.isEmpty())
        assertEquals(1, RouteObstacles.analyze(route, data, TravelMode.BICYCLE, reverse = true).uncertain)
        val footRoad = road.copy(tags = mapOf("highway" to "path", "oneway:foot:conditional" to "yes @ (Mo-Fr)"))
        assertEquals(1, RouteObstacles.analyze(route, data.copy(roads = listOf(footRoad)), reverse = true).uncertain)
    }
    @Test fun openingInheritsGeneralParentAccessWhenItHasNoOwnPermission() {
        val opening = gate(80.0, tags = mapOf("barrier" to "entrance"))
        val road = OsmRoad(listOf(p(0.0), p(80.0), p(200.0)), listOf(7, 1, 9),
            mapOf("highway" to "path", "foot" to "no"))
        val report = RouteObstacles.analyze(route, ObstacleData(listOf(opening), listOf(road)))
        assertEquals(1, report.events.size)
        assertEquals(1, report.blocked)
        assertEquals(0, report.uncertain)
    }
    @Test fun nodeFootPermissionOverridesGeneralParentDenial() {
        val barrier = gate(80.0, tags = mapOf("foot" to "yes"))
        val road = OsmRoad(listOf(p(0.0), p(80.0), p(200.0)), listOf(7, 1, 9),
            mapOf("highway" to "path", "access" to "no"))
        val data = ObstacleData(listOf(barrier), listOf(road))
        assertTrue(RouteObstacles.analyze(route, data).events.isEmpty())
        assertEquals(1, RouteObstacles.analyze(route, data.copy(barriers = listOf(gate(80.0)))).blocked)
    }
    @Test fun onlyAConditionAsSpecificAsTheProhibitionMakesItUncertain() {
        // Opening hours say when a gate is open, not who may pass; access:conditional is more general than foot=no.
        for (tags in listOf(mapOf("foot" to "no", "opening_hours" to "24/7"),
                            mapOf("foot" to "private", "opening_hours" to "Mo-Fr 09:00-17:00"),
                            mapOf("foot" to "no", "access:conditional" to "yes @ (Mo-Fr)")))
            assertEquals(tags.toString(), 1, analyze(gate(80.0, tags = tags)).blocked)
        for (tags in listOf(mapOf("foot" to "no", "foot:conditional" to "no @ (sunset-sunrise)"),
                            mapOf("access" to "no", "foot:conditional" to "yes @ (Mo-Fr)"),
                            mapOf("opening_hours" to "Mo-Fr 09:00-17:00")))
            assertEquals(tags.toString(), 1, analyze(gate(80.0, tags = tags)).uncertain)
    }
    @Test fun prohibitionByTheWayIgnoresTheGateOpeningHours() {
        val road = OsmRoad(listOf(p(0.0), p(80.0), p(200.0)), listOf(7, 1, 9), mapOf("highway" to "path", "foot" to "no"))
        val data = ObstacleData(listOf(gate(80.0, tags = mapOf("opening_hours" to "24/7"))), listOf(road))
        assertEquals(1, RouteObstacles.analyze(route, data).blocked)
    }
    @Test fun matchingRestrictionsSurviveAParentWaySplitAtTheGate() {
        val barrier = gate(80.0, tags = mapOf("bicycle" to "yes"))
        val tags = mapOf("highway" to "cycleway", "oneway" to "yes")
        val before = OsmRoad(listOf(p(0.0), p(80.0)), listOf(7, 1), tags)
        val after = OsmRoad(listOf(p(80.0), p(200.0)), listOf(1, 9), tags)
        val data = ObstacleData(listOf(barrier), listOf(before, after))
        assertTrue(RouteObstacles.analyze(route, data, TravelMode.BICYCLE).events.isEmpty())
        val reverse = RouteObstacles.analyze(route, data, TravelMode.BICYCLE, reverse = true)
        assertEquals(1, reverse.events.size)
        assertEquals(1, reverse.blocked)
        assertEquals(0, reverse.uncertain)
        assertEquals(120.0, reverse.events.single().distance, .1)
    }
    @Test fun directionalConditionalAccessWithUnknownOrientationRemainsUncertain() {
        val barrier = gate(80.0, tags = mapOf("foot" to "yes", "foot:forward:conditional" to "no @ (Mo-Fr)"))
        for (reverse in listOf(false, true)) {
            val report = RouteObstacles.analyze(route, ObstacleData(listOf(barrier)), reverse = reverse)
            assertEquals(1, report.events.size)
            assertEquals(0, report.blocked)
            assertEquals(1, report.uncertain)
        }
    }
    @Test fun conflictingParentAccessProducesAWarningInsteadOfLosingRestrictions() {
        val opening = gate(80.0, tags = mapOf("barrier" to "entrance"))
        val before = OsmRoad(listOf(p(0.0), p(80.0)), listOf(7, 1),
            mapOf("highway" to "path", "foot" to "yes"))
        val after = OsmRoad(listOf(p(80.0), p(200.0)), listOf(1, 9),
            mapOf("highway" to "path", "foot" to "no"))
        for (roads in listOf(listOf(before, after), listOf(after, before))) {
            val report = RouteObstacles.analyze(route, ObstacleData(listOf(opening), roads))
            assertEquals(1, report.events.size)
            assertEquals(0, report.blocked)
            assertEquals(1, report.uncertain)
        }
    }
}
