package com.nico.gpx2elev.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
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
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.nico.gpx2elev.AppState
import com.nico.gpx2elev.Result
import com.nico.gpx2elev.R
import com.nico.gpx2elev.core.Profile
import com.nico.gpx2elev.data.ElevationRepository
import com.nico.gpx2elev.I18n
import com.nico.gpx2elev.I18n.text as t
import kotlin.math.*

private val Green = Color(0xFF237A56)
private val Light = lightColorScheme(primary = Green, background = Color(0xFFF4F6F2), surface = Color.White,
    surfaceVariant = Color(0xFFEAF0E7), onSurfaceVariant = Color(0xFF4B5D51), primaryContainer = Color(0xFFE0F1DC), onPrimaryContainer = Color(0xFF153D2B))
private val Dark = darkColorScheme(primary = Color(0xFF9FDAAE), onPrimary = Color(0xFF153D2B), background = Color(0xFF101B17), surface = Color(0xFF1B2922),
    surfaceVariant = Color(0xFF293B30), onSurfaceVariant = Color(0xFFB8CABB), primaryContainer = Color(0xFF244D36), onPrimaryContainer = Color(0xFFC0EDCA))
private fun meters(value: Double) = String.format(I18n.locale, t("%,.0f"), value)
private fun distance(value: Double) = String.format(I18n.locale, t("%.2f"), value / 1000)

@Composable
fun GpxScreen(state: AppState, onImport: () -> Unit, onCancel: () -> Unit, onRetry: () -> Unit, onExport: () -> Unit, onClearMessage: () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light) {
        val colors = MaterialTheme.colorScheme
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
                }
            }, bottomBar = {
                Surface(shadowElevation = 8.dp) {
                    Column(Modifier.navigationBarsPadding().padding(horizontal = 20.dp, vertical = 12.dp)) {
                        Button(onClick = if (state.busy) onCancel else onImport,
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
    ProfileCard(result.computed.profiles, result.prepared.length, result.computed.minAltitude, result.computed.maxAltitude)
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

@Composable private fun ProfileCard(profiles: List<Profile>, length: Double, minAltitude: Double, maxAltitude: Double) {
    val line = MaterialTheme.colorScheme.primary
    val labels = MaterialTheme.colorScheme.onSurfaceVariant
    val paths = remember(profiles) { profiles.map { profile ->
        // Preserve minima/maxima per bucket to avoid hiding narrow peaks in the display.
        val n = profile.distance.size
        val stride = max(1, n / 600)
        val indices = mutableSetOf(0, n - 1)
        for (start in 0 until n step stride) {
            val end = min(n, start + stride)
            indices += (start until end).minBy { profile.elevation[it] }
            indices += (start until end).maxBy { profile.elevation[it] }
        }
        indices.sorted().map { profile.distance[it] to profile.elevation[it] }
    } }
    Card(shape = RoundedCornerShape(18.dp)) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
            Text(t("Profil d'altitude"), fontSize = 17.sp, fontWeight = FontWeight.SemiBold)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(t("Min. ${meters(minAltitude)} m"), fontSize = 12.sp, color = labels)
                Text(t("Max. ${meters(maxAltitude)} m"), fontSize = 12.sp, color = labels)
            }
            Canvas(Modifier.fillMaxWidth().height(150.dp)) {
                val span = max(20.0, maxAltitude - minAltitude)
                val low = (maxAltitude + minAltitude - span) / 2
                val margin = 8.dp.toPx()
                val h = size.height - 2 * margin
                for (i in 0..3) {
                    val y = margin + i * h / 3
                    drawLine(labels.copy(alpha = .13f), Offset(0f, y), Offset(size.width, y), 1.dp.toPx())
                }
                for (points in paths) {
                    if (points.isEmpty()) continue
                    val path = Path()
                    val firstX = (points.first().first / length * size.width).toFloat()
                    var lastX = firstX
                    for ((i, pair) in points.withIndex()) {
                        val x = (pair.first / length * size.width).toFloat()
                        val y = (margin + h * (1 - (pair.second - low) / span)).toFloat()
                        if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                        lastX = x
                    }
                    val fill = Path().apply { addPath(path); lineTo(lastX, size.height); lineTo(firstX, size.height); close() }
                    drawPath(fill, line.copy(alpha = .10f))
                    drawPath(path, line, style = Stroke(width = 2.dp.toPx()))
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(t("0 km"), color = labels, fontSize = 11.sp)
                Text(t("${distance(length)} km"), color = labels, fontSize = 11.sp)
            }
        }
    }
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
