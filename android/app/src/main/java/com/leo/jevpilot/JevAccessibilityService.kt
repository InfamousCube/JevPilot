package com.leo.jevpilot

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Path
import android.graphics.PixelFormat
import android.graphics.Rect
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.TextUtils
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import android.view.accessibility.AccessibilityWindowInfo
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** One thing Jev could do right now, described as an English sentence. */
data class Opt(
    val desc: String,
    val kind: String,
    val node: AccessibilityNodeInfo? = null,
    val data: String = "",
    val priority: Double = 0.0,
    val mayCommit: Boolean = false,
)

/**
 * The phone side of JevPilot: reads the screen as an accessibility tree, turns it
 * into a list of actions (like desktop_env.py does with UI Automation on the PC)
 * and performs the one Jev picks. Also draws the orange stop pill and the
 * confirmation card as accessibility overlays (no extra permission needed).
 */
class JevAccessibilityService : AccessibilityService() {
    companion object {
        @Volatile var instance: JevAccessibilityService? = null
    }

    private val main = Handler(Looper.getMainLooper())
    private var pill: TextView? = null
    private var apps: List<Pair<String, String>> = emptyList()   // label, package

    override fun onServiceConnected() {
        instance = this
        Thread { apps = loadApps() }.start()
    }

    override fun onUnbind(intent: Intent?): Boolean {
        instance = null
        return super.onUnbind(intent)
    }

