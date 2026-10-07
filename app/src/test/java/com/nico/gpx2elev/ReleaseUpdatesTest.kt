package com.nico.gpx2elev

import android.content.pm.PackageInfo
import android.content.pm.Signature
import android.content.pm.SigningInfo
import android.os.Build
import android.os.Looper
import androidx.core.content.FileProvider
import com.nico.gpx2elev.update.*
import org.json.JSONArray
import org.json.JSONObject
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode
import org.robolectric.shadow.api.Shadow
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.CancellationException
import java.util.concurrent.LinkedBlockingQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34])
class ReleaseUpdatesTest {
    @get:Rule val temporary = TemporaryFolder()
    private lateinit var server: ServerSocket
    private lateinit var serving: Thread
    private data class Reply(val body: ByteArray = byteArrayOf(), val code: Int = 200, val headers: String = "")
    private val replies = LinkedBlockingQueue<Reply>()
    private val requests = java.util.Collections.synchronizedList(mutableListOf<String>())
    private val payload = "verified update".toByteArray()
    private fun hash(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }

    @Before fun startServer() {
        server = ServerSocket().apply { bind(InetSocketAddress("127.0.0.1", 0)) }
        serving = Thread {
            while (!server.isClosed) {
                try { server.accept().use { socket ->
                    socket.soTimeout = 3000
                    val input = socket.getInputStream().bufferedReader(Charsets.US_ASCII)
                    input.readLine()
                    while (true) { if (input.readLine().isNullOrEmpty()) break }
                    val reply = replies.poll(3, java.util.concurrent.TimeUnit.SECONDS) ?: error("Missing test reply")
                    val output = socket.getOutputStream()
                    output.write(("HTTP/1.1 ${reply.code} Reply\r\nContent-Length: ${reply.body.size}\r\n" +
                        reply.headers + "Connection: close\r\n\r\n").toByteArray(Charsets.US_ASCII))
                    output.write(reply.body)
                    output.flush()
                } } catch (error: IOException) { if (!server.isClosed) throw error }
            }
        }.apply { isDaemon = true; start() }
    }
    @After fun stopServer() { server.close(); serving.join(3000) }
    private fun http() = UpdateHttp { request ->
        requests.add(request.toString())
        URL("http://127.0.0.1:${server.localPort}${request.path}").openConnection() as HttpURLConnection
    }
    private fun metadata(version: String = "0.4.0"): JSONObject {
        val tag = "v$version"
        val name = "gpx2elev-$version.apk"
        return JSONObject().put("tag_name", tag).put("draft", false).put("prerelease", false).put("body", "Release notes")
            .put("assets", JSONArray().put(JSONObject().put("name", name).put("size", payload.size)
                .put("digest", "sha256:" + hash(payload))
                .put("browser_download_url", "https://github.com/nico579/gpx2elev/releases/download/$tag/$name")))
    }
    private fun release() = ReleaseMetadata.parse(metadata(), "0.3.3")!!
    private fun rejected(action: () -> Unit) {
        try { action(); fail("Invalid update should be rejected") } catch (_: UpdateException) { }
    }

    @Test fun versionsCompareNumericallyAndNeverDowngrade() {
        assertTrue(ReleaseVersions.newer("v0.10.0", "0.9.9"))
        assertFalse(ReleaseVersions.newer("0.3.3", "v0.3.3"))
        assertNull(ReleaseMetadata.parse(metadata("0.3.2"), "0.3.3"))
        for (bad in listOf("0.4.0-beta", "0.04.0", "../0.4.0", "0.4", "2147483648.0.0")) rejected { ReleaseVersions.parse(bad) }
    }

    @Test fun metadataRejectsForeignUrlsPrereleasesMissingAndDuplicateFiles() {
        val mutations: List<(JSONObject) -> Unit> = listOf(
            { it.put("draft", true) }, { it.put("prerelease", true) },
            { it.getJSONArray("assets").getJSONObject(0).put("browser_download_url", "https://example.com/app.apk") },
            { it.getJSONArray("assets").getJSONObject(0).put("size", "15") },
            { it.getJSONArray("assets").getJSONObject(0).put("digest", "sha256:bad") },
            { it.getJSONArray("assets").getJSONObject(0).remove("digest") },
            { it.getJSONArray("assets").put(it.getJSONArray("assets").getJSONObject(0)) },
            { it.put("assets", JSONArray()) })
        for (mutate in mutations) {
            val json = metadata()
            mutate(json)
            rejected { ReleaseMetadata.parse(json, "0.3.3") }
        }
    }

