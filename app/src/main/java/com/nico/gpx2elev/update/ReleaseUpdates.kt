package com.nico.gpx2elev.update

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

private const val REPOSITORY = "https://github.com/nico579/gpx2elev"
internal const val LATEST_URL = "https://api.github.com/repos/nico579/gpx2elev/releases/latest"
private const val MAX_APK_BYTES = 64L * 1024 * 1024

class UpdateException(message: String) : IOException(message)

data class UpdateRelease(val version: String, val tag: String, val name: String, val url: String,
    val size: Long, val sha256: String?, val notes: String, val checksumUrl: String? = null)

data class DownloadedApk(val file: File, val sha256: String)

object ReleaseVersions {
    fun parse(value: String): List<Int> {
        if (!Regex("v?(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)").matches(value))
            throw UpdateException("Version de mise à jour invalide.")
        return value.removePrefix("v").split('.').map {
            it.toIntOrNull() ?: throw UpdateException("Version de mise à jour invalide.")
        }
    }

    fun newer(candidate: String, current: String): Boolean {
        val a = parse(candidate)
        val b = parse(current)
        return a.indices.firstOrNull { a[it] != b[it] }?.let { a[it] > b[it] } ?: false
    }
}

object ReleaseMetadata {
    fun parse(json: JSONObject, current: String): UpdateRelease? {
        if (json.opt("draft") != false || json.opt("prerelease") != false)
            throw UpdateException("Réponse de mise à jour invalide.")
        val tag = json.optString("tag_name")
        if (!ReleaseVersions.newer(tag, current)) return null
        val version = tag.removePrefix("v")
        val name = "gpx2elev-$version.apk"
        val assets = json.optJSONArray("assets") ?: throw UpdateException("Réponse de mise à jour invalide.")
        val matches = (0 until assets.length()).mapNotNull { assets.optJSONObject(it) }.filter { it.optString("name") == name }
        if (matches.size != 1) throw UpdateException("Le fichier de mise à jour de ce système est absent.")
        val asset = matches.single()
        val url = "$REPOSITORY/releases/download/$tag/$name"
        val size = asset.optLong("size", -1)
        if (asset.optString("browser_download_url") != url || size !in 1..MAX_APK_BYTES ||
            (asset.opt("size") !is Int && asset.opt("size") !is Long))
            throw UpdateException("Réponse de mise à jour invalide.")
        val digest = if (asset.isNull("digest")) null else asset.optString("digest")
        if (digest != null && !Regex("sha256:[0-9a-fA-F]{64}").matches(digest))
            throw UpdateException("Empreinte de mise à jour invalide.")
        val checksumUrl = "$REPOSITORY/releases/download/$tag/SHA256SUMS.txt"
        if (digest == null && !(0 until assets.length()).mapNotNull { assets.optJSONObject(it) }.any {
                it.optString("name") == "SHA256SUMS.txt" && it.optString("browser_download_url") == checksumUrl
            }) throw UpdateException("Empreinte de mise à jour absente.")
        return UpdateRelease(version, tag, name, url, size, digest?.substring(7)?.lowercase(),
            json.optString("body").take(20000), if (digest == null) checksumUrl else null)
    }
}

/** Downloads only from the official HTTPS endpoints, with bounded redirects, size and timeouts. */
class UpdateHttp(private val openConnection: (URL) -> HttpURLConnection = { it.openConnection() as HttpURLConnection }) {
    private val cancelled = AtomicBoolean(false)
    private val active = AtomicReference<HttpURLConnection?>()

    fun cancel() {
        cancelled.set(true)
        active.getAndSet(null)?.disconnect()
    }

    private fun checkCancellation() {
        if (cancelled.get() || Thread.currentThread().isInterrupted) throw CancellationException()
    }

    private fun open(address: String): HttpURLConnection {
        var url = URL(address)
        repeat(6) {
            checkCancellation()
            if (url.protocol != "https" || url.host !in setOf("api.github.com", "github.com",
                    "release-assets.githubusercontent.com", "objects.githubusercontent.com") || url.userInfo != null || url.port !in listOf(-1, 443))
                throw UpdateException("Adresse de mise à jour invalide.")
            val connection = openConnection(url)
            active.set(connection)
            try {
                checkCancellation()
                connection.connectTimeout = 15000
                connection.readTimeout = 30000
                connection.instanceFollowRedirects = false
                connection.setRequestProperty("User-Agent", "gpx2elev-update")
                connection.setRequestProperty("Accept-Encoding", "identity")
                connection.setRequestProperty("Accept", if (address == LATEST_URL) "application/vnd.github+json" else "application/octet-stream")
                val code = connection.responseCode
                if (code in listOf(301, 302, 303, 307, 308)) {
                    val location = connection.getHeaderField("Location") ?: throw UpdateException("Adresse de mise à jour invalide.")
                    url = URL(url, location)
                    connection.disconnect()
                    active.compareAndSet(connection, null)
                } else {
                    if (code != 200) throw UpdateException(when (code) {
                        403, 429 -> "GitHub limite les vérifications. Réessayez plus tard."
                        404 -> if (address == LATEST_URL) "Aucune release publiée pour le moment." else "Le serveur de mises à jour est indisponible."
                        else -> "Le serveur de mises à jour est indisponible."
                    })
                    return connection
                }
            } catch (error: Exception) {
                connection.disconnect()
                active.compareAndSet(connection, null)
                checkCancellation()
                throw error
            }
        }
        throw UpdateException("Adresse de mise à jour invalide.")
    }

