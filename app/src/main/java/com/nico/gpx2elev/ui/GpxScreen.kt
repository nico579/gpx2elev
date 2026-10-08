package com.nico.gpx2elev.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.semantics.onClick
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import com.nico.gpx2elev.AppState
import com.nico.gpx2elev.Result
import com.nico.gpx2elev.R
import com.nico.gpx2elev.core.Profile
import com.nico.gpx2elev.core.PreparedTrack
import com.nico.gpx2elev.data.ElevationRepository
import com.nico.gpx2elev.data.CacheSize
import com.nico.gpx2elev.I18n
import com.nico.gpx2elev.I18n.text as t
import com.nico.gpx2elev.update.UpdateState
import kotlin.math.*

private val Green = Color(0xFF237A56)
private val Light = lightColorScheme(primary = Green, background = Color(0xFFF4F6F2), surface = Color.White,
    surfaceVariant = Color(0xFFEAF0E7), onSurfaceVariant = Color(0xFF4B5D51), primaryContainer = Color(0xFFE0F1DC), onPrimaryContainer = Color(0xFF153D2B))
private val Dark = darkColorScheme(primary = Color(0xFF9FDAAE), onPrimary = Color(0xFF153D2B), background = Color(0xFF101B17), surface = Color(0xFF1B2922),
    surfaceVariant = Color(0xFF293B30), onSurfaceVariant = Color(0xFFB8CABB), primaryContainer = Color(0xFF244D36), onPrimaryContainer = Color(0xFFC0EDCA))
private fun meters(value: Double) = String.format(I18n.locale, t("%,.0f"), value)
private fun distance(value: Double) = String.format(I18n.locale, t("%.2f"), value / 1000)