    @Test fun realHttpCheckAndVerifiedDownloadKeepOnlyCompleteFile() {
        replies.add(Reply(metadata().toString().toByteArray()))
        replies.add(Reply(payload))
        val http = http()
        val release = http.check("0.3.3")!!
        val directory = temporary.newFolder()
        val progress = mutableListOf<Long>()
        val result = http.download(release, directory) { done, _ -> progress.add(done) }
        assertArrayEquals(payload, result.file.readBytes())
        assertEquals(hash(payload), result.sha256)
        assertEquals(payload.size.toLong(), progress.last())
        assertEquals(listOf(LATEST_URL, release.url), requests)
        assertEquals(listOf(release.name), directory.list()!!.toList())
    }

    @Test fun incorrectHashTruncatedAndOversizeBodyNeverReplaceVerifiedDownload() {
        val directory = temporary.newFolder()
        val original = File(directory, release().name).apply { writeBytes(payload) }
        for (body in listOf(ByteArray(payload.size), payload.copyOf(payload.size - 1), payload + byteArrayOf(1))) {
            replies.add(Reply(body))
            rejected { http().download(release(), directory) }
            assertArrayEquals(payload, original.readBytes())
            assertEquals(listOf(release().name), directory.list()!!.toList())
        }
    }

    @Test fun missingDigestUsesPublishedChecksumFileAndMalformedJsonIsRejected() {
        val json = metadata()
        json.getJSONArray("assets").getJSONObject(0).remove("digest")
        val url = "https://github.com/nico579/gpx2elev/releases/download/v0.4.0/SHA256SUMS.txt"
        json.getJSONArray("assets").put(JSONObject().put("name", "SHA256SUMS.txt").put("browser_download_url", url))
        val release = ReleaseMetadata.parse(json, "0.3.3")!!
        replies.add(Reply((hash(payload) + "  ${release.name}\n").toByteArray()))
        replies.add(Reply(payload))
        assertArrayEquals(payload, http().download(release, temporary.newFolder()).file.readBytes())
        replies.add(Reply("not JSON".toByteArray()))
        rejected { http().check("0.3.3") }
    }

    @Test fun insecureRedirectsAndGithubRateLimitExplainTheFailure() {
        for (bad in listOf("http://github.com/app.apk", "https://evil.example/app.apk", "https://github.com@evil.example/app.apk")) {
            replies.add(Reply(code = 302, headers = "Location: $bad\r\n"))
            val count = requests.size
            rejected { http().check("0.3.3") }
            assertEquals(count + 1, requests.size)
        }
        replies.add(Reply(code = 429))
        try { http().check("0.3.3"); fail() } catch (error: UpdateException) { assertTrue(error.message!!.contains("limite")) }
    }

    @Test fun cancellationRemovesThePartialApk() {
        replies.add(Reply(payload))
        val directory = temporary.newFolder()
        val http = http()
        try { http.download(release(), directory) { _, _ -> http.cancel() }; fail() } catch (_: CancellationException) { }
        assertTrue(directory.list()!!.isEmpty())
    }

    private fun immediateConnection(request: URL, contents: ByteArray): HttpURLConnection = object : HttpURLConnection(request) {
        override fun connect() { }
        override fun disconnect() { }
        override fun usingProxy() = false
        override fun getResponseCode() = 200
        override fun getInputStream(): java.io.InputStream = contents.inputStream()
    }

