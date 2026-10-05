package com.nico.gpx2elev

import android.app.Application
import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.provider.OpenableColumns
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.nico.gpx2elev.core.*
import com.nico.gpx2elev.data.*
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.File
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.util.Locale

data class Result(val name: String, val prepared: PreparedTrack, val computed: Computed, val series: ElevationSeries, val date: Long)
data class AppState(val busy: Boolean = false, val progress: Progress? = null, val result: Result? = null, val error: String? = null, val fileName: String? = null, val clearingCache: Boolean = false, val cacheMessage: String? = null)

class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val mutableState = MutableStateFlow(AppState())
    val state = mutableState.asStateFlow()
    private var job: Job? = null
    private var transport: HttpTransport? = null
    private var retryUri: Uri? = null
    private var pendingUri: Uri? = null
    private val base = File(application.filesDir, "elevation").apply { mkdirs() }
    private val lastTrack = File(base, "last.gpx")
    private val prefs = application.getSharedPreferences("trace", Context.MODE_PRIVATE)
    private val storageLock = Mutex()
    private val mutableCacheSize = MutableStateFlow(CacheSize())
    val cacheSize = mutableCacheSize.asStateFlow()

    init {
        viewModelScope.launch(Dispatchers.IO) {
            storageLock.withLock { mutableCacheSize.value = CacheStorage.size(base) }
        }
    }

    fun clearCache() {
        if (state.value.busy) return
        mutableState.value = state.value.copy(busy = true, clearingCache = true, error = null,
            progress = Progress("Suppression du cache…", 0, 0))
        viewModelScope.launch {
            var message = "Cache vidé."
            try {
                withContext(Dispatchers.IO) { storageLock.withLock { CacheStorage.clear(base) } }
            } catch (e: Exception) {
                message = "Impossible de vider complètement le cache."
            } finally {
                withContext(Dispatchers.IO) { storageLock.withLock { mutableCacheSize.value = CacheStorage.size(base) } }
                mutableState.value = state.value.copy(busy = false, clearingCache = false, progress = null, cacheMessage = message)
                pendingUri?.let { pendingUri = null; import(it) }
            }
        }
    }

    fun restore() {
        if (mutableState.value.result == null && !mutableState.value.busy && lastTrack.exists()) {
            analyze(prefs.getString("name", "Dernière trace.gpx") ?: "Dernière trace.gpx", null)
        }
    }

    fun import(uri: Uri) {
        if (state.value.clearingCache) { pendingUri = uri; return }
        val resolver = getApplication<Application>().contentResolver
        val name = try {
            resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0) else null
            }
        } catch (_: Exception) { null }
        analyze(name ?: uri.lastPathSegment?.substringAfterLast('/')?.substringAfterLast('\\') ?: "Trace.gpx", uri)
    }

    fun retry() {
        val current = mutableState.value.fileName ?: prefs.getString("name", "Trace.gpx") ?: "Trace.gpx"
        if (retryUri != null || lastTrack.exists()) analyze(current, retryUri)
    }

    fun cancel() {
        if (state.value.clearingCache) return
        transport?.cancel()
        job?.cancel()
        job = null
        mutableState.value = mutableState.value.copy(busy = false, progress = null)
    }

    private fun analyze(name: String, uri: Uri?) {
        if (state.value.clearingCache) return
        cancel()
        retryUri = uri
        val http = HttpTransport()
        transport = http
        mutableState.value = AppState(busy = true, progress = Progress("Lecture du GPX", 0, 0), fileName = name)
        job = viewModelScope.launch {
            try {
                val result = withContext(Dispatchers.IO) { storageLock.withLock {
                    val app = getApplication<Application>()
                    if (uri != null) {
                        val temporary = File.createTempFile("import-", ".gpx.part", base)
                        try {
                            app.contentResolver.openInputStream(uri)?.use { input ->
                                temporary.outputStream().use { output ->
                                    val buffer = ByteArray(16384)
                                    var bytes = 0L
                                    while (true) {
                                        ensureActive(); http.checkActive()
                                        val n = input.read(buffer)
                                        if (n < 0) break
                                        bytes += n
                                        require(bytes <= Protocol.MAX_GPX_BYTES) { "Le GPX dépasse 20 Mo." }
                                        output.write(buffer, 0, n)
                                    }
                                    output.fd.sync()
                                }
                            } ?: error("Impossible d'ouvrir ce fichier GPX.")
                            // Parse before replacing the last valid selection.
                            temporary.inputStream().use { GpxParser.parse(it) }
                            ensureActive()
                            Files.move(temporary.toPath(), lastTrack.toPath(), StandardCopyOption.REPLACE_EXISTING)
                            prefs.edit().putString("name", name).apply()
                        } finally { temporary.delete() }
                    }
                    ensureActive()
                    val track = lastTrack.inputStream().use { GpxParser.parse(it) }
                    val prepared = ElevationMath.prepare(track)
                    val cm = app.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
                    val online = cm.activeNetwork?.let { cm.getNetworkCapabilities(it)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) } == true
                    val reader = PublicModels(File(base, "tiles"), http)
                    val repository = ElevationRepository(File(base, "profiles"), reader)
                    val series = repository.obtain(prepared.points, online) { progress ->
                        http.checkActive()
                        mutableState.value = mutableState.value.copy(progress = progress)
                    }
                    ensureActive()
                    mutableState.value = mutableState.value.copy(progress = Progress("Lissage et calcul du dénivelé", prepared.sampleCount, prepared.sampleCount))
                    val computed = ElevationMath.compute(prepared, series.values)
                    ensureActive()
                    pruneCache(File(base, "profiles"), 64L * 1024 * 1024)
                    pruneCache(File(base, "tiles"), 512L * 1024 * 1024)
                    Result(name, prepared, computed, series, System.currentTimeMillis())
                } }
                mutableState.value = AppState(result = result, fileName = name)
            } catch (_: CancellationException) { }
            catch (exception: Exception) {
                if (isActive) mutableState.value = AppState(error = exception.message ?: "Le calcul a échoué.", fileName = name)
            }
            finally {
                withContext(NonCancellable + Dispatchers.IO) {
                    storageLock.withLock {
                        pruneCache(File(base, "profiles"), 64L * 1024 * 1024)
                        pruneCache(File(base, "tiles"), 512L * 1024 * 1024)
                        mutableCacheSize.value = CacheStorage.size(base)
                    }
                }
            }
        }
    }

    fun export(uri: Uri) {
        val result = state.value.result ?: return
        viewModelScope.launch {
            try {
                withContext(Dispatchers.IO) {
                    getApplication<Application>().contentResolver.openOutputStream(uri, "wt")?.bufferedWriter(Charsets.UTF_8)?.use { writer ->
                        writer.write('\uFEFF'.code)
                        writer.write(exportText(result))
                    } ?: error("Impossible de créer le fichier CSV.")
                }
                mutableState.value = mutableState.value.copy(error = "Résultat exporté.")
            } catch (e: Exception) { mutableState.value = mutableState.value.copy(error = e.message ?: "Export impossible.") }
        }
    }

    fun clearMessage() { mutableState.value = mutableState.value.copy(error = null, cacheMessage = null) }

    private fun pruneCache(directory: File, maximum: Long) {
        val files = directory.listFiles()?.filter { it.isFile && !it.name.endsWith(".part") }?.sortedBy { it.lastModified() } ?: return
        var size = files.sumOf { it.length() }
        for (file in files) {
            if (size <= maximum) break
            val length = file.length()
            if (file.delete()) size -= length
        }
    }

    override fun onCleared() { transport?.cancel(); super.onCleared() }

    companion object {
        fun exportText(r: Result): String {
            fun value(d: Double) = String.format(Locale.ROOT, "%.6f", d)
            fun quote(s: String) = "\"" + s.replace("\"", "\"\"") + "\""
            val columns = listOf("fichier", "source", "distance_m", "pas_m", "sigma_m", "hysteresis_m", "Dplus_m", "Dmoins_m", "GPX_brut_Dplus_m", "GPX_brut_Dmoins_m", "GPX_filtre_Dplus_m", "GPX_filtre_Dmoins_m", "points_origine", "positions_5m", "segments", "date_calcul_UTC", "protocole")
            val row = listOf(quote(r.name), quote(r.series.source.label), value(r.prepared.length), "5", "20", "2", value(r.computed.gain.up), value(r.computed.gain.down),
                r.computed.gpxRaw?.up?.let(::value) ?: "", r.computed.gpxRaw?.down?.let(::value) ?: "",
                r.computed.gpxFiltered?.up?.let(::value) ?: "", r.computed.gpxFiltered?.down?.let(::value) ?: "",
                r.prepared.track.pointCount.toString(), r.prepared.sampleCount.toString(), r.prepared.segments.size.toString(),
                java.time.Instant.ofEpochMilli(r.date).toString(), Protocol.VERSION)
            return columns.joinToString(";") + "\n" + row.joinToString(";") + "\n"
        }
    }
}
