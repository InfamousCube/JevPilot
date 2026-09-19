package com.leo.jevpilot

import android.content.Context
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Claude Code palette, same values as app.py on the PC. */
object Pal {
    const val BG = 0xFF262624.toInt()
    const val SIDEBAR = 0xFF1F1E1D.toInt()
    const val INPUT = 0xFF30302E.toInt()
    const val LINE = 0xFF3E3D39.toInt()
    const val ACCENT = 0xFFD97757.toInt()
    const val ACCENT_HI = 0xFFC6613F.toInt()
    const val ACCENT_DIM = 0xFF8A4A35.toInt()
    const val TEXT = 0xFFFAF9F5.toInt()
    const val MUTED = 0xFFA6A39B.toInt()
    const val FAINT = 0xFF6F6C64.toInt()
    const val GREEN = 0xFF7FB87A.toInt()
    const val RED = 0xFFE0715F.toInt()
    const val YELLOW = 0xFFE0B25F.toInt()
    const val USER = 0xFFC9C5BB.toInt()

    fun tag(tag: String) = when (tag) {
        "meta" -> MUTED; "ok" -> GREEN; "warn" -> YELLOW; "err" -> RED; "user" -> USER; else -> TEXT
    }
}

data class LogLine(val text: String, val tag: String)

/** Log lines for one tab; changes are delivered on the main thread. */
class LogModel {
    private val main = Handler(Looper.getMainLooper())
    val lines = ArrayList<LogLine>()
    var onChange: (() -> Unit)? = null

    fun add(text: String, tag: String = "act") = main.post {
        lines.add(LogLine(text, tag))
        if (lines.size > 1500) lines.subList(0, 500).clear()
        onChange?.invoke()
    }

    fun addAll(new: List<LogLine>) = main.post {
        lines.addAll(new)
        if (lines.size > 1500) lines.subList(0, lines.size - 1000).clear()
        onChange?.invoke()
    }

    fun replaceAll(new: List<LogLine>) = main.post {
        lines.clear(); lines.addAll(new); onChange?.invoke()
    }
}

/** Settings. A provision.json dropped into filesDir (by adb run-as) is imported once. */
class Prefs(ctx: Context) {
    private val sp = ctx.getSharedPreferences("jevpilot", Context.MODE_PRIVATE)

    init {
        val f = File(ctx.filesDir, "provision.json")
        if (f.isFile) {
            try {
                val j = JSONObject(f.readText())
                sp.edit().apply {
                    j.optString("api_key").takeIf { it.isNotBlank() }?.let { putString("api_key", it) }
                    j.optString("pc_host").takeIf { it.isNotBlank() }?.let { putString("pc_host", it) }
                    j.optString("pc_token").takeIf { it.isNotBlank() }?.let { putString("pc_token", it) }
                }.apply()
            } catch (_: Exception) {
            }
            f.delete()
        }
    }

    var apiKey: String
        get() = sp.getString("api_key", "") ?: ""
        set(v) = sp.edit().putString("api_key", v.trim()).apply()
    var pcHost: String
        get() = sp.getString("pc_host", "") ?: ""
        set(v) = sp.edit().putString("pc_host", v.trim()).apply()
    var pcToken: String
        get() = sp.getString("pc_token", "") ?: ""
        set(v) = sp.edit().putString("pc_token", v.trim()).apply()
    var steps: Int
        get() = sp.getInt("steps", 25)
        set(v) = sp.edit().putInt("steps", v).apply()
    var tab: Int
        get() = sp.getInt("tab", 0)
        set(v) = sp.edit().putInt("tab", v).apply()
}

class PcError(msg: String, val code: Int = 0) : Exception(msg)

/**
 * Talks to jevpilot/remote.py on the PC. Tries the saved Wi-Fi address and
 * 127.0.0.1:8765 (works over USB after `adb reverse tcp:8765 tcp:8765`).
 */
class PcClient(private val prefs: Prefs) {
    @Volatile var activeHost: String? = null

    private fun hosts(): List<String> =
        listOfNotNull(activeHost, prefs.pcHost.takeIf { it.isNotBlank() }, "127.0.0.1:8765").distinct()

    fun request(method: String, path: String, body: JSONObject? = null): ByteArray {
        var last: Exception = PcError("PC nicht erreichbar")
        for (host in hosts()) {
            val h = if (host.contains(":")) host else "$host:8765"
            val conn = URL("http://$h$path").openConnection() as HttpURLConnection
            try {
                conn.requestMethod = method
                conn.connectTimeout = 1500
                conn.readTimeout = 6000
                conn.setRequestProperty("X-JevPilot-Token", prefs.pcToken)
                if (body != null) {
                    conn.doOutput = true
                    conn.setRequestProperty("Content-Type", "application/json")
                    conn.outputStream.use { it.write(body.toString().toByteArray()) }
                }
                val code = conn.responseCode
                activeHost = host
                if (code == 200) return conn.inputStream.use { it.readBytes() }
                val err = conn.errorStream?.bufferedReader()?.readText().orEmpty()
                val msg = try { JSONObject(err).optString("error", "HTTP $code") } catch (_: Exception) { "HTTP $code" }
                throw PcError(msg, code)
            } catch (e: IOException) {
                last = e
                if (activeHost == host) activeHost = null
            } finally {
                conn.disconnect()
            }
        }
        throw PcError("PC nicht erreichbar (${last.message ?: "keine Verbindung"})")
    }

    fun json(method: String, path: String, body: JSONObject? = null) =
        JSONObject(String(request(method, path, body)))
}