    override fun onDestroy() {
        instance = null
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}
    override fun onInterrupt() {}

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun loadApps(): List<Pair<String, String>> {
        val pm = packageManager
        val it = Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER)
        return pm.queryIntentActivities(it, 0)
            .map { it.loadLabel(pm).toString() to it.activityInfo.packageName }
            .filter { it.second != packageName }
            .distinctBy { it.second }
            .sortedBy { it.first.lowercase() }
    }

    private fun appLabel(pkg: String): String =
        apps.firstOrNull { it.second == pkg }?.first ?: try {
            packageManager.getApplicationLabel(packageManager.getApplicationInfo(pkg, 0)).toString()
        } catch (_: Exception) { pkg }

    // ------------------------------------------------------------------ observe

    private fun appRoot(): AccessibilityNodeInfo? {
        val active = rootInActiveWindow
        if (active != null && active.packageName != packageName) return active
        return windows.firstOrNull {
            it.type == AccessibilityWindowInfo.TYPE_APPLICATION && it.root?.packageName != packageName
        }?.root ?: active
    }

    private fun short(s: CharSequence?, max: Int = 60): String {
        val t = s?.toString()?.replace(Regex("\\s+"), " ")?.trim().orEmpty()
        return if (t.length > max) t.take(max - 1) + "…" else t
    }

    private fun ownLabel(n: AccessibilityNodeInfo): String =
        short(n.text).ifEmpty { short(n.contentDescription) }.ifEmpty { short(n.hintText) }

    private fun childText(n: AccessibilityNodeInfo, depth: Int = 0): String {
        if (depth > 3) return ""
        val parts = mutableListOf<String>()
        for (i in 0 until n.childCount) {
            val c = n.getChild(i) ?: continue
            val t = ownLabel(c).ifEmpty { childText(c, depth + 1) }
            if (t.isNotEmpty()) parts.add(t)
            if (parts.size >= 3) break
        }
        return short(parts.joinToString(" · "), 70)
    }

    private fun idTail(n: AccessibilityNodeInfo) =
        n.viewIdResourceName?.substringAfterLast('/')?.replace('_', ' ').orEmpty()

    private fun role(n: AccessibilityNodeInfo): String {
        val cls = n.className?.toString().orEmpty()
        return when {
            n.isCheckable -> if (n.isChecked) "switch (currently ON)" else "switch (currently OFF)"
            cls.contains("Button") && cls.contains("Image") -> "icon button"
            cls.contains("Button") -> "button"
            cls.contains("Image") -> "icon"
            cls.contains("Tab") -> "tab"
            else -> "item"
        }
    }

    fun observe(prompt: String): Pair<JSONObject, List<Opt>> {
        val root = appRoot()
        val pkg = root?.packageName?.toString().orEmpty()
        val screenH = resources.displayMetrics.heightPixels
        val texts = LinkedHashSet<String>()
        val taps = mutableListOf<Triple<String, AccessibilityNodeInfo, Rect>>()
        val fields = mutableListOf<Pair<String, AccessibilityNodeInfo>>()
        val scrolls = mutableListOf<Pair<String, AccessibilityNodeInfo>>()
        var focused: String? = null

        fun walk(n: AccessibilityNodeInfo, depth: Int) {
            if (depth > 40 || !n.isVisibleToUser) return
            val own = ownLabel(n)
            if (own.isNotEmpty() && texts.size < 70) texts.add(own)
            when {
                n.isEditable -> {
                    val label = short(n.hintText).ifEmpty { short(n.contentDescription) }
                        .ifEmpty { idTail(n) }.ifEmpty { "text field" }
                    if (!n.isPassword) fields.add(label to n)
                    if (n.isFocused) focused = label
                }
                n.isClickable -> {
                    val label = own.ifEmpty { childText(n) }.ifEmpty { idTail(n) }
                    if (label.isNotEmpty()) {
                        val r = Rect(); n.getBoundsInScreen(r)
                        if (r.width() > 0 && r.height() > 0) taps.add(Triple("${role(n)} '$label'", n, r))
                    }
                }
            }
            if (n.isScrollable) {
                val label = own.ifEmpty { idTail(n) }.ifEmpty { "the list" }
                scrolls.add(label to n)
            }
            for (i in 0 until n.childCount) n.getChild(i)?.let { walk(it, depth + 1) }
        }
        if (root != null && pkg != packageName) walk(root, 0)

        val opts = mutableListOf<Opt>()
        val counts = taps.groupingBy { it.first }.eachCount()
        for ((what, node, r) in taps) {
            val where = if ((counts[what] ?: 0) > 1) {
                val y = r.centerY().toFloat() / screenH
                " near the " + (if (y < 0.33) "top" else if (y < 0.66) "middle" else "bottom") + " of the screen"
            } else ""
            opts.add(Opt("Tap the $what$where", "tap", node, priority = 2.0, mayCommit = true))
        }
        val cands = TextCands.candidates(prompt, 8)
        for ((label, node) in fields.take(4)) for (c in cands) {
            opts.add(Opt("Type \"$c\" into the text field '$label'", "type", node, c, priority = 1.5))
        }
        val keyboard = windows.any { it.type == AccessibilityWindowInfo.TYPE_INPUT_METHOD }
        val focusNode = root?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        if (focusNode != null && focusNode.isEditable) {
            opts.add(Opt("Press Enter / Search / Send on the keyboard in the field '${focused ?: "text field"}'",
                "ime", focusNode, priority = 1.5, mayCommit = true))
        }
        for ((label, node) in scrolls.take(4)) {
            opts.add(Opt("Scroll down in '$label' to see more", "scroll", node, "down", 1.0))
            opts.add(Opt("Scroll up in '$label'", "scroll", node, "up", 0.5))
        }
        opts.add(Opt("Press the Back button", "global", data = "back", priority = 3.0))
        opts.add(Opt("Go to the home screen", "global", data = "home", priority = 3.0))
        opts.add(Opt("Show the recent apps", "global", data = "recents", priority = 1.0))
        opts.add(Opt("Pull down the notification shade", "global", data = "notifications", priority = 1.0))
        opts.add(Opt("Wait a moment for the screen to finish loading", "wait", priority = 2.0))
        for (u in TextCands.urls(prompt)) opts.add(Opt("Open the website $u in the browser", "url", data = u, priority = 3.0))
        for ((label, p) in apps) opts.add(Opt("Open the app '$label'", "app", data = p))

        val state = JSONObject().put("phone", JSONObject()
            .put("open_app", if (pkg.isEmpty()) "unknown" else appLabel(pkg))
            .put("screen_text", JSONArray(texts.toList()))
            .put("focused_text_field", focused ?: "none")
            .put("keyboard_visible", keyboard))
        return state to opts
    }

    // ------------------------------------------------------------------ act

    fun execute(o: Opt): String {
        val r = when (o.kind) {
            "tap" -> tap(o.node!!)
            "type" -> {
                val n = o.node!!
                n.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                n.performAction(AccessibilityNodeInfo.ACTION_FOCUS)
                val args = Bundle().apply {
                    putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, o.data)
                }
                if (n.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) "typed" else "could not type"
            }
            "ime" -> if (o.node!!.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id))
                "pressed enter" else "enter not supported here"
            "scroll" -> if (o.node!!.performAction(
                    if (o.data == "down") AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
                    else AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD)) "scrolled" else "cannot scroll further"
            "global" -> {
                performGlobalAction(when (o.data) {
                    "back" -> GLOBAL_ACTION_BACK
                    "home" -> GLOBAL_ACTION_HOME
                    "recents" -> GLOBAL_ACTION_RECENTS
                    else -> GLOBAL_ACTION_NOTIFICATIONS
                })
                "done"
            }
            "app" -> {
                val i = packageManager.getLaunchIntentForPackage(o.data)
                if (i == null) "app cannot be opened" else {
                    startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)); "opened"
                }
            }
            "url" -> {
                val u = if (o.data.contains("://")) o.data else "https://${o.data}"
                startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(u)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                "opened"
            }
            "wait" -> { Thread.sleep(1500); "waited" }
            else -> "unknown action"
        }
        Thread.sleep(if (o.kind == "app" || o.kind == "url") 1800 else 900)
        return r
    }

    private fun tap(node: AccessibilityNodeInfo): String {
        var n: AccessibilityNodeInfo? = node
        while (n != null) {
            if (n.isClickable && n.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return "tapped"
            n = n.parent
        }
        val r = Rect(); node.getBoundsInScreen(r)
        val path = Path().apply { moveTo(r.exactCenterX(), r.exactCenterY()) }
        val g = GestureDescription.Builder().addStroke(GestureDescription.StrokeDescription(path, 0, 60)).build()
        return if (dispatchGesture(g, null, null)) "tapped (gesture)" else "tap failed"
    }

    fun goHome() = performGlobalAction(GLOBAL_ACTION_HOME)

    // ------------------------------------------------------------------ overlays

    private fun overlayParams(gravity: Int, touchable: Boolean = true) = WindowManager.LayoutParams(
        WindowManager.LayoutParams.WRAP_CONTENT, WindowManager.LayoutParams.WRAP_CONTENT,
        WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
        WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL or
            (if (touchable) 0 else WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE),
        PixelFormat.TRANSLUCENT,
    ).apply { this.gravity = gravity }

    fun showPill(text: String) = main.post {
        val wm = getSystemService(WINDOW_SERVICE) as WindowManager
        val p = pill ?: TextView(this).also { tv ->
            tv.setTextColor(Pal.TEXT)
            tv.textSize = 13f
            tv.maxLines = 1
            tv.ellipsize = TextUtils.TruncateAt.END
            tv.maxWidth = (resources.displayMetrics.widthPixels * 0.9).toInt()
            tv.setPadding(dp(16), dp(8), dp(16), dp(8))
            tv.background = GradientDrawable().apply { setColor(Pal.ACCENT); cornerRadius = dp(20).toFloat() }
            tv.elevation = dp(6).toFloat()
            tv.setOnClickListener { PhoneAgent.requestStop() }
            wm.addView(tv, overlayParams(Gravity.TOP or Gravity.CENTER_HORIZONTAL).apply { y = dp(36) })
            pill = tv
        }
        p.text = text
    }

    fun hidePill(delayMs: Long = 0) = main.postDelayed({
        pill?.let { (getSystemService(WINDOW_SERVICE) as WindowManager).removeView(it) }
        pill = null
    }, delayMs)

    /** Blocks the calling (agent) thread until the user answers on the overlay card. */
    fun confirm(question: String, stop: () -> Boolean): Boolean {
        val latch = CountDownLatch(1)
        var answer = false
        var card: View? = null
        val wm = getSystemService(WINDOW_SERVICE) as WindowManager
        main.post {
            val box = LinearLayout(this).apply {
                orientation = LinearLayout.VERTICAL
                setPadding(dp(20), dp(18), dp(20), dp(14))
                background = GradientDrawable().apply {
                    setColor(Pal.INPUT); cornerRadius = dp(16).toFloat(); setStroke(dp(1), Pal.ACCENT_DIM)
                }
                elevation = dp(10).toFloat()
            }
            box.addView(TextView(this).apply {
                text = "✻ JevPilot – Bestätigung"; setTextColor(Pal.ACCENT); textSize = 13f
            })
            box.addView(TextView(this).apply {
                text = question; setTextColor(Pal.TEXT); textSize = 15f; setPadding(0, dp(8), 0, dp(12))
            })
            val row = LinearLayout(this).apply { gravity = Gravity.END }
            fun btn(label: String, filled: Boolean, yes: Boolean) = TextView(this).apply {
                text = label; textSize = 14f
                setTextColor(if (filled) 0xFFFFFFFF.toInt() else Pal.MUTED)
                setPadding(dp(18), dp(10), dp(18), dp(10))
                background = GradientDrawable().apply {
                    cornerRadius = dp(10).toFloat()
                    if (filled) setColor(Pal.ACCENT) else setStroke(dp(1), Pal.LINE)
                }
                setOnClickListener { answer = yes; latch.countDown() }
            }
            row.addView(btn("Ablehnen", false, false))
            row.addView(View(this), LinearLayout.LayoutParams(dp(10), 1))
            row.addView(btn("Erlauben", true, true))
            box.addView(row)
            val params = overlayParams(Gravity.CENTER).apply {
                width = (resources.displayMetrics.widthPixels * 0.88).toInt()
            }
            wm.addView(box, params)
            card = box
        }
        while (!latch.await(200, TimeUnit.MILLISECONDS)) if (stop()) break
        main.post { card?.let { wm.removeView(it) } }
        return answer
    }
}