    private fun awaitUpdate(model: UpdateViewModel) {
        val deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5)
        while (model.state.value.busy && System.nanoTime() < deadline) {
            Shadows.shadowOf(Looper.getMainLooper()).idle()
            Thread.sleep(5)
        }
        Shadows.shadowOf(Looper.getMainLooper()).idle()
        assertFalse("The update operation completes", model.state.value.busy)
    }

    private fun nextVersion(increment: Int = 1): String {
        val version = ReleaseVersions.parse(ApkUpdate.installed(RuntimeEnvironment.getApplication()).versionName ?: "0.0.0")
        return "${version[0]}.${version[1]}.${version[2] + increment}"
    }

    @Test @LooperMode(LooperMode.Mode.PAUSED) fun reopeningTheMenuChecksForANewerReleaseAgain() {
        val created = AtomicInteger()
        val model = UpdateViewModel(RuntimeEnvironment.getApplication()) {
            val version = nextVersion(created.incrementAndGet())
            UpdateHttp { request -> immediateConnection(request, metadata(version).toString().toByteArray()) }
        }
        model.open()
        awaitUpdate(model)
        assertEquals(nextVersion(), model.state.value.release?.version)
        model.dismiss()
        model.open()
        awaitUpdate(model)
        assertEquals(nextVersion(2), model.state.value.release?.version)
        assertEquals(2, created.get())
        model.dismiss()
    }

    @Test @LooperMode(LooperMode.Mode.PAUSED) fun cancellingNetworkCheckCannotStartAnOverlappingJob() {
        val entered = CountDownLatch(1)
        val unblock = CountDownLatch(1)
        val created = AtomicInteger()
        val model = UpdateViewModel(RuntimeEnvironment.getApplication()) {
            val first = created.incrementAndGet() == 1
            UpdateHttp { request ->
                if (first) {
                    entered.countDown()
                    assertTrue(unblock.await(5, TimeUnit.SECONDS))
                }
                immediateConnection(request, metadata(nextVersion()).toString().toByteArray())
            }
        }
        model.open()
        Shadows.shadowOf(Looper.getMainLooper()).idle()
        assertTrue(entered.await(5, TimeUnit.SECONDS))
        model.dismiss()
        model.check()
        assertEquals("Wait for the cancelling job before creating another client", 1, created.get())
        unblock.countDown()
        awaitUpdate(model)
        assertFalse(model.state.value.open)
        assertEquals(UpdatePhase.IDLE, model.state.value.phase)
        model.open()
        awaitUpdate(model)
        assertEquals(2, created.get())
        assertEquals(UpdatePhase.AVAILABLE, model.state.value.phase)
        model.dismiss()
    }

    @Suppress("DEPRECATION")
    private fun identity(version: String, code: Int, key: ByteArray): PackageInfo = PackageInfo().apply {
        packageName = "com.nico.gpx2elev"
        versionName = version
        versionCode = code
        val signatures = arrayOf(Signature(key))
        if (Build.VERSION.SDK_INT >= 28) {
            signingInfo = Shadow.newInstanceOf(SigningInfo::class.java).also { Shadows.shadowOf(it).setSignatures(signatures) }
        } else this.signatures = signatures
    }

    private fun checkIdentity() {
        val current = identity("0.3.3", 6, byteArrayOf(1, 2, 3))
        val candidate = identity("0.4.0", 7, byteArrayOf(1, 2, 3))
        ApkUpdate.verifyIdentity(candidate, current, release())
        rejected { ApkUpdate.verifyIdentity(identity("0.4.0", 7, byteArrayOf(4)), current, release()) }
        rejected { ApkUpdate.verifyIdentity(identity("0.4.0", 6, byteArrayOf(1, 2, 3)), current, release()) }
        rejected { ApkUpdate.verifyIdentity(identity("0.4.1", 7, byteArrayOf(1, 2, 3)), current, release()) }
        candidate.packageName = "another.application"
        rejected { ApkUpdate.verifyIdentity(candidate, current, release()) }
    }
    @Test fun apkIdentityAndCurrentSigningCertificateMustMatch() { checkIdentity() }
    @Test @Config(sdk = [26]) fun oldAndroidAlsoRejectsDifferentSignerAndNonIncreasingVersionCode() { checkIdentity() }

    @Test fun fileProviderSharesOnlyThePrivateUpdateFolder() {
        // AndroidX uses '/' for canonical path boundaries; Robolectric on Windows uses '\\'.
        // This integration check runs on Linux release CI, where paths match the Android runtime.
        org.junit.Assume.assumeTrue("FileProvider needs Android-style path separators", File.separatorChar == '/')
        val context = RuntimeEnvironment.getApplication()
        val file = File(context.cacheDir, "updates/test.apk").apply { parentFile!!.mkdirs(); writeBytes(payload) }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.updates", file)
        assertEquals("content", uri.scheme)
        assertEquals("${context.packageName}.updates", uri.authority)
        assertArrayEquals(payload, context.contentResolver.openInputStream(uri)!!.use { it.readBytes() })
        val other = File(context.cacheDir, "last.gpx").apply { writeText("private track") }
        try { FileProvider.getUriForFile(context, "${context.packageName}.updates", other); fail() } catch (_: IllegalArgumentException) { }
    }
}