    private fun bytes(url: String, limit: Int): ByteArray {
        val connection = open(url)
        try {
            connection.inputStream.use { input ->
                val output = java.io.ByteArrayOutputStream()
                val buffer = ByteArray(65536)
                while (true) {
                    checkCancellation()
                    val count = input.read(buffer)
                    if (count < 0) break
                    if (output.size() + count > limit) throw UpdateException("Réponse de mise à jour trop volumineuse.")
                    output.write(buffer, 0, count)
                }
                checkCancellation()
                return output.toByteArray()
            }
        } finally {
            connection.disconnect()
            active.compareAndSet(connection, null)
        }
    }

    fun check(current: String): UpdateRelease? {
        val text = bytes(LATEST_URL, 1024 * 1024).toString(Charsets.UTF_8)
        val metadata = try { JSONObject(text) } catch (_: org.json.JSONException) {
            throw UpdateException("Réponse de mise à jour invalide.")
        }
        return ReleaseMetadata.parse(metadata, current)
    }

    fun download(release: UpdateRelease, directory: File, progress: (Long, Long) -> Unit = { _, _ -> }): DownloadedApk {
        if (!directory.isDirectory && !directory.mkdirs()) throw IOException("Cannot create update directory")
        var expected = release.sha256
        if (expected == null) {
            val lines = bytes(release.checksumUrl ?: throw UpdateException("Empreinte de mise à jour absente."), 65536)
                .toString(Charsets.UTF_8).lineSequence()
            val values = lines.mapNotNull { Regex("([0-9a-fA-F]{64})  (.+)").matchEntire(it) }
                .filter { it.groupValues[2] == release.name }.map { it.groupValues[1].lowercase() }.toList()
            if (values.size != 1) throw UpdateException("Empreinte de mise à jour absente.")
            expected = values.single()
        }
        val temporary = File(directory, "download-${UUID.randomUUID()}.part")
        val final = File(directory, release.name)
        val connection = open(release.url)
        try {
            val digest = MessageDigest.getInstance("SHA-256")
            var count = 0L
            temporary.outputStream().use { output ->
                connection.inputStream.use { input ->
                    val buffer = ByteArray(65536)
                    while (true) {
                        checkCancellation()
                        val size = input.read(buffer)
                        if (size < 0) break
                        count += size
                        if (count > release.size) throw UpdateException("Fichier de mise à jour incomplet ou corrompu.")
                        output.write(buffer, 0, size)
                        digest.update(buffer, 0, size)
                        progress(count, release.size)
                    }
                }
            }
            checkCancellation()
            if (count != release.size || digest.digest().hex() != expected)
                throw UpdateException("Fichier de mise à jour incomplet ou corrompu.")
            java.nio.file.Files.move(temporary.toPath(), final.toPath(), java.nio.file.StandardCopyOption.REPLACE_EXISTING)
            return DownloadedApk(final, expected)
        } finally {
            connection.disconnect()
            active.compareAndSet(connection, null)
            temporary.delete()
        }
    }
}

internal fun ByteArray.hex(): String = joinToString("") { "%02x".format(it) }

object ApkUpdate {
    @Suppress("DEPRECATION")
    private fun flags() = if (Build.VERSION.SDK_INT >= 28) PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES

    @Suppress("DEPRECATION")
    fun installed(context: Context): PackageInfo = context.packageManager.getPackageInfo(context.packageName, flags())

    @Suppress("DEPRECATION")
    private fun signers(info: PackageInfo): Set<String> {
        val signatures = if (Build.VERSION.SDK_INT >= 28) info.signingInfo?.apkContentsSigners else info.signatures
        return signatures?.map { MessageDigest.getInstance("SHA-256").digest(it.toByteArray()).hex() }?.toSet() ?: emptySet()
    }

    @Suppress("DEPRECATION")
    fun verifyIdentity(candidate: PackageInfo, current: PackageInfo, release: UpdateRelease) {
        val candidateCode = if (Build.VERSION.SDK_INT >= 28) candidate.longVersionCode else candidate.versionCode.toLong()
        val currentCode = if (Build.VERSION.SDK_INT >= 28) current.longVersionCode else current.versionCode.toLong()
        if (candidate.packageName != current.packageName || candidate.versionName != release.version || candidateCode <= currentCode)
            throw UpdateException("L'APK ne correspond pas à cette application ou à une version plus récente.")
        val expected = signers(current)
        if (expected.isEmpty() || signers(candidate) != expected)
            throw UpdateException("La signature de la mise à jour ne correspond pas à l'application installée.")
    }

    @Suppress("DEPRECATION")
    fun verify(context: Context, file: File, release: UpdateRelease, expectedHash: String) {
        val folder = File(context.cacheDir, "updates").canonicalFile
        if (file.canonicalFile.parentFile != folder || file.name != release.name || file.length() != release.size)
            throw UpdateException("Fichier de mise à jour incomplet ou corrompu.")
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(65536)
            while (true) {
                val count = input.read(buffer)
                if (count < 0) break
                digest.update(buffer, 0, count)
            }
        }
        if (digest.digest().hex() != expectedHash) throw UpdateException("Fichier de mise à jour incomplet ou corrompu.")
        val candidate = context.packageManager.getPackageArchiveInfo(file.absolutePath, flags())
            ?: throw UpdateException("L'APK de mise à jour est illisible.")
        verifyIdentity(candidate, installed(context), release)
    }
}