@Composable
fun GpxScreen(state: AppState, onImport: () -> Unit, onCancel: () -> Unit, onRetry: () -> Unit, onExport: () -> Unit, onClearMessage: () -> Unit,
    cacheSize: CacheSize = CacheSize(), onClearCache: () -> Unit = {},
    updateState: UpdateState = UpdateState(), onUpdates: () -> Unit = {}, onUpdateClose: () -> Unit = {},
    onUpdateCheck: () -> Unit = {}, onUpdateAction: () -> Unit = {}) {
    var confirmCache by remember { mutableStateOf(false) }
    var showMenu by remember { mutableStateOf(false) }
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light) {
        val colors = MaterialTheme.colorScheme
        if (updateState.open) UpdateDialog(updateState, !state.busy, onUpdateClose, onUpdateCheck, onUpdateAction)
        if (confirmCache) {
            AlertDialog(onDismissRequest = { confirmCache = false }, title = { Text(t("Vider le cache ?")) },
                text = { Text(t("Les altitudes devront être téléchargées à nouveau. Le GPX, les réglages et le résultat affiché sont conservés.")) },
                confirmButton = { TextButton(onClick = { confirmCache = false; onClearCache() }, enabled = !state.busy) { Text(t("Vider le cache")) } },
                dismissButton = { TextButton(onClick = { confirmCache = false }) { Text(t("Annuler")) } })
        }
        Surface(Modifier.fillMaxSize(), color = colors.background) {
            Scaffold(containerColor = colors.background, topBar = {
                Row(Modifier.fillMaxWidth().background(Color(0xFF112B25)).statusBarsPadding().padding(horizontal = 22.dp, vertical = 18.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Mountains(Modifier.size(36.dp), Color(0xFFB4E6BE))
                    Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) {
                        Text(stringResource(R.string.app_name), color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.SemiBold)
                        Text(t("Le relief de votre parcours"), color = Color(0xFFB6C8B9), fontSize = 12.sp)
                    }
                    for (language in listOf("fr", "en")) {
                        TextButton(onClick = { I18n.select(language) },
                            modifier = Modifier.width(42.dp), contentPadding = PaddingValues(0.dp)) {
                            Text(language.uppercase(), color = if (I18n.language == language) Color.White else Color(0xFF819B91),
                                fontWeight = if (I18n.language == language) FontWeight.Bold else FontWeight.Normal)
                        }
                    }
                    Box {
                        IconButton(onClick = { showMenu = true }) {
                            Icon(Icons.Default.MoreVert, t("Menu"), tint = Color.White)
                        }
                        DropdownMenu(expanded = showMenu, onDismissRequest = { showMenu = false }) {
                            DropdownMenuItem(text = { Text(t("Mises à jour")) }, onClick = { showMenu = false; onUpdates() })
                        }
                    }
                }
            }, bottomBar = {
                Surface(shadowElevation = 8.dp) {
                    Column(Modifier.navigationBarsPadding().padding(horizontal = 20.dp, vertical = 12.dp)) {
                        Button(onClick = if (state.busy) onCancel else onImport,
                            enabled = !state.clearingCache,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 54.dp), shape = RoundedCornerShape(16.dp)) {
                            Icon(if (state.busy) Icons.Default.Close else Icons.Default.Add, null)
                            Spacer(Modifier.width(10.dp))
                            Text(if (state.busy) t("Annuler le calcul") else if (state.result != null) t("Importer une autre trace GPX") else t("Importer une trace GPX"), fontSize = 16.sp)
                        }
                    }
                }
            }) { padding ->
                Column(Modifier.padding(padding).fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    when {
                        state.busy -> Loading(state)
                        state.result != null -> ResultCards(state.result, onExport)
                        state.error != null -> ErrorCard(state.error, state.fileName, onRetry)
                        else -> Welcome()
                    }
                    if (state.result != null && state.error != null) {
                        Card {
                            Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                                Text(t(state.error), Modifier.weight(1f))
                                IconButton(onClick = onClearMessage) { Icon(Icons.Default.Close, t("Fermer le message")) }
                            }
                        }
                    }
                    ProtocolCard()
                    Card(shape = RoundedCornerShape(20.dp)) {
                        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            fun size(bytes: Long) = when {
                                bytes < 1024 -> "$bytes " + t("octets")
                                bytes < 1048576 -> String.format(I18n.locale, "%.1f", bytes / 1024.0) + " " + t("Kio")
                                else -> String.format(I18n.locale, "%.1f", bytes / 1048576.0) + " " + t("Mio")
                            }
                            Text(t("Cache des altitudes") + " · " + size(cacheSize.total), fontWeight = FontWeight.SemiBold)
                            Text(t("Profils") + " : " + size(cacheSize.profiles) + " / 64 " + t("Mio") + " · " +
                                t("Tuiles") + " : " + size(cacheSize.tiles) + " / 512 " + t("Mio"), fontSize = 12.sp)
                            OutlinedButton(onClick = { confirmCache = true }, enabled = !state.busy && cacheSize.total > 0) {
                                Text(t("Vider le cache"))
                            }
                            state.cacheMessage?.let { Text(t(it), fontSize = 12.sp) }
                        }
                    }
                    if (state.result == null && !state.busy) {
                        Text(t("Le premier calcul utilise Internet. Les données téléchargées restent disponibles pour cette trace hors connexion."),
                            color = colors.onSurfaceVariant, fontSize = 13.sp, lineHeight = 19.sp)
                    }
                    Text(t("IGN · Mapterhorn · FABDEM · Copernicus · SRTM"), color = colors.onSurfaceVariant, fontSize = 11.sp)
                }
            }
        }
    }
}

@Composable private fun Welcome() {
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.primaryContainer)) {
        Column(Modifier.fillMaxWidth().padding(24.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Mountains(Modifier.fillMaxWidth().height(110.dp), MaterialTheme.colorScheme.primary)
            Text(t("Le dénivelé de votre parcours"), fontSize = 27.sp, lineHeight = 33.sp, fontWeight = FontWeight.SemiBold)
            Text(t("Importez votre parcours pour calculer sa montée, sa descente et son profil d'altitude à partir des modèles de terrain."), lineHeight = 23.sp)
        }
    }
}

