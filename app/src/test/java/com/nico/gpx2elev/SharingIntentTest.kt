package com.nico.gpx2elev

import android.content.ClipData
import android.content.ClipDescription
import android.content.Intent
import android.net.Uri
import android.os.Looper
import androidx.lifecycle.ViewModelProvider
import com.nico.gpx2elev.core.*
import com.nico.gpx2elev.data.*
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.io.File

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class SharingIntentTest {
    private fun receive(clipOnly: Boolean) {
        val app = RuntimeEnvironment.getApplication()
        assertEquals("com.nico.gpx2elev", app.packageName)
        val bytes = "<gpx><rte><rtept lat='45' lon='5'><ele>500</ele></rtept><rtept lat='45' lon='5.001'><ele>510</ele></rtept></rte></gpx>".toByteArray()
        val prepared = bytes.inputStream().use { ElevationMath.prepare(GpxParser.parse(it)) }
        val distances = prepared.segments.single().distance
        val values = distances.map { 500 + 10 * it / distances.last() }.toDoubleArray()
        ElevationRepository(File(app.filesDir, "elevation/profiles"), object : ModelReader {
            override fun read(source: ElevationSource, points: List<GeoPoint>, progress: (Progress) -> Unit) = values
        }).obtain(prepared.points, true) {}
        val uri = Uri.parse("content://gestionnaire.example/partage.gpx")
        Shadows.shadowOf(app.contentResolver).registerInputStreamSupplier(uri) { bytes.inputStream() }
        val send = Intent(Intent.ACTION_SEND).setType("application/gpx+xml").addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        if (clipOnly) send.clipData = ClipData(ClipDescription("parcours", arrayOf("application/gpx+xml")), ClipData.Item(uri))
        else send.putExtra(Intent.EXTRA_STREAM, uri)
        for (type in listOf("application/gpx+xml", "application/gpx", "application/x-gpx+xml", "application/x-gpx", "text/gpx", "text/gpx+xml", "text/plain", "text/xml", "application/octet-stream")) {
            @Suppress("DEPRECATION")
            val targets = app.packageManager.queryIntentActivities(Intent(Intent.ACTION_SEND).setType(type), 0)
            assertTrue("GPX share MIME $type", targets.any {
                it.activityInfo.name == MainActivity::class.java.name && it.activityInfo.packageName == "com.nico.gpx2elev"
            })
        }
        val controller = Robolectric.buildActivity(MainActivity::class.java, if (clipOnly) Intent(Intent.ACTION_MAIN) else send).setup()
        try {
            val activity = controller.get()
            if (clipOnly) controller.newIntent(send)
            val model = ViewModelProvider(activity)[AppViewModel::class.java]
            val deadline = System.nanoTime() + 15_000_000_000L
            while (model.state.value.busy && System.nanoTime() < deadline) {
                Shadows.shadowOf(Looper.getMainLooper()).idle()
                Thread.sleep(10)
            }
            Shadows.shadowOf(Looper.getMainLooper()).idle()
            val state = model.state.value
            assertFalse("Import terminé", state.busy)
            assertNull(state.error)
            assertEquals("partage.gpx", state.result?.name)
            assertEquals(ElevationSource.IGN, state.result?.series?.source)
            assertEquals(10.0, state.result!!.computed.gain.up, 1e-7)
            assertEquals("gpx2elev", activity.getString(R.string.app_name))
        } finally { controller.pause().stop().destroy() }
    }

    @Test fun opensSharedGpxFromContentUri() { receive(false) }
    @Test fun receivesGpxFromClipDataWhileAlreadyOpen() { receive(true) }
}
