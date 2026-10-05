package com.nico.gpxdenivele

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONObject
import java.util.Locale

/** Shared FR/EN catalog; changing language never modifies the calculation. */
object I18n {
    var language by mutableStateOf("fr")
        private set
    private var catalog = emptyList<Pair<String, String>>()
    private var preferences: android.content.SharedPreferences? = null
    val locale: Locale get() = if (language == "fr") Locale.FRANCE else Locale.US

    fun initialize(context: Context) {
        preferences = context.getSharedPreferences("language", Context.MODE_PRIVATE)
        val json = context.assets.open("translations.json").bufferedReader().use { JSONObject(it.readText()) }
        catalog = json.keys().asSequence().map { it to json.getString(it) }.sortedByDescending { it.first.length }.toList()
        val default = if (context.resources.configuration.locales[0].language == "fr") "fr" else "en"
        language = preferences?.getString("choice", default)?.takeIf { it == "fr" || it == "en" } ?: default
    }

    fun select(value: String) {
        require(value == "fr" || value == "en")
        language = value
        preferences?.edit()?.putString("choice", value)?.apply()
    }

    fun text(input: String): String {
        if (language != "en") return input
        var output = input
        val placeholder = Regex("\\{(\\d+)\\}")
        for ((fr, en) in catalog) {
            val matches = placeholder.findAll(fr).toList()
            if (matches.isEmpty()) continue
            var start = 0
            val pattern = buildString {
                for (match in matches) {
                    append(Regex.escape(fr.substring(start, match.range.first)))
                    append("(.+?)")
                    start = match.range.last + 1
                }
                append(Regex.escape(fr.substring(start)))
            }
            output = Regex(pattern).replace(output) { match ->
                val values = matches.mapIndexed { i, m -> m.groupValues[1] to match.groupValues[i + 1] }.toMap()
                placeholder.replace(en) { values.getValue(it.groupValues[1]) }
            }
        }
        for ((fr, en) in catalog) if (!placeholder.containsMatchIn(fr)) output = output.replace(fr, en)
        return output
    }
}
