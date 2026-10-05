package com.nico.gpxdenivele

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.net.Uri
import android.os.Looper
import androidx.activity.compose.setContent
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import com.nico.gpxdenivele.core.*
import com.nico.gpxdenivele.data.*
import com.nico.gpxdenivele.ui.GpxScreen
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], qualifiers = "w411dp-h891dp-mdpi")
@LooperMode(LooperMode.Mode.PAUSED)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class AndroidUiTest {
    @get:Rule val rule = createAndroidComposeRule<MainActivity>()

    @Before fun useFrenchForExistingScreens() {
        rule.runOnUiThread { I18n.select("fr") }
    }

    @Test fun languageToggleUpdatesWelcomeAndPersistsChoice() {
        rule.onNodeWithText("EN").performClick()
        rule.onNodeWithText("Import a GPX track").assertIsDisplayed()
        rule.onNodeWithText("Your route's elevation gain").assertIsDisplayed()
        screenshot("welcome_EN")
        assertEquals("en", rule.activity.getSharedPreferences("language", 0).getString("choice", null))
        rule.runOnUiThread { I18n.initialize(rule.activity) }
        assertEquals("en", I18n.language)
        assertEquals("Invalid coordinates at point 42.", I18n.text("Coordonnées invalides au point 42."))
        rule.onNodeWithText("FR").performClick()
        rule.onNodeWithText("Importer une trace GPX").assertIsDisplayed()
        assertEquals("fr", rule.activity.getSharedPreferences("language", 0).getString("choice", null))
    }

    private fun reference(): Pair<PreparedTrack, DoubleArray> {
        assumeTrue("Banc d'essai personnel local", javaClass.getResource("/reference.gpx") != null && javaClass.getResource("/reference.csv") != null)
        val track = javaClass.getResourceAsStream("/reference.gpx")!!.use { GpxParser.parse(it) }
        val prepared = ElevationMath.prepare(track)
        val values = javaClass.getResourceAsStream("/reference.csv")!!.bufferedReader().use { it.readLines() }.drop(1)
            .map { it.split(',')[3].toDouble() }.toDoubleArray()
        return prepared to values
    }
    private fun screenshot(name: String) {
        val file = File(System.getProperty("gpxdenivele.qa"), "$name.png")
        file.parentFile!!.mkdirs()
        rule.waitForIdle()
        lateinit var bitmap: Bitmap
        rule.runOnUiThread {
            val root = rule.activity.window.decorView
            bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888)
            root.draw(Canvas(bitmap))
        }
        assertTrue(bitmap.width > 300 && bitmap.height > 300)
        file.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
    }

    @Test fun welcomeAndRealImportWithCachedIgn() {
        rule.onNodeWithText("Importer une trace GPX").assertIsDisplayed()
        screenshot("accueil")
        val (prepared, values) = reference()
        val base = File(rule.activity.filesDir, "elevation")
        val repository = ElevationRepository(File(base, "profiles"), object : ModelReader {
            override fun read(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit) = values
        })
        repository.obtain(prepared.points, true) {}
        assertTrue(repository.obtain(prepared.points, false) {}.fromCache)
        val imported = File(rule.activity.cacheDir, "2026-10-04_10-30.gpx")
        imported.writeBytes(javaClass.getResourceAsStream("/reference.gpx")!!.use { it.readBytes() })
        rule.onNodeWithText("Importer une trace GPX").performClick()
        val request = Shadows.shadowOf(rule.activity).nextStartedActivityForResult
        assertEquals(Intent.ACTION_OPEN_DOCUMENT, request.intent.action)
        rule.runOnUiThread {
            Shadows.shadowOf(rule.activity).receiveResult(request.intent, Activity.RESULT_OK, Intent().setData(Uri.fromFile(imported)))
        }
        rule.waitUntil(15000) {
            Shadows.shadowOf(Looper.getMainLooper()).idle()
            rule.onAllNodesWithText("735").fetchSemanticsNodes().isNotEmpty()
        }
        rule.onNodeWithText("IGN LiDAR HD").assertIsDisplayed()
        screenshot("resultat_IGN")
        rule.onNodeWithText("Comparer avec les altitudes du GPX").performScrollTo().performClick()
        rule.onNodeWithText("Somme brute des variations").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Exporter le résultat en CSV").performScrollTo().performClick()
        val export = Shadows.shadowOf(rule.activity).nextStartedActivityForResult
        assertEquals(Intent.ACTION_CREATE_DOCUMENT, export.intent.action)
        val csv = File(rule.activity.cacheDir, "resultat.csv")
        rule.runOnUiThread {
            Shadows.shadowOf(rule.activity).receiveResult(export.intent, Activity.RESULT_OK, Intent().setData(Uri.fromFile(csv)))
        }
        rule.waitUntil(10000) {
            Shadows.shadowOf(Looper.getMainLooper()).idle()
            csv.exists() && csv.readText().contains("735.128566")
        }
        assertTrue(csv.readText().contains("3380.710000"))
    }

    private fun showResult() {
        val (prepared, values) = reference()
        val result = Result("2026-10-04_10-30.gpx", prepared, ElevationMath.compute(prepared, values),
            ElevationSeries(ElevationSource.IGN, values, true, emptyList()), 0L)
        rule.runOnUiThread {
            rule.activity.setContent { GpxScreen(AppState(result = result), {}, {}, {}, {}, {}) }
        }
        rule.onNodeWithText("735").assertIsDisplayed()
    }

    @Test @Config(qualifiers = "w411dp-h891dp-night-mdpi") fun resultInDarkMode() {
        showResult(); screenshot("resultat_nuit")
    }

    @Test fun resultInEnglishKeepsGainAndFormatsDistance() {
        showResult()
        rule.onNodeWithText("EN").performClick()
        rule.onNodeWithText("ELEVATION GAIN").assertIsDisplayed()
        rule.onNodeWithText("735").assertIsDisplayed()
        rule.onAllNodesWithText("22.33 km")[0].assertIsDisplayed()
        screenshot("result_EN")
        rule.onNodeWithText("Compare with GPX elevations").performScrollTo().performClick()
        rule.onNodeWithText("Raw sum of elevation changes").performScrollTo().assertIsDisplayed()
        screenshot("comparison_EN")
        rule.onNodeWithText("FR").performClick()
        rule.onNodeWithText("Somme brute des variations").assertIsDisplayed()
    }

    @Test @Config(qualifiers = "w891dp-h411dp-land-mdpi") fun resultInLandscape() {
        showResult(); screenshot("resultat_paysage")
    }

    @Test fun androidDecodesTerrariumWebpWithoutChangingRgbSamples() {
        val bytes = javaClass.getResourceAsStream("/mapterhorn.webp")!!.use { it.readBytes() }
        val tile = PublicModels.decodeWebp(bytes)
        assertEquals(512, tile.size)
        val rows = javaClass.getResourceAsStream("/mapterhorn_pixels.csv")!!.bufferedReader().use { it.readLines() }.drop(1)
        for (row in rows) {
            val values = row.split(',').map { it.toInt() }
            val pixel = tile.pixels[values[1] * tile.size + values[0]]
            assertEquals(values[2], (pixel ushr 16) and 255)
            assertEquals(values[3], (pixel ushr 8) and 255)
            assertEquals(values[4], pixel and 255)
        }
    }

}
