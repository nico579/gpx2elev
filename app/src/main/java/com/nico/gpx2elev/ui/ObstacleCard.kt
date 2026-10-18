package com.nico.gpx2elev.ui

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.nico.gpx2elev.I18n
import com.nico.gpx2elev.I18n.text as t
import com.nico.gpx2elev.ObstacleState
import com.nico.gpx2elev.core.*
import java.text.DateFormat
import java.util.Date
import kotlin.math.*

private val BlockedColor = Color(0xFFD52E39)
private val UncertainColor = Color(0xFFD78113)
private val RouteColor = Color(0xFF377BB5)

@Composable
fun ObstacleCard(prepared: PreparedTrack, state: ObstacleState, onRefresh: () -> Unit,
    onMode: (TravelMode) -> Unit, onReverse: () -> Unit) {
    val uriHandler = LocalUriHandler.current
    Card(shape = RoundedCornerShape(20.dp)) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(t("Passage et obstacles"), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.SemiBold)
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                for (mode in TravelMode.entries) FilterChip(selected = state.mode == mode, onClick = { onMode(mode) },
                    label = { Text(t(mode.label)) })
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(onClick = onReverse) { Text(t(if (state.reverse) "Sens inversé" else "Sens du GPX")) }
                TextButton(onClick = onRefresh, enabled = !state.checking) { Text(t("Vérifier les obstacles")) }
            }
            if (state.checking) { LinearProgressIndicator(Modifier.fillMaxWidth()); Text(t("Recherche des obstacles OSM…")) }
            state.error?.let { Text(t(it), color = MaterialTheme.colorScheme.error) }
            val report = state.report
            if (report != null) {
                Text(t("${report.blocked} blocage(s) probable(s) · ${report.uncertain} passage(s) à vérifier"),
                    color = if (report.blocked > 0) BlockedColor else MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.SemiBold)
                if (report.events.isEmpty()) Text(t("Aucun obstacle signalé dans les données consultées."))
            } else if (!state.checking && state.error == null) Text(t("Lancez la vérification pour consulter les obstacles cartographiés."))
            RouteMap(prepared, report, state.reverse)
            Text(t("Pincez pour zoomer, glissez pour déplacer la vue."), style = MaterialTheme.typography.bodySmall)
            Text(t("Bleu : tracé · Rouge : blocage probable · Orange : passage à vérifier"), style = MaterialTheme.typography.bodySmall)
            Text(t("Les portions colorées couvrent 25 m de chaque côté de l'obstacle. Les flèches indiquent le sens du parcours."), style = MaterialTheme.typography.bodySmall)
            report?.events?.take(100)?.forEachIndexed { index, event ->
                Column(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surface, RoundedCornerShape(10.dp)).padding(10.dp)) {
                    Text("${index + 1}. ${t(event.label)} · " + String.format(I18n.locale, "%.2f km", event.distance / 1000),
                        color = if (event.level == ObstacleLevel.BLOCKED) BlockedColor else UncertainColor, fontWeight = FontWeight.SemiBold)
                    Text(t(event.reason), style = MaterialTheme.typography.bodySmall)
                }
            }
            if ((report?.events?.size ?: 0) > 100) Text(t("Liste limitée aux 100 premiers obstacles ; tous sont représentés sur le parcours."))
            state.notice?.let { Text(t(it), style = MaterialTheme.typography.bodySmall) }
            state.fetchedAt?.let { Text(t("Données consultées le " + DateFormat.getDateTimeInstance(DateFormat.SHORT, DateFormat.SHORT, I18n.locale).format(Date(it))), style = MaterialTheme.typography.bodySmall) }
            Text(t("© contributeurs OpenStreetMap · ODbL. Données non exhaustives : l'absence d'alerte ne garantit pas le passage. Le portail peut être ouvert ou fermé sur place."), style = MaterialTheme.typography.bodySmall)
            TextButton(onClick = { uriHandler.openUri("https://www.openstreetmap.org/copyright") }) { Text("OpenStreetMap · ODbL") }
            Text(t("La vérification en ligne transmet les environs du parcours au service Overpass. Les données sont conservées 7 jours avant actualisation, et restent consultables hors connexion."), style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun RouteMap(prepared: PreparedTrack, report: ObstacleReport?, reverse: Boolean) {
    var zoom by remember(prepared) { mutableFloatStateOf(1f) }
    var pan by remember(prepared) { mutableStateOf(Offset.Zero) }
    val description = t("Vue du parcours : départ D, arrivée A, flèches du sens et portions bloquées en rouge")
    val origin = prepared.segments.first().points.first()
    val longitudeScale = cos(Math.toRadians(origin.lat))
    fun coordinate(point: GeoPoint): Offset {
        val longitudeDelta = ((point.lon - origin.lon + 540.0) % 360.0) - 180.0
        return Offset((longitudeDelta * longitudeScale).toFloat(), -(point.lat - origin.lat).toFloat())
    }
    val all = remember(prepared) { prepared.points.map(::coordinate) }
    val minX = all.minOf { it.x }; val maxX = all.maxOf { it.x }; val minY = all.minOf { it.y }; val maxY = all.maxOf { it.y }
    val segments = remember(prepared) {
        val step = max(1, prepared.sampleCount / 4000)
        prepared.segments.map { segment -> segment.points.filterIndexed { i, _ -> i % step == 0 || i == segment.points.lastIndex }.map(::coordinate) }
    }
    val background = MaterialTheme.colorScheme.surface
    Canvas(Modifier.fillMaxWidth().height(280.dp).background(background, RoundedCornerShape(12.dp))
        .semantics { contentDescription = description }
        .pointerInput(prepared) { detectTransformGestures { _, move, factor, _ -> zoom = (zoom * factor).coerceIn(1f, 20f); pan += move } }) {
        val scale = min((size.width - 50f) / max(maxX - minX, .00001f), (size.height - 50f) / max(maxY - minY, .00001f)) * zoom
        fun screen(point: Offset) = Offset(size.width / 2 + (point.x - (minX + maxX) / 2) * scale,
            size.height / 2 + (point.y - (minY + maxY) / 2) * scale) + pan
        fun line(points: List<Offset>, color: Color, width: Float) {
            val path = Path()
            points.forEachIndexed { i, p -> val xy = screen(p); if (i == 0) path.moveTo(xy.x, xy.y) else path.lineTo(xy.x, xy.y) }
            drawPath(path, color, style = Stroke(width = width, cap = StrokeCap.Round))
        }
        clipRect {
            segments.forEach { line(it, RouteColor, 3.dp.toPx()) }
            for (event in report?.events.orEmpty().sortedBy { if (it.level == ObstacleLevel.BLOCKED) 1 else 0 }) {
                val segment = prepared.segments[event.segment]
                val from = (event.localDistance - RouteObstacles.HIGHLIGHT_METERS).coerceAtLeast(0.0)
                val to = (event.localDistance + RouteObstacles.HIGHLIGHT_METERS).coerceAtMost(segment.distance.last())
                val positions = mutableListOf<Offset>()
                val search = segment.distance.binarySearch(from)
                val first = (if (search >= 0) search - 1 else -search - 2).coerceAtLeast(0)
                for (i in first until segment.points.lastIndex) {
                    val a = segment.distance[i]; val b = segment.distance[i + 1]
                    if (a > to) break
                    if (b < from || a > to || b <= a) continue
                    val p = coordinate(segment.points[i]); val q = coordinate(segment.points[i + 1])
                    positions += p + (q - p) * ((max(a, from) - a) / (b - a)).toFloat()
                    positions += p + (q - p) * ((min(b, to) - a) / (b - a)).toFloat()
                }
                line(positions, if (event.level == ObstacleLevel.BLOCKED) BlockedColor else UncertainColor, 6.dp.toPx())
            }
            val arrowStep = max(1, segments.sumOf { it.size } / 18)
            for (segment in segments) for (i in 0 until segment.lastIndex step arrowStep) {
                val a = screen(segment[i]); val b = screen(segment[min(i + max(1, arrowStep / 3), segment.lastIndex)])
                val vector = (if (reverse) a - b else b - a)
                val length = vector.getDistance()
                if (length < 3) continue
                val direction = vector / length; val normal = Offset(-direction.y, direction.x)
                val tip = (a + b) / 2f
                drawLine(RouteColor, tip - direction * 8f + normal * 5f, tip, 2.dp.toPx())
                drawLine(RouteColor, tip - direction * 8f - normal * 5f, tip, 2.dp.toPx())
            }
            val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { color = android.graphics.Color.WHITE; textSize = 12.dp.toPx(); textAlign = Paint.Align.CENTER; isFakeBoldText = true }
            for ((label, point) in listOf("D" to if (reverse) all.last() else all.first(), "A" to if (reverse) all.first() else all.last())) {
                val p = screen(point)
                drawCircle(if (label == "D") Color(0xFF237A56) else Color(0xFF354454), 11.dp.toPx(), p)
                drawContext.canvas.nativeCanvas.drawText(label, p.x, p.y + 4.dp.toPx(), paint)
            }
            for ((index, event) in report?.events.orEmpty().take(100).withIndex()) {
                val p = screen(coordinate(event.position))
                drawCircle(if (event.level == ObstacleLevel.BLOCKED) BlockedColor else UncertainColor, 9.dp.toPx(), p)
                drawContext.canvas.nativeCanvas.drawText((index + 1).toString(), p.x, p.y + 4.dp.toPx(), paint)
            }
        }
    }
    TextButton(onClick = { zoom = 1f; pan = Offset.Zero }) { Text(t("Recentrer le parcours")) }
}
