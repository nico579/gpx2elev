package com.nico.gpx2elev

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.LaunchedEffect
import androidx.core.content.IntentCompat
import androidx.core.content.FileProvider
import androidx.lifecycle.ViewModelProvider
import com.nico.gpx2elev.ui.GpxScreen
import com.nico.gpx2elev.update.UpdatePhase
import com.nico.gpx2elev.update.UpdateViewModel

class MainActivity : ComponentActivity() {
    private val model: AppViewModel by viewModels { ViewModelProvider.AndroidViewModelFactory(application) }
    private val updates: UpdateViewModel by viewModels { ViewModelProvider.AndroidViewModelFactory(application) }
    private val open = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(model::import) }
    private val export = registerForActivityResult(ActivityResultContracts.CreateDocument("text/csv")) { uri -> uri?.let(model::export) }
    private val installPermission = registerForActivityResult(ActivityResultContracts.StartActivityForResult()) {
        if (packageManager.canRequestPackageInstalls()) updates.requestInstall()
        else updates.fail("L'autorisation d'installer la mise à jour n'a pas été accordée.")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        I18n.initialize(this)
        if (savedInstanceState == null && !importIntent(intent)) model.restore()
        setContent {
            val state by model.state.collectAsState()
            val cacheSize by model.cacheSize.collectAsState()
            val updateState by updates.state.collectAsState()
            LaunchedEffect(updateState.installRequested) {
                if (updateState.installRequested) {
                    if (!packageManager.canRequestPackageInstalls()) updates.permissionRequired()
                    else {
                        updates.consumeInstallRequest()
                        try {
                            val file = updateState.downloaded?.file ?: return@LaunchedEffect
                            val uri = FileProvider.getUriForFile(this@MainActivity, "$packageName.updates", file)
                            startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
                                .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION))
                        } catch (_: Exception) {
                            updates.fail("Impossible d'ouvrir l'installateur Android.")
                        }
                    }
                }
            }
            GpxScreen(state, onImport = { open.launch(arrayOf("*/*")) }, onCancel = model::cancel,
                onRetry = model::retry, onExport = {
                    val name = state.result?.name?.substringBeforeLast('.') ?: "trace"
                    export.launch("${name}_denivele.csv")
                }, onClearMessage = model::clearMessage, cacheSize = cacheSize, onClearCache = model::clearCache,
                updateState = updateState, onUpdates = updates::open, onUpdateClose = updates::dismiss,
                onUpdateCheck = updates::check, onUpdateAction = {
                    if (updateState.phase == UpdatePhase.PERMISSION) {
                        try {
                            installPermission.launch(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName")))
                        } catch (_: Exception) {
                            updates.fail("Impossible d'ouvrir les réglages d'installation Android.")
                        }
                    } else updates.primaryAction()
                })
        }
    }

    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent); setIntent(intent); importIntent(intent) }

    private fun importIntent(intent: Intent?): Boolean {
        val uri = when (intent?.action) {
            Intent.ACTION_VIEW -> intent.data
            Intent.ACTION_SEND -> IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java)
                ?: intent.clipData?.takeIf { it.itemCount > 0 }?.getItemAt(0)?.uri
                ?: intent.data
            else -> null
        }
        if (uri != null) { model.import(uri); return true }
        return false
    }
}