@Composable private fun Loading(state: AppState) {
    Card(shape = RoundedCornerShape(24.dp)) {
        Column(Modifier.fillMaxWidth().padding(24.dp), verticalArrangement = Arrangement.spacedBy(18.dp)) {
            Text(state.fileName ?: t("Votre parcours"), fontWeight = FontWeight.SemiBold)
            Text(t(state.progress?.message ?: "Calcul en cours"), fontSize = 21.sp)
            val progress = state.progress
            if (progress != null && progress.total > 0 && progress.completed > 0) {
                LinearProgressIndicator(progress = { (progress.completed.toFloat() / progress.total).coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth())
                Text(t("${meters(progress.completed.toDouble())} / ${meters(progress.total.toDouble())} positions"), color = MaterialTheme.colorScheme.onSurfaceVariant)
            } else LinearProgressIndicator(Modifier.fillMaxWidth())
            Text(t("Lecture des altitudes, puis lissage du profil et cumul des montées."), color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 13.sp)
        }
    }
}

@Composable private fun ErrorCard(message: String, name: String?, onRetry: () -> Unit) {
    Card(shape = RoundedCornerShape(24.dp)) {
        Column(Modifier.fillMaxWidth().padding(22.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Icon(Icons.Default.Warning, null, tint = MaterialTheme.colorScheme.error)
            Text(t("Calcul indisponible"), fontSize = 23.sp, fontWeight = FontWeight.SemiBold)
            name?.let { Text(it, color = MaterialTheme.colorScheme.onSurfaceVariant) }
            Text(t(message), fontSize = 14.sp, lineHeight = 21.sp)
            OutlinedButton(onClick = onRetry) { Icon(Icons.Default.Refresh, null); Spacer(Modifier.width(8.dp)); Text(t("Réessayer")) }
        }
    }
}

@Composable private fun ResultCards(result: Result, onExport: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    Text(result.name, fontSize = 16.sp, fontWeight = FontWeight.Medium, maxLines = 2, overflow = TextOverflow.Ellipsis)
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = colors.primaryContainer)) {
        Column(Modifier.fillMaxWidth().padding(24.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(t("DÉNIVELÉ POSITIF"), fontSize = 12.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 1.sp)
                Spacer(Modifier.weight(1f))
                Icon(Icons.Default.Check, null, tint = colors.primary, modifier = Modifier.size(20.dp))
            }
            Row(verticalAlignment = Alignment.Bottom) {
                Text(meters(result.computed.gain.up), fontSize = 66.sp, fontWeight = FontWeight.SemiBold, letterSpacing = (-2).sp, modifier = Modifier.weight(1f, fill = false))
                Text(t(" m"), fontSize = 28.sp, modifier = Modifier.padding(bottom = 12.dp))
            }
            Text(result.series.source.label, fontWeight = FontWeight.Medium, fontSize = 16.sp)
            Text(if (result.series.fromCache) t("Altitudes conservées sur cet appareil") else t("Profil complet · ${meters(result.prepared.sampleCount.toDouble())} positions"), color = colors.onSurfaceVariant, fontSize = 12.sp)
        }
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Metric(t("DESCENTE · D−"), t("${meters(result.computed.gain.down)} m"), Modifier.weight(1f))
        Metric(t("DISTANCE"), t("${distance(result.prepared.length)} km"), Modifier.weight(1f))
    }
    ProfileCard(result.prepared, result.computed.profiles)
    if (result.series.cacheWarning != null) {
        Text(t("Le profil n'a pas pu être enregistré dans le cache. Le résultat reste disponible, mais son utilisation hors connexion n'est pas assurée."),
            color = colors.onSurfaceVariant, fontSize = 12.sp)
    }
    if (result.series.fallbacks.isNotEmpty()) {
        Card(shape = RoundedCornerShape(18.dp)) {
            Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(t("Modèle de repli utilisé"), fontWeight = FontWeight.SemiBold)
                Text(t("${result.series.source.label} a fourni le premier profil complet."), fontSize = 14.sp)
                for (failure in result.series.fallbacks) {
                    Text(t("${failure.source.label} : ${t(failure.reason)}"), fontSize = 12.sp, color = colors.onSurfaceVariant)
                }
            }
        }
    }
    var expanded by remember(result) { mutableStateOf(false) }
    Card(shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.fillMaxWidth().padding(18.dp)) {
            TextButton(onClick = { expanded = !expanded }, contentPadding = PaddingValues(0.dp)) {
                Text(if (expanded) t("Masquer les valeurs du GPX") else t("Comparer avec les altitudes du GPX"))
            }
            if (expanded) {
                Text(t("Somme brute des variations"), fontWeight = FontWeight.Medium)
                Text(result.computed.gpxRaw?.let { t("D+ ${meters(it.up)} m · D− ${meters(it.down)} m") } ?: t("Altitudes GPX manquantes."), fontSize = 14.sp)
                Spacer(Modifier.height(14.dp))
                Text(t("GPX filtré · même protocole"), fontWeight = FontWeight.Medium)
                Text(result.computed.gpxFiltered?.let { t("D+ ${meters(it.up)} m · D− ${meters(it.down)} m") } ?: t("Altitudes GPX manquantes."), fontSize = 14.sp)
                Spacer(Modifier.height(14.dp))
                Text(t("${meters(result.prepared.track.pointCount.toDouble())} points d'origine · ${result.prepared.segments.size} segment(s)"), color = colors.onSurfaceVariant, fontSize = 12.sp)
            }
        }
    }
    OutlinedButton(onClick = onExport, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(14.dp)) {
        Icon(Icons.Default.Share, null); Spacer(Modifier.width(8.dp)); Text(t("Exporter le résultat en CSV"))
    }
}

