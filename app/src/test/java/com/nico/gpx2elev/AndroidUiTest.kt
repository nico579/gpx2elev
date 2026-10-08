package com.nico.gpx2elev

import android.app.Activity
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.Canvas
import android.net.Uri
import android.os.Looper
import androidx.activity.compose.setContent
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import com.nico.gpx2elev.core.*
import com.nico.gpx2elev.data.*
import com.nico.gpx2elev.ui.GpxScreen
import com.nico.gpx2elev.update.*
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

    @Test fun tappingChartShowsRecordedTimeAndBothAltitudesAndKeepsSelectionInFullscreen() {
        val start = java.time.Instant.parse("2026-10-08T10:00:00Z")
        val prepared = ElevationMath.prepare(Track(listOf(listOf(
            TrackPoint(GeoPoint(45.0, 5.0), 20.0, start),
            TrackPoint(GeoPoint(45.0, 5.0005), 600.0, start.plusSeconds(300)),
            TrackPoint(GeoPoint(45.0, 5.001), 50.0, start.plusSeconds(600)),
        ))))
        val values = DoubleArray(prepared.sampleCount) { 100.0 }
        val result = Result("heures.gpx", prepared, ElevationMath.compute(prepared, values),
            ElevationSeries(ElevationSource.IGN, values, true, emptyList()), 0L)
        val description = "Profils d'altitude : terrain lissé et mesures GPX, distance en kilomètres et altitude en mètres"
        rule.runOnUiThread { rule.activity.setContent { GpxScreen(AppState(result = result), {}, {}, {}, {}, {}) } }
        rule.onNodeWithContentDescription(description).performScrollTo().performTouchInput { click(center) }
        rule.onNodeWithText("Terrain lissé : 100,0 m").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Mesure GPX : 600,0 m").assertIsDisplayed()
        val selected = rule.onNodeWithContentDescription(description).fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.StateDescription]
        assertTrue(selected.contains("Heure locale : "))
        assertTrue(selected.contains(com.nico.gpx2elev.ui.profileTimeLabel(start.plusSeconds(300), seconds = true, date = true)))
        screenshot("profil_curseur_heures")
        rule.onNodeWithText("Plein écran").performScrollTo().performClick()
        rule.onNodeWithText("Mesure GPX : 600,0 m").assertIsDisplayed()
        rule.onNodeWithContentDescription("Zoom avant").performClick()
        assertEquals(selected, rule.onNodeWithContentDescription(description).fetchSemanticsNode().config[androidx.compose.ui.semantics.SemanticsProperties.StateDescription])
        rule.runOnUiThread { I18n.select("en") }
        rule.onNodeWithText("GPX measurement: 600.0 m").assertIsDisplayed()
        rule.onNodeWithText("Exit full screen").performClick()
        rule.onNodeWithText("GPX measurement: 600.0 m").performScrollTo().assertIsDisplayed()
        assertEquals(0.0, result.computed.gain.up, 1e-9)
    }

    private fun chartResult(cacheWarning: String? = null): Result {
        val prepared = ElevationMath.prepare(Track(listOf(listOf(
            TrackPoint(GeoPoint(45.0, 5.0), 20.0), TrackPoint(GeoPoint(45.0, 5.001), 600.0),
        ))))
        val values = DoubleArray(prepared.sampleCount) { 100.0 }
        return Result("graphique.gpx", prepared, ElevationMath.compute(prepared, values),
            ElevationSeries(ElevationSource.IGN, values, false, emptyList(), cacheWarning), 0L)
    }

    private fun updateRelease() = UpdateRelease("0.4.0", "v0.4.0", "gpx2elev-0.4.0.apk",
        "https://github.com/nico579/gpx2elev/releases/download/v0.4.0/gpx2elev-0.4.0.apk", 1048576, "a".repeat(64), "")

    @Test fun updateMenuShowsVersionDownloadProgressAndAndroidPermissionInBothLanguages() {
        var updates by mutableStateOf(UpdateState(currentVersion = "0.3.3"))
        var actions = 0
        rule.runOnUiThread {
            rule.activity.setContent {
                GpxScreen(AppState(), {}, {}, {}, {}, {}, updateState = updates,
                    onUpdates = { updates = updates.copy(open = true, phase = UpdatePhase.AVAILABLE, release = updateRelease()) },
                    onUpdateAction = { actions++; updates = updates.copy(phase = UpdatePhase.DOWNLOADING, total = 100, completed = 35) },
                    onUpdateClose = { updates = updates.copy(open = false) })
            }
        }
        rule.onNodeWithContentDescription("Menu").performClick()
        rule.onNodeWithText("Mises à jour").performClick()
        rule.onNodeWithText("Version installée : 0.3.3").assertIsDisplayed()
        rule.onNodeWithText("Version 0.4.0 disponible · 1,0 Mio").assertIsDisplayed()
        rule.onNodeWithText("Télécharger et installer").performClick()
        assertEquals(1, actions)
        rule.onNodeWithText("35 %").assertIsDisplayed()
        rule.onNodeWithText("Télécharger et installer").assertDoesNotExist()
        rule.runOnUiThread { updates = updates.copy(phase = UpdatePhase.PERMISSION); I18n.select("en") }
        rule.onNodeWithText("Allow installation").assertIsDisplayed()
        rule.onNodeWithText("Installed version: 0.3.3").assertIsDisplayed()
        screenshot("updates_EN")
        rule.onNodeWithText("Close").performClick()
        rule.onNodeWithText("Import a GPX track").assertIsDisplayed()
    }

    @Test fun installationWaitsForCalculationAndNetworkErrorOffersRetry() {
        var appState by mutableStateOf(AppState(busy = true))
        var updates by mutableStateOf(UpdateState(open = true, currentVersion = "0.3.3", phase = UpdatePhase.AVAILABLE, release = updateRelease()))
        var actions = 0
        rule.runOnUiThread {
            rule.activity.setContent { GpxScreen(appState, {}, {}, {}, {}, {}, updateState = updates, onUpdateAction = { actions++ }) }
        }
        rule.onNodeWithText("Télécharger et installer").assertIsNotEnabled()
        rule.onNodeWithText("Attendez la fin du calcul avant d'installer la mise à jour.").assertIsDisplayed()
        rule.runOnUiThread {
            appState = AppState()
            updates = updates.copy(phase = UpdatePhase.ERROR, error = "Impossible de télécharger la mise à jour. Vérifiez Internet, l'espace libre et réessayez.")
        }
        rule.onNodeWithText("Réessayer").assertIsEnabled().performClick()
        assertEquals(1, actions)
        screenshot("updates_erreur_FR")
    }

    @Test fun cancellingUpdateReturnsToTheSameGpxResult() {
        var updates by mutableStateOf(UpdateState(open = true, currentVersion = "0.3.3", phase = UpdatePhase.DOWNLOADING, total = 100, completed = 40))
        var cancelled = 0
        val result = chartResult()
        rule.runOnUiThread {
            rule.activity.setContent { GpxScreen(AppState(result = result), {}, {}, {}, {}, {}, updateState = updates,
                onUpdateClose = { cancelled++; updates = updates.copy(open = false) }) }
        }
        rule.onNodeWithText("40 %").assertIsDisplayed()
        rule.onNodeWithText("Annuler").performClick()
        assertEquals(1, cancelled)
        rule.onNodeWithText("graphique.gpx").assertIsDisplayed()
        rule.onNodeWithText("Plein écran").performScrollTo().assertIsDisplayed()
    }

    @Test fun fullscreenChartGrowsAndPreservesZoomWhenReturningAndChangingLanguage() {
        val description = "Profils d'altitude : terrain lissé et mesures GPX, distance en kilomètres et altitude en mètres"
        val result = chartResult()
        rule.runOnUiThread { rule.activity.setContent { GpxScreen(AppState(result = result), {}, {}, {}, {}, {}) } }
        val normal = rule.onNodeWithContentDescription(description).performScrollTo().fetchSemanticsNode().boundsInRoot
        rule.onNodeWithContentDescription("Zoom avant").performClick()
        val initialRange = rule.onAllNodes(hasText("Altitude visible :", substring = true)).fetchSemanticsNodes().single().config[androidx.compose.ui.semantics.SemanticsProperties.Text].first().text
        rule.onNodeWithText("Plein écran").performScrollTo().performClick()
        rule.onNodeWithText("Quitter le plein écran").assertIsDisplayed()
        rule.onNodeWithText("Mesures GPX").assertIsDisplayed()
        val full = rule.onNodeWithContentDescription(description).fetchSemanticsNode().boundsInRoot
        assertTrue(full.height > normal.height)
        rule.onNodeWithText(initialRange).assertIsDisplayed()
        rule.onNodeWithContentDescription("Zoom avant").performClick()
        val zoomed = rule.onAllNodes(hasText("Altitude visible :", substring = true)).fetchSemanticsNodes().single().config[androidx.compose.ui.semantics.SemanticsProperties.Text].first().text
        assertNotEquals(initialRange, zoomed)
        rule.onNodeWithText("Quitter le plein écran").performClick()
        rule.onNodeWithText(zoomed).performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Plein écran").performScrollTo().performClick()
        rule.runOnUiThread { I18n.select("en") }
        rule.onNodeWithText("Exit full screen").assertIsDisplayed().performClick()
        rule.onNodeWithText("Full screen").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Full view").assertIsEnabled()
    }

    @Test fun successfulResultExplainsThatFailedCacheDoesNotGuaranteeOfflineUse() {
        val result = chartResult("disk full")
        rule.runOnUiThread { rule.activity.setContent { GpxScreen(AppState(result = result), {}, {}, {}, {}, {}) } }
        rule.onNodeWithText("Le profil n'a pas pu être enregistré dans le cache. Le résultat reste disponible, mais son utilisation hors connexion n'est pas assurée.")
            .performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("EN").performClick()
        rule.onNodeWithText("The profile could not be saved to the cache. The result is available, but offline use cannot be guaranteed.")
            .performScrollTo().assertIsDisplayed()
    }

    @Test @Config(qualifiers = "w891dp-h411dp-land-mdpi") fun fullscreenLandscapeLeavesMoreSpaceForTheCurve() {
        val description = "Profils d'altitude : terrain lissé et mesures GPX, distance en kilomètres et altitude en mètres"
        val result = chartResult()
        rule.runOnUiThread { rule.activity.setContent { GpxScreen(AppState(result = result), {}, {}, {}, {}, {}) } }
        val normal = rule.onNodeWithContentDescription(description).performScrollTo().fetchSemanticsNode().boundsInRoot
        rule.onNodeWithText("Plein écran").performScrollTo().performClick()
        rule.onNodeWithText("Quitter le plein écran").assertIsDisplayed()
        rule.onNodeWithContentDescription("Zoom avant").assertIsDisplayed()
        val full = rule.onNodeWithContentDescription(description).fetchSemanticsNode().boundsInRoot
        assertTrue("Landscape curve gains vertical space", full.height > normal.height)
        rule.onNodeWithText("Quitter le plein écran").performClick()
        rule.onNodeWithText("Plein écran").performScrollTo().assertIsDisplayed()
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

    @Test fun cacheSizeConfirmationAndBusyGuard() {
        var cleared = 0
        rule.runOnUiThread {
            rule.activity.setContent {
                GpxScreen(AppState(), {}, {}, {}, {}, {}, CacheSize(1048576, 2097152), { cleared++ })
            }
        }
        rule.onNodeWithText("Cache des altitudes · 3,0 Mio").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Vider le cache").performScrollTo().performClick()
        rule.onNodeWithText("Annuler").performClick()
        assertEquals(0, cleared)
        rule.onNodeWithText("Vider le cache").performClick()
        rule.onNode(hasText("Vider le cache") and hasAnyAncestor(isDialog())).performClick()
        assertEquals(1, cleared)
        rule.runOnUiThread {
            rule.activity.setContent {
                GpxScreen(AppState(busy = true), {}, {}, {}, {}, {}, CacheSize(1048576, 0), { cleared++ })
            }
        }
        rule.onNodeWithText("Vider le cache").performScrollTo().assertIsNotEnabled()
    }

    @Test fun chartShowsNativeGpxLegendAndSharedBounds() {
        val prepared = ElevationMath.prepare(Track(listOf(listOf(
            TrackPoint(GeoPoint(45.0, 5.0), 20.0),
            TrackPoint(GeoPoint(45.0, 5.0005), null),
            TrackPoint(GeoPoint(45.0, 5.001), 600.0),
        ))))
        val values = DoubleArray(prepared.sampleCount) { 100.0 }
        val result = Result("comparaison.gpx", prepared, ElevationMath.compute(prepared, values),
            ElevationSeries(ElevationSource.IGN, values, true, emptyList()), 0L)
        rule.runOnUiThread {
            rule.activity.setContent { GpxScreen(AppState(result = result), {}, {}, {}, {}, {}) }
        }
        rule.onNodeWithText("Profil lissé (terrain)").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Mesures GPX").assertIsDisplayed()
        rule.onNodeWithText("Min. 20 m").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("Max. 600 m").assertIsDisplayed()
        rule.onNodeWithContentDescription("Profils d'altitude : terrain lissé et mesures GPX, distance en kilomètres et altitude en mètres")
            .performScrollTo().assertIsDisplayed()
        screenshot("profils_GPX_partiels")
        rule.onNodeWithContentDescription("Zoom avant").performScrollTo().performClick()
        rule.onNodeWithText("Altitude visible : 165 à 455 m").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("EN").performClick()
        rule.onNodeWithText("Visible elevation: 165 to 455 m").performScrollTo().assertIsDisplayed()
        rule.onNodeWithText("FR").performClick()
        rule.onNodeWithText("Vue complète").performScrollTo().performClick()
        rule.onNodeWithText("Altitude visible : 20 à 600 m").performScrollTo().assertIsDisplayed()
    }

    @Test fun chartReportsMissingGpxObservations() {
        val prepared = ElevationMath.prepare(Track(listOf(listOf(
            TrackPoint(GeoPoint(45.0, 5.0), null), TrackPoint(GeoPoint(45.0, 5.001), null),
        ))))
        val values = DoubleArray(prepared.sampleCount) { 100.0 }
        val result = Result("sans-altitudes.gpx", prepared, ElevationMath.compute(prepared, values),
            ElevationSeries(ElevationSource.IGN, values, true, emptyList()), 0L)
        rule.runOnUiThread {
            rule.activity.setContent { GpxScreen(AppState(result = result), {}, {}, {}, {}, {}) }
        }
        rule.onNodeWithText("Altitudes GPX manquantes.").performScrollTo().assertIsDisplayed()
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
        val file = File(System.getProperty("gpx2elev.qa"), "$name.png")
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
        rule.onNodeWithText("Somme brute des variations").performScrollTo().assertIsDisplayed()
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
