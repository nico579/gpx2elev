package com.nico.gpxdenivele

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.core.content.IntentCompat
import androidx.lifecycle.ViewModelProvider
import com.nico.gpxdenivele.ui.GpxScreen

class MainActivity : ComponentActivity() {
    private val model: AppViewModel by viewModels { ViewModelProvider.AndroidViewModelFactory(application) }
    private val open = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri -> uri?.let(model::import) }
    private val export = registerForActivityResult(ActivityResultContracts.CreateDocument("text/csv")) { uri -> uri?.let(model::export) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null && !importIntent(intent)) model.restore()
        setContent {
            val state by model.state.collectAsState()
            GpxScreen(state, onImport = { open.launch(arrayOf("*/*")) }, onCancel = model::cancel,
                onRetry = model::retry, onExport = {
                    val name = state.result?.name?.substringBeforeLast('.') ?: "trace"
                    export.launch("${name}_denivele.csv")
                }, onClearMessage = model::clearMessage)
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
