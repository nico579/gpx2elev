package com.nico.gpx2elev.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.nico.gpx2elev.I18n
import com.nico.gpx2elev.I18n.text as t
import com.nico.gpx2elev.update.UpdatePhase
import com.nico.gpx2elev.update.UpdateState

@Composable
internal fun UpdateDialog(state: UpdateState, installEnabled: Boolean, onClose: () -> Unit, onCheck: () -> Unit, onAction: () -> Unit) {
    val message = when (state.phase) {
        UpdatePhase.IDLE, UpdatePhase.CHECKING -> "Recherche de mises à jour…"
        UpdatePhase.CURRENT -> "Vous utilisez la dernière version publiée."
        UpdatePhase.AVAILABLE -> "Une nouvelle version est disponible."
        UpdatePhase.DOWNLOADING -> "Téléchargement de la mise à jour…"
        UpdatePhase.VALIDATING -> "Vérification de la mise à jour…"
        UpdatePhase.READY -> "Mise à jour vérifiée. Vous pouvez lancer l'installation."
        UpdatePhase.PERMISSION -> "Android demande votre autorisation pour installer une mise à jour depuis gpx2elev. Activez cette autorisation dans les réglages, puis revenez ici."
        UpdatePhase.INSTALLER -> "Confirmez l'installation dans la fenêtre Android. Si vous l'avez annulée, vous pouvez réessayer."
        UpdatePhase.ERROR -> state.error ?: "La vérification de la mise à jour a échoué."
    }
    val action = when (state.phase) {
        UpdatePhase.AVAILABLE -> "Télécharger et installer"
        UpdatePhase.PERMISSION -> "Autoriser l'installation"
        UpdatePhase.READY, UpdatePhase.INSTALLER -> "Installer"
        UpdatePhase.ERROR -> "Réessayer"
        else -> "Vérifier à nouveau"
    }
    AlertDialog(onDismissRequest = onClose, title = { Text(t("Mises à jour")) },
        text = {
            Column(Modifier.heightIn(max = 300.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text(t("Version installée : {0}").replace("{0}", state.currentVersion))
                Text(t(message))
                state.release?.let { release ->
                    val size = String.format(I18n.locale, "%.1f", release.size / 1048576.0)
                    Text(t("Version {0} disponible · {1} Mio").replace("{0}", release.version).replace("{1}", size))
                    if (release.notes.isNotBlank()) Text(release.notes, style = MaterialTheme.typography.bodySmall)
                }
                if (state.busy) {
                    if (state.phase == UpdatePhase.DOWNLOADING && state.total > 0) {
                        LinearProgressIndicator(progress = { (state.completed.toFloat() / state.total).coerceIn(0f, 1f) }, modifier = Modifier.fillMaxWidth())
                        Text("${(state.completed * 100 / state.total).coerceIn(0, 100)} %")
                    } else LinearProgressIndicator(Modifier.fillMaxWidth())
                }
                if (!installEnabled && state.release != null) Text(t("Attendez la fin du calcul avant d'installer la mise à jour."))
            }
        }, confirmButton = {
            if (!state.busy) TextButton(onClick = if (state.phase in setOf(UpdatePhase.IDLE, UpdatePhase.CURRENT)) onCheck else onAction,
                enabled = installEnabled || state.release == null) { Text(t(action)) }
        }, dismissButton = { TextButton(onClick = onClose) { Text(t(if (state.busy) "Annuler" else "Fermer")) } })
}
