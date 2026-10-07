package com.nico.gpx2elev

import android.content.Context
import android.net.Uri
import android.os.Looper
import com.nico.gpx2elev.core.*
import com.nico.gpx2elev.data.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
@LooperMode(LooperMode.Mode.PAUSED)
class ImportValidationTest {
    private val saved = "<gpx><rte><rtept lat='45' lon='5'><ele>100</ele></rtept>" +
        "<rtept lat='45.001' lon='5'><ele>110</ele></rtept></rte></gpx>"

    private fun awaitFinished(model: AppViewModel) {
        val deadline = System.nanoTime() + 15_000_000_000L
        while (model.state.value.busy && System.nanoTime() < deadline) {
            Shadows.shadowOf(Looper.getMainLooper()).idle()
            Thread.sleep(10)
        }
        Shadows.shadowOf(Looper.getMainLooper()).idle()
        assertFalse("Import or restoration completes", model.state.value.busy)
    }

    private fun failedImportKeepsSavedTrack(xml: String, expectedError: String) {
        val app = RuntimeEnvironment.getApplication()
        val base = File(app.filesDir, "elevation")
        base.deleteRecursively()
        base.mkdirs()
        val last = File(base, "last.gpx").apply { writeText(saved) }
        val prefs = app.getSharedPreferences("trace", Context.MODE_PRIVATE)
        prefs.edit().clear().putString("name", "saved.gpx").commit()
        val prepared = saved.byteInputStream().use { ElevationMath.prepare(GpxParser.parse(it)) }
        ElevationRepository(File(base, "profiles"), object : ModelReader {
            override fun read(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit) =
                DoubleArray(points.size) { 100.0 }
        }).obtain(prepared.points, true) {}
        val uri = Uri.parse("content://import.example/replacement.gpx")
        Shadows.shadowOf(app.contentResolver).registerInputStreamSupplier(uri) { xml.byteInputStream() }
        val model = AppViewModel(app)
        try {
            model.import(uri)
            awaitFinished(model)
            assertNotNull(model.state.value.error)
            assertTrue(model.state.value.error.orEmpty(), model.state.value.error.orEmpty().contains(expectedError))
            assertEquals(saved, last.readText())
            assertEquals("saved.gpx", prefs.getString("name", null))
            assertFalse(base.listFiles().orEmpty().any { it.name.startsWith("import-") })

            model.restore()
            awaitFinished(model)
            assertNull(model.state.value.error)
            assertEquals("saved.gpx", model.state.value.result?.name)
            assertEquals(2, model.state.value.result?.prepared?.track?.pointCount)
        } finally { model.cancel() }
    }

    @Test fun stationaryTraceCannotReplaceTheLastUsableGpx() {
        failedImportKeepsSavedTrack("<gpx><rte><rtept lat='45' lon='5'/><rtept lat='45' lon='5'/></rte></gpx>",
            "deux positions distinctes")
    }

    @Test fun overlongTraceCannotReplaceTheLastUsableGpx() {
        failedImportKeepsSavedTrack("<gpx><rte><rtept lat='0' lon='0'/><rtept lat='0' lon='20'/></rte></gpx>",
            "Trace trop longue")
    }

    @Test fun invalidXmlCannotReplaceTheLastUsableGpx() {
        failedImportKeepsSavedTrack("<gpx><rte>", "")
    }

    @Test fun validRouteReplacesTheSavedGpxAndUsesItsPreparedTrack() {
        val app = RuntimeEnvironment.getApplication()
        val base = File(app.filesDir, "elevation")
        base.deleteRecursively()
        base.mkdirs()
        val last = File(base, "last.gpx").apply { writeText(saved) }
        val prefs = app.getSharedPreferences("trace", Context.MODE_PRIVATE)
        prefs.edit().clear().putString("name", "saved.gpx").commit()
        val replacement = "<gpx><rte><rtept lat='45' lon='5'><ele>120</ele></rtept>" +
            "<rtept lat='45.001' lon='5'><ele>140</ele></rtept>" +
            "<rtept lat='45.002' lon='5'><ele>150</ele></rtept></rte></gpx>"
        val prepared = replacement.byteInputStream().use { ElevationMath.prepare(GpxParser.parse(it)) }
        ElevationRepository(File(base, "profiles"), object : ModelReader {
            override fun read(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit) =
                DoubleArray(points.size) { 130.0 }
        }).obtain(prepared.points, true) {}
        val uri = Uri.parse("content://import.example/replacement.gpx")
        Shadows.shadowOf(app.contentResolver).registerInputStreamSupplier(uri) { replacement.byteInputStream() }
        val model = AppViewModel(app)
        try {
            model.import(uri)
            awaitFinished(model)
            assertNull(model.state.value.error)
            assertEquals(replacement, last.readText())
            assertEquals("replacement.gpx", prefs.getString("name", null))
            assertEquals("replacement.gpx", model.state.value.result?.name)
            assertEquals(3, model.state.value.result?.prepared?.track?.pointCount)
            assertEquals(prepared.sampleCount, model.state.value.result?.prepared?.sampleCount)
            assertFalse(base.listFiles().orEmpty().any { it.name.startsWith("import-") })
        } finally { model.cancel() }
    }
}