@Composable private fun Metric(label: String, value: String, modifier: Modifier) {
    Card(modifier, shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text(label, fontSize = 10.sp, letterSpacing = .5.sp, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Text(value, fontSize = 23.sp, fontWeight = FontWeight.SemiBold, maxLines = 1)
        }
    }
}

@Composable private fun ProfileCard(prepared: PreparedTrack, profiles: List<Profile>) {
    val line = MaterialTheme.colorScheme.primary
    val observations = if (isSystemInDarkTheme()) Color(0xFFF0B16B) else Color(0xFFB86A22)
    val labels = MaterialTheme.colorScheme.onSurfaceVariant
    val chart = remember(prepared, profiles) { profileChartData(prepared, profiles) }
    val length = prepared.length
    val minAltitude = chart.minAltitude
    val maxAltitude = chart.maxAltitude
    val fullViewport = remember(chart, length) { fullProfileViewport(chart, length) }
    var viewport by remember(chart) { mutableStateOf(fullViewport) }
    var fullscreen by remember(chart) { mutableStateOf(false) }
    var selection by remember(chart) { mutableStateOf<ProfileSelection?>(null) }
    val hasTime = remember(chart) { chart.observations.any { it.point.time != null } }
    val compactFullscreen = fullscreen && LocalConfiguration.current.screenHeightDp < 500
    fun axisDistance(value: Double) = String.format(I18n.locale,
        if (viewport.distanceSpan < 100) "%.4f" else if (viewport.distanceSpan < 1000) "%.3f" else "%.2f", value / 1000)
    fun axisAltitude(value: Double) = String.format(I18n.locale,
        if (viewport.altitudeSpan < 2) "%.2f" else if (viewport.altitudeSpan < 20) "%.1f" else "%,.0f", value)
    fun selectedAltitude(value: Double?) = value?.let { String.format(I18n.locale, "%,.1f", it) } ?: "—"
    val selectedDescription = selection?.let {
        t("Distance : ${String.format(I18n.locale, "%.4f", it.distance / 1000)} km") + "; " +
            t("Heure locale : ") + profileTimeLabel(it.time, seconds = true, language = I18n.language, date = true) + "; " +
            t("Terrain lissé : ${selectedAltitude(it.terrain)} m") + "; " +
            t("${if (it.interpolated) "GPX interpolé" else "Mesure GPX"} : ${selectedAltitude(it.gpx)} m")
    } ?: t("Touchez la courbe pour lire les valeurs.")
    val tapDescription = t("Lire les valeurs de la courbe")
    val paths = remember(chart, viewport) { chart.terrain.map { visibleProfilePoints(it, viewport) }.filter { it.isNotEmpty() } }
    val observationPaths = remember(chart, viewport) { chart.gpx.map { visibleProfilePoints(it, viewport) }.filter { it.isNotEmpty() } }
    val plotMarginPx = with(LocalDensity.current) { 8.dp.toPx() }
    val chartDescription = t("Profils d'altitude : terrain lissé et mesures GPX, distance en kilomètres et altitude en mètres")
    val content: @Composable () -> Unit = {
        Card(modifier = if (fullscreen) Modifier.fillMaxSize() else Modifier.fillMaxWidth(), shape = RoundedCornerShape(18.dp)) {
            Column(Modifier.fillMaxWidth().then(if (fullscreen) Modifier.fillMaxHeight() else Modifier).padding(if (fullscreen) 12.dp else 18.dp),
                verticalArrangement = Arrangement.spacedBy(if (fullscreen) 6.dp else 14.dp)) {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    Text(t("Profil d'altitude"), Modifier.weight(1f), fontSize = 17.sp, fontWeight = FontWeight.SemiBold,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    if (compactFullscreen) ProfileZoomControls(viewport, fullViewport) { viewport = it }
                    TextButton(onClick = { fullscreen = !fullscreen }) {
                        Text(t(if (fullscreen) "Quitter le plein écran" else "Plein écran"))
                    }
                }
                val legends: @Composable () -> Unit = {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Canvas(Modifier.width(22.dp).height(10.dp)) {
                            drawLine(line, Offset(0f, size.height / 2), Offset(size.width, size.height / 2), 2.dp.toPx())
                        }
                        Spacer(Modifier.width(8.dp))
                        Text(t("Profil lissé (terrain)"), fontSize = 12.sp, color = labels)
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Canvas(Modifier.width(22.dp).height(10.dp)) {
                            drawLine(observations, Offset(0f, size.height / 2), Offset(size.width, size.height / 2), 2.dp.toPx(),
                                pathEffect = PathEffect.dashPathEffect(floatArrayOf(5.dp.toPx(), 3.dp.toPx())))
                        }
                        Spacer(Modifier.width(8.dp))
                        Text(t("Mesures GPX"), fontSize = 12.sp, color = labels)
                    }
                }
                if (compactFullscreen) Row(horizontalArrangement = Arrangement.spacedBy(18.dp)) { legends() }
                else Column(verticalArrangement = Arrangement.spacedBy(6.dp)) { legends() }
                if (chart.gpx.isEmpty()) Text(t("Altitudes GPX manquantes."), fontSize = 12.sp, color = labels)
                if (!compactFullscreen) Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                    ProfileZoomControls(viewport, fullViewport) { viewport = it }
                }
                if (!fullscreen) {
                    Text(t("Pincez pour zoomer, glissez pour déplacer, touchez pour lire les valeurs."), fontSize = 11.sp, color = labels)
                    Text(t("Altitudes totales"), fontSize = 11.sp, color = labels)
                }
                if (!compactFullscreen) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(t("Min. ${meters(minAltitude)} m"), fontSize = 12.sp, color = labels)
                    Text(t("Max. ${meters(maxAltitude)} m"), fontSize = 12.sp, color = labels)
                }
                Canvas(Modifier.fillMaxWidth().then(if (fullscreen) Modifier.weight(1f) else Modifier.height(150.dp))
                    .semantics {
                        contentDescription = chartDescription
                        stateDescription = selectedDescription
                        onClick(tapDescription) {
                            selection = selectProfilePoint(chart, (viewport.minDistance + viewport.maxDistance) / 2,
                                (viewport.minAltitude + viewport.maxAltitude) / 2, viewport)
                            true
                        }
                    }
                    .pointerInput(chart) {
                        detectTapGestures { position ->
                            if (size.width > 0 && size.height > 2 * plotMarginPx &&
                                position.y in plotMarginPx..(size.height - plotMarginPx)) {
                                val x = viewport.minDistance + position.x / size.width * viewport.distanceSpan
                                val z = viewport.maxAltitude - (position.y - plotMarginPx) / (size.height - 2 * plotMarginPx) * viewport.altitudeSpan
                                selection = selectProfilePoint(chart, x, z, viewport)
                            }
                        }
                    }
                    .pointerInput(chart) {
                        detectTransformGestures { centroid, pan, zoom, _ ->
                            val plotHeight = size.height - 2 * plotMarginPx
                            if (size.width > 0 && plotHeight > 0) {
                                viewport = transformProfileViewport(viewport, fullViewport, zoom.toDouble(),
                                    centroid.x / size.width.toDouble(), 1 - (centroid.y - plotMarginPx) / plotHeight.toDouble(),
                                    pan.x / size.width.toDouble(), pan.y / plotHeight.toDouble())
                            }
                        }
                    }) {
                    val span = viewport.altitudeSpan
                    val low = viewport.minAltitude
                    val margin = 8.dp.toPx()
                    val h = size.height - 2 * margin
                    for (i in 0..3) {
                        val y = margin + i * h / 3
                        drawLine(labels.copy(alpha = .13f), Offset(0f, y), Offset(size.width, y), 1.dp.toPx())
                    }
                    fun pathFor(points: List<Pair<Double, Double>>): Path {
                        val path = Path()
                        for ((i, pair) in points.withIndex()) {
                            val x = ((pair.first - viewport.minDistance) / viewport.distanceSpan * size.width).toFloat()
                            val y = (margin + h * (1 - (pair.second - low) / span)).toFloat()
                            if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                        }
                        return path
                    }
                    clipRect(top = margin, bottom = size.height - margin) {
                        for (points in paths) {
                            val path = pathFor(points)
                            val firstX = ((points.first().first - viewport.minDistance) / viewport.distanceSpan * size.width).toFloat()
                            val lastX = ((points.last().first - viewport.minDistance) / viewport.distanceSpan * size.width).toFloat()
                            val fill = Path().apply { addPath(path); lineTo(lastX, size.height); lineTo(firstX, size.height); close() }
                            drawPath(fill, line.copy(alpha = .10f))
                        }
                        for (points in observationPaths) {
                            if (points.size == 1 || points.all { it == points.first() }) {
                                val point = points.first()
                                drawCircle(observations, radius = 2.dp.toPx(), center = Offset(
                                    ((point.first - viewport.minDistance) / viewport.distanceSpan * size.width).toFloat(),
                                    (margin + h * (1 - (point.second - low) / span)).toFloat()))
                            } else {
                                drawPath(pathFor(points), observations, style = Stroke(width = 1.5.dp.toPx(),
                                    pathEffect = PathEffect.dashPathEffect(floatArrayOf(5.dp.toPx(), 3.dp.toPx()))))
                            }
                        }
                        for (points in paths) drawPath(pathFor(points), line, style = Stroke(width = 2.dp.toPx()))
                        selection?.takeIf { it.distance in viewport.minDistance..viewport.maxDistance }?.let { point ->
                            val x = ((point.distance - viewport.minDistance) / viewport.distanceSpan * size.width).toFloat()
                            drawLine(labels, Offset(x, margin), Offset(x, size.height - margin), 1.dp.toPx(),
                                pathEffect = PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(), 3.dp.toPx())))
                            for ((altitude, color) in listOf(point.terrain to line, point.gpx to observations)) {
                                if (altitude != null && altitude in viewport.minAltitude..viewport.maxAltitude) {
                                    val y = (margin + h * (1 - (altitude - low) / span)).toFloat()
                                    drawCircle(color, radius = 4.dp.toPx(), center = Offset(x, y))
                                }
                            }
                        }
                    }
                }
                BoxWithConstraints(Modifier.fillMaxWidth()) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        for (i in 0..2) {
                            val x = viewport.minDistance + viewport.distanceSpan * i / 2
                            Column(horizontalAlignment = if (i == 0) Alignment.Start else if (i == 2) Alignment.End else Alignment.CenterHorizontally) {
                                Text(t("${axisDistance(x)} km"), color = labels, fontSize = 11.sp)
                                Text(profileTimeLabel(profileTimeAt(chart, x), seconds = viewport.distanceSpan < 1000), color = labels, fontSize = 10.sp)
                            }
                        }
                    }
                    selection?.takeIf { it.distance in viewport.minDistance..viewport.maxDistance }?.let { point ->
                        val width = 120.dp
                        val fraction = ((point.distance - viewport.minDistance) / viewport.distanceSpan).toFloat()
                        val x = (maxWidth * fraction - width / 2).coerceIn(0.dp, maxOf(0.dp, maxWidth - width))
                        Surface(Modifier.offset(x = x).width(width), color = MaterialTheme.colorScheme.primaryContainer,
                            shape = RoundedCornerShape(6.dp)) {
                            Column(Modifier.padding(horizontal = 4.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(String.format(I18n.locale, "%.4f km", point.distance / 1000), fontSize = 11.sp)
                                Text(profileTimeLabel(point.time, seconds = true), fontSize = 10.sp)
                            }
                        }
                    }
                }
                if (!compactFullscreen) Text(t(if (hasTime) "Distance · Heure locale" else "Distance · Heures GPX absentes."), color = labels, fontSize = 10.sp)
                selection?.let { point ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        Text(t("Terrain lissé : ${selectedAltitude(point.terrain)} m"), Modifier.weight(1f), color = line, fontSize = 12.sp)
                        Text(t("${if (point.interpolated) "GPX interpolé" else "Mesure GPX"} : ${selectedAltitude(point.gpx)} m"), Modifier.weight(1f), color = observations, fontSize = 12.sp)
                    }
                    if (!compactFullscreen) Text(t("Heure locale : ") + profileTimeLabel(point.time, seconds = true, language = I18n.language, date = true),
                        color = labels, fontSize = 11.sp)
                }
                Text(t("Altitude visible : ${axisAltitude(viewport.minAltitude)} à ${axisAltitude(viewport.maxAltitude)} m"), color = labels, fontSize = 11.sp)
            }
        }
    }
    if (fullscreen) {
        Dialog(onDismissRequest = { fullscreen = false },
            properties = DialogProperties(usePlatformDefaultWidth = false, decorFitsSystemWindows = false)) {
            Surface(Modifier.fillMaxSize()) {
                Box(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) { content() }
            }
        }
    } else content()
}

