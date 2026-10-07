package com.nico.gpx2elev.update

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.update
import java.io.File
import java.io.IOException
import java.util.concurrent.CancellationException

enum class UpdatePhase { IDLE, CHECKING, CURRENT, AVAILABLE, DOWNLOADING, READY, VALIDATING, PERMISSION, INSTALLER, ERROR }

data class UpdateState(val open: Boolean = false, val currentVersion: String = "", val phase: UpdatePhase = UpdatePhase.IDLE,
    val release: UpdateRelease? = null, val downloaded: DownloadedApk? = null,
    val completed: Long = 0, val total: Long = 0, val error: String? = null, val installRequested: Boolean = false) {
    val busy: Boolean get() = phase in setOf(UpdatePhase.CHECKING, UpdatePhase.DOWNLOADING, UpdatePhase.VALIDATING)
}

/** Independent of GPX calculations; the Activity alone opens settings and the system installer. */
class UpdateViewModel(app: Application, private val httpFactory: () -> UpdateHttp) : AndroidViewModel(app) {
    constructor(app: Application) : this(app, ::UpdateHttp)
    private val mutableState = MutableStateFlow(UpdateState(currentVersion = ApkUpdate.installed(app).versionName ?: "0.0.0"))
    val state: StateFlow<UpdateState> = mutableState
    private var job: Job? = null
    @Volatile private var client: UpdateHttp? = null

    fun open() {
        mutableState.update { it.copy(open = true) }
        if (!state.value.busy && state.value.downloaded == null) check()
    }

    fun dismiss() {
        mutableState.update { it.copy(open = false, installRequested = false) }
        job?.cancel()
        client?.cancel()
    }

    fun check() {
        if (job?.isCompleted == false) return
        mutableState.update { it.copy(phase = UpdatePhase.CHECKING, release = null, downloaded = null, error = null) }
        runTask {
            val http = httpFactory().also { client = it }
            val release = http.check(state.value.currentVersion)
            mutableState.update { it.copy(phase = if (release == null) UpdatePhase.CURRENT else UpdatePhase.AVAILABLE, release = release) }
        }
    }

    fun primaryAction() {
        if (state.value.busy) return
        when {
            state.value.downloaded != null -> requestInstall()
            state.value.release != null -> download()
            else -> check()
        }
    }

    private fun download() {
        val release = state.value.release ?: return
        if (job?.isCompleted == false) return
        mutableState.update { it.copy(phase = UpdatePhase.DOWNLOADING, completed = 0, total = release.size, error = null) }
        runTask {
            val http = httpFactory().also { client = it }
            val downloaded = http.download(release, File(getApplication<Application>().cacheDir, "updates")) { done, total ->
                mutableState.update { it.copy(completed = done, total = total) }
            }
            try {
                ApkUpdate.verify(getApplication(), downloaded.file, release, downloaded.sha256)
            } catch (error: Exception) {
                downloaded.file.delete()
                throw error
            }
            mutableState.update { it.copy(phase = UpdatePhase.READY, downloaded = downloaded) }
        }
    }

    fun requestInstall() {
        val current = state.value
        val downloaded = current.downloaded ?: return
        val release = current.release ?: return
        if (job?.isCompleted == false) return
        mutableState.update { it.copy(phase = UpdatePhase.VALIDATING, error = null) }
        runTask {
            // Recheck immediately before sharing the APK, including after a trip to Android settings.
            try {
                ApkUpdate.verify(getApplication(), downloaded.file, release, downloaded.sha256)
            } catch (error: Exception) {
                downloaded.file.delete()
                mutableState.update { it.copy(downloaded = null) }
                throw error
            }
            mutableState.update { it.copy(phase = UpdatePhase.READY, installRequested = it.open) }
        }
    }

    fun consumeInstallRequest() {
        mutableState.update { it.copy(installRequested = false, phase = UpdatePhase.INSTALLER) }
    }

    fun permissionRequired() {
        mutableState.update { it.copy(installRequested = false, phase = UpdatePhase.PERMISSION) }
    }

    fun fail(message: String) {
        mutableState.update { it.copy(phase = UpdatePhase.ERROR, installRequested = false, error = message) }
    }

    private fun runTask(action: () -> Unit) {
        job = viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) { action() }
            } catch (_: CancellationException) {
                mutableState.update { it.copy(phase = if (it.downloaded != null) UpdatePhase.READY
                    else if (it.release != null) UpdatePhase.AVAILABLE else UpdatePhase.IDLE) }
            } catch (error: UpdateException) {
                fail(error.message ?: "Réponse de mise à jour invalide.")
            } catch (_: IOException) {
                fail("Impossible de télécharger la mise à jour. Vérifiez Internet, l'espace libre et réessayez.")
            } catch (_: Exception) {
                fail("La vérification de la mise à jour a échoué.")
            } finally {
                client = null
            }
        }
    }

    override fun onCleared() {
        client?.cancel()
        super.onCleared()
    }
}
