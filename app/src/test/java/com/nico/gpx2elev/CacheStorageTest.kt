package com.nico.gpx2elev

import com.nico.gpx2elev.data.CacheStorage
import com.nico.gpx2elev.data.CacheSize
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.nio.file.Files

class CacheStorageTest {
    @Test fun clearsDownloadsAndPartialFilesButPreservesUserFiles() {
        val root = Files.createTempDirectory("cache-test").toFile()
        try {
            val contents = mapOf("profiles/a.profile" to "123", "tiles/sub/b.tif" to "4567",
                "tiles/interrupted.part" to "89", "last.gpx" to "gpx", "settings.json" to "{}", "result.csv" to "result")
            contents.forEach { (name, data) -> File(root, name).apply { parentFile!!.mkdirs(); writeText(data) } }
            assertEquals(CacheSize(3, 6), CacheStorage.size(root))
            CacheStorage.clear(root)
            assertEquals(CacheSize(), CacheStorage.size(root))
            CacheStorage.clear(root)
            assertEquals("gpx", File(root, "last.gpx").readText())
            assertEquals("{}", File(root, "settings.json").readText())
            assertEquals("result", File(root, "result.csv").readText())
        } finally { root.deleteRecursively() }
    }

    @Test fun absentCacheIsEmpty() {
        val root = Files.createTempDirectory("empty-cache-test").toFile()
        try {
            CacheStorage.clear(root)
            assertEquals(CacheSize(), CacheStorage.size(root))
        } finally { root.deleteRecursively() }
    }
}
