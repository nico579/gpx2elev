package com.nico.gpx2elev.data

import java.io.File
import java.nio.file.Files
import java.nio.file.LinkOption.NOFOLLOW_LINKS

data class CacheSize(val profiles: Long = 0, val tiles: Long = 0) {
    val total: Long get() = profiles + tiles
}

object CacheStorage {
    private fun size(directory: File): Long {
        if (!directory.exists() || Files.isSymbolicLink(directory.toPath())) return 0
        return Files.walk(directory.toPath()).use { paths ->
            paths.filter { Files.isRegularFile(it, NOFOLLOW_LINKS) }.mapToLong { Files.size(it) }.sum()
        }
    }

    fun size(base: File) = CacheSize(size(File(base, "profiles")), size(File(base, "tiles")))

    fun clear(base: File) {
        for (name in listOf("profiles", "tiles")) {
            val root = File(base, name).toPath()
            if (Files.isSymbolicLink(root)) {
                Files.delete(root)
            } else if (Files.exists(root)) {
                // Files.walk does not follow symlinks. Preserve reusable directories.
                Files.walk(root).use { paths ->
                    paths.filter { !Files.isDirectory(it, NOFOLLOW_LINKS) }.forEach { Files.delete(it) }
                }
            }
        }
    }
}
