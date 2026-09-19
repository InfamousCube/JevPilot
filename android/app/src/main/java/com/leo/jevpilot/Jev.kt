package com.leo.jevpilot

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class JevError(msg: String) : Exception(msg)

/** Thin client for TypeSafe's System One endpoint (Jev), same as jevpilot/jev.py on the PC. */
class Jev(private val apiKey: String) {
    companion object {
        const val ENDPOINT = "https://api.typesafe.ai/v1/systemone"
        const val MODEL = "jev-latest"
        const val MAX_CHOICE_OPTIONS = 255

        fun choice(instructions: String, options: Map<String, String>): JSONObject =
            JSONObject().put("type", "choice").put("instructions", instructions)
                .put("criteria", JSONObject(options))

        fun noul(instructions: String): JSONObject =
            JSONObject().put("type", "noul").put("instructions", instructions)
    }

    /** Returns (answers, seconds). */
    fun ask(state: Any, questions: JSONObject, retries: Int = 3): Pair<JSONObject, Double> {
        if (apiKey.isBlank()) throw JevError("No API key set (Settings).")
        val body = JSONObject().put("model", MODEL).put("state", state).put("questions", questions)
            .toString().toByteArray()
        var delay = 1000L
        for (attempt in 0..retries) {
            val t0 = System.nanoTime()
            val conn = URL(ENDPOINT).openConnection() as HttpURLConnection
            try {
                conn.requestMethod = "POST"
                conn.connectTimeout = 10_000
                conn.readTimeout = 30_000
                conn.doOutput = true
                conn.setRequestProperty("Authorization", "Bearer ${apiKey.trim()}")
                conn.setRequestProperty("Content-Type", "application/json")
                conn.outputStream.use { it.write(body) }
                val code = conn.responseCode
                val dt = (System.nanoTime() - t0) / 1e9
                if (code == 200) {
                    val data = JSONObject(conn.inputStream.bufferedReader().readText())
                    return data.getJSONObject("answers") to dt
                }
                val err = conn.errorStream?.bufferedReader()?.readText().orEmpty()
                if (code in listOf(429, 500, 502, 503, 504) && attempt < retries) {
                    Thread.sleep(delay); delay *= 2; continue
                }
                if (code == 401 || code == 403) throw JevError("API key invalid or not permitted (HTTP $code).")
                throw JevError("HTTP $code: ${err.take(300)}")
            } catch (e: IOException) {
                if (attempt == retries) throw JevError("Network error: ${e.message}")
                Thread.sleep(delay); delay *= 2
            } finally {
                conn.disconnect()
            }
        }
        throw JevError("No answer from Jev.")
    }
}