@Composable private fun ProfileZoomControls(viewport: ProfileViewport, fullViewport: ProfileViewport,
    onChange: (ProfileViewport) -> Unit) {
    val zoomOutDescription = t("Zoom arrière")
    IconButton(onClick = { onChange(transformProfileViewport(viewport, fullViewport, 2.0)) },
        enabled = viewport.distanceSpan > fullViewport.distanceSpan / 200 * 1.000001) {
        Icon(Icons.Default.Add, t("Zoom avant"))
    }
    IconButton(onClick = { onChange(transformProfileViewport(viewport, fullViewport, .5)) }, enabled = viewport != fullViewport) {
        Text("−", Modifier.clearAndSetSemantics { contentDescription = zoomOutDescription }, fontSize = 24.sp)
    }
    TextButton(onClick = { onChange(fullViewport) }, enabled = viewport != fullViewport) { Text(t("Vue complète")) }
}

@Composable private fun ProtocolCard() {
    var expanded by remember { mutableStateOf(false) }
    val colors = MaterialTheme.colorScheme
    Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = colors.surfaceVariant)) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text(t("Protocole de calcul"), fontWeight = FontWeight.SemiBold)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Pill(t("Pas 5 m"), Modifier.weight(1f))
                Pill(t("σ 20 m"), Modifier.weight(1f))
                Pill(t("Seuil 2 m"), Modifier.weight(1f))
            }
            TextButton(onClick = { expanded = !expanded }, contentPadding = PaddingValues(0.dp)) {
                Icon(Icons.Default.Info, null, Modifier.size(16.dp)); Spacer(Modifier.width(8.dp))
                Text(if (expanded) t("Réduire les explications") else t("Méthode et sources"))
            }
            if (expanded) {
                Text(t("Le parcours est rééchantillonné tous les 5 m. Seules les altitudes sont lissées, avec une gaussienne de σ = 20 m. Une montée ou descente est confirmée après un retournement de 2 m ; les petites hausses successives restent cumulées."), fontSize = 13.sp, lineHeight = 20.sp)
                Text(t("Ordre de repli : ") + ElevationRepository.RANKING.joinToString(t(" → ")) { it.label } + t(". Le premier modèle couvrant toute la trace fournit le profil. Cet ordre vient de la comparaison en France métropolitaine."), fontSize = 13.sp, lineHeight = 20.sp)
                Text(t("Les coordonnées GPX sont conservées. Près d'une falaise, leur précision peut fortement influencer le résultat. Le D+ affiché est une estimation selon ce protocole."), fontSize = 13.sp, lineHeight = 20.sp)
                Text(t("Les coordonnées sont envoyées au service IGN pour lire les altitudes. Les autres modèles utilisent leurs tuiles publiques. GPX et altitudes sont conservés sur cet appareil."), fontSize = 12.sp, lineHeight = 19.sp)
                Text(t("Données : IGN (Licence Ouverte) ; Mapterhorn et ses producteurs (mapterhorn.com/attribution) ; FABDEM 1.2, University of Bristol (CC BY-NC-SA 4.0) ; Copernicus DEM © DLR e.V., Airbus Defence and Space GmbH, financé par l'Union européenne ; SRTM NASA/USGS, miroir Kurviger."), fontSize = 11.sp, lineHeight = 17.sp)
            }
        }
    }
}

@Composable private fun Pill(text: String, modifier: Modifier) {
    Surface(modifier, color = MaterialTheme.colorScheme.surface, shape = RoundedCornerShape(10.dp)) {
        Box(Modifier.padding(horizontal = 6.dp, vertical = 10.dp), contentAlignment = Alignment.Center) { Text(text, fontSize = 12.sp, fontWeight = FontWeight.Medium) }
    }
}

@Composable private fun Mountains(modifier: Modifier, color: Color) {
    Canvas(modifier) {
        val path = Path().apply {
            moveTo(size.width * .05f, size.height * .85f)
            lineTo(size.width * .39f, size.height * .12f)
            lineTo(size.width * .66f, size.height * .72f)
            lineTo(size.width * .79f, size.height * .39f)
            lineTo(size.width * .96f, size.height * .85f)
        }
        drawPath(path, color, style = Stroke(width = 3.dp.toPx()))
        drawLine(color.copy(alpha = .5f), Offset(size.width * .05f, size.height * .92f), Offset(size.width * .96f, size.height * .92f), 2.dp.toPx())
    }
}
