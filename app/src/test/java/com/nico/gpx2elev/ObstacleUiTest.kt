package com.nico.gpx2elev

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.activity.compose.setContent
import androidx.compose.runtime.*
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import com.nico.gpx2elev.core.*
import com.nico.gpx2elev.data.*
import com.nico.gpx2elev.ui.GpxScreen
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-mdpi")
@LooperMode(LooperMode.Mode.PAUSED)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ObstacleUiTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()
    private fun result(): Result {
        val points = listOf(GeoPoint(45.0, 5.0), GeoPoint(45.001, 5.001), GeoPoint(45.001, 5.003), GeoPoint(45.002, 5.002))
        val prepared = ElevationMath.prepare(Track(listOf(points.map { TrackPoint(it, null) })))
        val values = DoubleArray(prepared.sampleCount) { 100.0 }
        return Result("obstacles.gpx", prepared, ElevationMath.compute(prepared, values), ElevationSeries(ElevationSource.IGN, values, true, emptyList()), 0)
    }
    @Test fun controlsRecomputeDirectionAndModesAndErrorsKeepTheElevationResult() {
        val result = result()
        val data = ObstacleData(listOf(OsmBarrier("node/1", listOf(GeoPoint(45.001, 5.002)), mapOf("barrier" to "gate", "foot" to "no"))))
        var state by mutableStateOf(AppState(result = result, obstacles = ObstacleState(report = RouteObstacles.analyze(result.prepared, data))))
        rule.runOnUiThread {
            I18n.select("fr")
            rule.activity.setContent { GpxScreen(state, {}, {}, {}, {}, {},
                onObstacleReverse = {
                    val reverse = !state.obstacles.reverse
                    state = state.copy(obstacles = state.obstacles.copy(reverse = reverse, report = RouteObstacles.analyze(result.prepared, data, state.obstacles.mode, reverse)))
                }, onObstacleMode = { mode -> state = state.copy(obstacles = state.obstacles.copy(mode = mode,
                    report = RouteObstacles.analyze(result.prepared, data, mode, state.obstacles.reverse))) },
                onObstacleRefresh = { state = state.copy(obstacles = state.obstacles.copy(error = "Vérification des obstacles indisponible : erreur réseau.")) }) }
        }
        rule.onNodeWithText("1 blocage(s) probable(s) · 0 passage(s) à vérifier").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Sens du GPX").performScrollTo().performClick()
        assertTrue(state.obstacles.reverse)
        rule.onNodeWithText("Sens inversé").assertIsDisplayed()
        rule.onNodeWithText("Vélo").performScrollTo().performClick()
        assertEquals(TravelMode.BICYCLE, state.obstacles.mode)
        rule.onNodeWithText("0 blocage(s) probable(s) · 1 passage(s) à vérifier").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Vérifier les obstacles").performScrollTo().performClick()
        rule.onNodeWithText("Vérification des obstacles indisponible : erreur réseau.").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("obstacles.gpx").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("EN").performClick()
        rule.onNodeWithText("Access and obstacles").performScrollTo().assertIsDisplayed()
    }
    @Test fun mapShowsRedAndOrangeCrossingsWithAccessibleDescription() {
        val result = result()
        val data = ObstacleData(listOf(
            OsmBarrier("node/1", listOf(GeoPoint(45.001, 5.002)), mapOf("barrier" to "gate", "foot" to "no")),
            OsmBarrier("node/2", listOf(GeoPoint(45.0015, 5.0025)), mapOf("barrier" to "gate"))))
        val report = RouteObstacles.analyze(result.prepared, data)
        assertEquals(1, report.blocked); assertEquals(1, report.uncertain)
        rule.runOnUiThread {
            I18n.select("fr")
            rule.activity.setContent { GpxScreen(AppState(result = result, obstacles = ObstacleState(report = report)), {}, {}, {}, {}, {}) }
        }
        rule.onNodeWithContentDescription("Vue du parcours : départ D, arrivée A, flèches du sens et portions bloquées en rouge").performScrollTo().assertIsDisplayed()
        rule.waitForIdle()
        val file = File(System.getProperty("gpx2elev.qa"), "obstacles_parcours.png").apply { parentFile!!.mkdirs() }
        rule.runOnUiThread {
            val view = rule.activity.window.decorView
            val bitmap = Bitmap.createBitmap(view.width, view.height, Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap))
            file.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
        }
    }
}
