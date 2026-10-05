package com.nico.gpxdenivele

import com.nico.gpxdenivele.core.GeoPoint
import com.nico.gpxdenivele.core.GpxParser
import com.nico.gpxdenivele.core.ElevationMath
import com.nico.gpxdenivele.data.*
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import java.io.File

/** Optional network integration: public bytes -> native Android decode -> audited altitude. */
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class LiveModelsTest {
    @Test fun allPublicSourcesAgreeWithAuditedLocalData() {
        assumeTrue(System.getProperty("gpxdenivele.live") == "true")
        assumeTrue("Banc d'essai personnel local", javaClass.getResource("/live_expected.csv") != null && javaClass.getResource("/reference.gpx") != null)
        val qa = File(checkNotNull(System.getProperty("gpxdenivele.qa")))
        val rows = javaClass.getResourceAsStream("/live_expected.csv")!!.bufferedReader().use { it.readLines() }
            .drop(1).map { it.split(',') }.groupBy { ElevationSource.valueOf(it[0]) }
        val models = PublicModels(File(qa.parentFile, "live-cache"), HttpTransport())
        val report = StringBuilder("source;latitude;longitude;reference_m;android_m;ecart_m\n")
        val failures = mutableListOf<String>()
        for (source in ElevationSource.entries) {
            val group = rows.getValue(source)
            println("Validation en ligne : ${source.label}")
            try {
                val actual = models.read(source, group.map { GeoPoint(it[1].toDouble(), it[2].toDouble()) }) { println(it.message) }
                for (i in actual.indices) {
                    val expected = group[i][3].toDouble()
                    report.append("${source.name};${group[i][1]};${group[i][2]};$expected;${actual[i]};${actual[i]-expected}\n")
                    // The live IGN service currently differs from its archived response by up to
                    // 0.17 m at these positions (also confirmed by an independent HTTPS request).
                    assertEquals(source.label, expected, actual[i], if (source == ElevationSource.IGN) .5 else 1e-5)
                }
            } catch (exception: Exception) {
                failures += "${source.label}: ${exception.message}"
                println(failures.last())
            }
        }
        qa.mkdirs()
        File(qa, "modeles_en_ligne.csv").writeText(report.toString())
        assertEquals("Les cinq sources doivent être vérifiées : ${failures.joinToString()}", emptyList<String>(), failures)
        val track = javaClass.getResourceAsStream("/reference.gpx")!!.use { GpxParser.parse(it) }
        val prepared = ElevationMath.prepare(track)
        val liveIgn = models.read(ElevationSource.IGN, prepared.points) { println(it.message) }
        val computed = ElevationMath.compute(prepared, liveIgn)
        File(qa, "profil_IGN_actuel.csv").bufferedWriter().use { writer ->
            writer.write("distance_m;altitude_IGN_m\n")
            prepared.segments.single().distance.indices.forEach { i -> writer.write("${prepared.segments.single().distance[i]};${liveIgn[i]}\n") }
        }
        File(qa, "verification_IGN_actuelle.json").writeText(org.json.JSONObject()
            .put("date_UTC", java.time.Instant.now().toString()).put("positions", liveIgn.size)
            .put("Dplus_m", computed.gain.up).put("Dmoins_m", computed.gain.down)
            .put("pas_m", 5).put("sigma_m", 20).put("hysteresis_m", 2).toString(2))
        println("Trace complète IGN actuelle : D+ ${computed.gain.up} m / D- ${computed.gain.down} m")
    }
}
