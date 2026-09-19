package com.leo.jevpilot

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.provider.Settings
import android.text.InputType
import android.text.SpannableStringBuilder
import android.text.Spanned
import android.text.style.ForegroundColorSpan
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.ImageView
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.SeekBar
import android.widget.Switch
import android.widget.TextView
import android.widget.Toast
import org.json.JSONObject
import kotlin.concurrent.thread

class MainActivity : Activity() {
    private lateinit var prefs: Prefs
    private lateinit var pc: PcClient
    private val pcLog = LogModel()

    private lateinit var tabs: List<TextView>
    private lateinit var panels: List<View>
    private lateinit var pcStatus: TextView
    private lateinit var modeButtons: List<TextView>
    private lateinit var gamesBox: LinearLayout
    private lateinit var a11yCard: LinearLayout
    private lateinit var pcComposer: Composer
    private lateinit var phoneComposer: Composer

    private var mode = "Auto"
    private var selectedGame: String? = null
    private var gameNames: List<String> = emptyList()
    private val cardCache = HashMap<String, Bitmap>()
    private var pcBusy = false
    private var pcNext = 0
    private var pcHostName: String? = null
    private var shownConfirm = -1
    private var confirmDialog: AlertDialog? = null
    @Volatile private var polling = false

    private fun dp(v: Int) = (v * resources.displayMetrics.density).toInt()

    private fun rounded(fill: Int, radius: Int, stroke: Int = 0, strokeColor: Int = 0) = GradientDrawable().apply {
        setColor(fill); cornerRadius = dp(radius).toFloat()
        if (stroke > 0) setStroke(dp(stroke), strokeColor)
    }

    private fun label(text: String, size: Float, color: Int, bold: Boolean = false) = TextView(this).apply {
        this.text = text; textSize = size; setTextColor(color)
        if (bold) typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
    }

    private fun section(text: String) = label(text.uppercase(), 11f, Pal.FAINT, true).apply {
        letterSpacing = 0.08f; setPadding(dp(4), dp(18), 0, dp(6))
    }

    private fun lp(w: Int = ViewGroup.LayoutParams.MATCH_PARENT, h: Int = ViewGroup.LayoutParams.WRAP_CONTENT, weight: Float = 0f) =
        LinearLayout.LayoutParams(w, h, weight)

    /** Segmented control like CTkSegmentedButton: charcoal track, terracotta selection. */
    private fun segmented(values: List<String>, onPick: (Int) -> Unit): Pair<LinearLayout, List<TextView>> {
        val track = LinearLayout(this).apply {
            background = rounded(Pal.INPUT, 10); setPadding(dp(3), dp(3), dp(3), dp(3))
        }
        val items = values.mapIndexed { i, v ->
            label(v, 13f, Pal.TEXT, true).apply {
                gravity = Gravity.CENTER; setPadding(0, dp(8), 0, dp(8))
                setOnClickListener { onPick(i) }
            }.also { track.addView(it, lp(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)) }
        }
        return track to items
    }

    private fun paintSegments(items: List<TextView>, selected: Int) = items.forEachIndexed { i, t ->
        t.background = if (i == selected) rounded(Pal.ACCENT, 8) else null
        t.setTextColor(if (i == selected) 0xFFFFFFFF.toInt() else Pal.MUTED)
    }

    // ------------------------------------------------------------------ composer

    /** Prompt box + start/stop + log, one per tab. */
    inner class Composer(val log: LogModel, hint: String, val onStart: (String, Int, Boolean) -> Unit, val onStop: () -> Unit) {
        val target = label(hint, 13f, Pal.MUTED).apply { setPadding(dp(4), dp(16), 0, dp(6)) }
        val input = EditText(this@MainActivity)
        val risky = Switch(this@MainActivity)
        val start = label("Start  ↵", 14f, 0xFFFFFFFF.toInt(), true)
        val stop = label("Stop", 14f, Pal.MUTED, true)
        val logText = TextView(this@MainActivity)
        val logScroll = ScrollView(this@MainActivity)
        val stepsLbl = label("", 12f, Pal.MUTED)
        var steps = prefs.steps
        val box = LinearLayout(this@MainActivity)

        fun build(parent: LinearLayout) {
            parent.addView(target)
            box.orientation = LinearLayout.VERTICAL
            box.background = rounded(Pal.INPUT, 14, 1, Pal.LINE)
            box.setPadding(dp(10), dp(6), dp(12), dp(10))
            val row = LinearLayout(this@MainActivity)
            row.addView(label("›", 24f, Pal.ACCENT, true).apply { setPadding(dp(4), 0, dp(6), 0) })
            input.apply {
                background = null; setTextColor(Pal.TEXT); setHintTextColor(Pal.FAINT); textSize = 15f
                this.hint = "Aufgabe für Jev …"
                minLines = 2; maxLines = 6; gravity = Gravity.TOP
                inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
                setOnFocusChangeListener { _, f -> box.background = rounded(Pal.INPUT, 14, 1, if (f) Pal.ACCENT_DIM else Pal.LINE) }
            }
            row.addView(input, lp(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            box.addView(row)

            risky.apply {
                text = "Vor Kaufen/Senden/Löschen fragen"; textSize = 13f; setTextColor(Pal.MUTED)
                isChecked = true
                thumbTintList = android.content.res.ColorStateList(
                    arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()), intArrayOf(Pal.TEXT, Pal.MUTED))
                trackTintList = android.content.res.ColorStateList(
                    arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()), intArrayOf(Pal.ACCENT, Pal.LINE))
                setPadding(dp(4), dp(6), 0, dp(2))
            }
            box.addView(risky)

            val foot = LinearLayout(this@MainActivity).apply { gravity = Gravity.CENTER_VERTICAL }
            val seek = SeekBar(this@MainActivity).apply {
                max = 15; progress = ((steps - 5) / 5).coerceIn(0, 15)
                progressTintList = android.content.res.ColorStateList.valueOf(Pal.ACCENT)
                thumbTintList = android.content.res.ColorStateList.valueOf(Pal.TEXT)
                progressBackgroundTintList = android.content.res.ColorStateList.valueOf(Pal.LINE)
                setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                    override fun onProgressChanged(s: SeekBar?, p: Int, u: Boolean) {
                        steps = 5 + p * 5; prefs.steps = steps; stepsLbl.text = "$steps Schritte"
                    }
                    override fun onStartTrackingTouch(s: SeekBar?) {}
                    override fun onStopTrackingTouch(s: SeekBar?) {}
                })
            }
            stepsLbl.text = "$steps Schritte"
            foot.addView(stepsLbl, lp(dp(78)))
            foot.addView(seek, lp(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            stop.apply {
                gravity = Gravity.CENTER; setPadding(dp(16), dp(9), dp(16), dp(9))
                setOnClickListener { onStop() }
            }
            start.apply {
                gravity = Gravity.CENTER; setPadding(dp(18), dp(9), dp(18), dp(9))
                setOnClickListener {
                    onStart(input.text.toString().trim(), steps, risky.isChecked)
                }
            }
            foot.addView(stop, lp(ViewGroup.LayoutParams.WRAP_CONTENT).apply { marginStart = dp(6) })
            foot.addView(start, lp(ViewGroup.LayoutParams.WRAP_CONTENT).apply { marginStart = dp(8) })
            box.addView(foot)
            parent.addView(box)

            logText.apply {
                typeface = Typeface.MONOSPACE; textSize = 12f; setTextColor(Pal.TEXT)
                setLineSpacing(dp(2).toFloat(), 1f); setTextIsSelectable(true)
                setPadding(dp(4), dp(12), dp(4), dp(24))
            }
            logScroll.addView(logText)
            logScroll.isFillViewport = true
            parent.addView(logScroll, lp(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
            log.onChange = { renderLog() }
            renderLog()
            setBusy(false)
        }

        fun renderLog() {
            val sb = SpannableStringBuilder()
            fun put(s: String, color: Int) {
                val a = sb.length; sb.append(s)
                sb.setSpan(ForegroundColorSpan(color), a, sb.length, Spanned.SPAN_EXCLUSIVE_EXCLUSIVE)
            }
            for (l in log.lines.takeLast(400)) {
                val body = l.text.trim('\n')
                if (l.text.startsWith("\n")) sb.append("\n")
                when (l.tag) {
                    "act" -> { put("⏺ ", Pal.ACCENT); put(body + "\n", Pal.TEXT) }
                    "meta" -> put("  ⎿  " + body.trim() + "\n", Pal.MUTED)
                    else -> put(body + "\n", Pal.tag(l.tag))
                }
            }
            logText.text = sb
            logScroll.post { logScroll.fullScroll(View.FOCUS_DOWN) }
        }

        fun setBusy(busy: Boolean) {
            start.text = if (busy) "Läuft …" else "Start  ↵"
            start.background = rounded(if (busy) Pal.ACCENT_DIM else Pal.ACCENT, 9)
            start.isEnabled = !busy
            stop.isEnabled = busy
            stop.setTextColor(if (busy) Pal.TEXT else Pal.FAINT)
            stop.background = rounded(0, 9, 1, if (busy) Pal.ACCENT else Pal.LINE)
        }
    }

    // ------------------------------------------------------------------ lifecycle

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        prefs = Prefs(this)
        pc = PcClient(prefs)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Pal.BG)
            setPadding(dp(16), dp(14), dp(16), 0)
        }
        val head = LinearLayout(this).apply { gravity = Gravity.CENTER_VERTICAL }
        head.addView(label("✻", 24f, Pal.ACCENT).apply { setPadding(0, 0, dp(8), 0) })
        head.addView(label("JevPilot", 24f, Pal.TEXT).apply { typeface = Typeface.SERIF })
        head.addView(View(this), lp(0, 1, 1f))
        head.addView(label("⚙", 22f, Pal.MUTED).apply {
            setPadding(dp(12), dp(4), dp(4), dp(4)); setOnClickListener { openSettings() }
        })
        root.addView(head)
        root.addView(label("Computer Use mit TypeSafe Jev", 12f, Pal.MUTED).apply { setPadding(dp(2), 0, 0, dp(12)) })

        val (tabTrack, tabItems) = segmented(listOf("PC steuern", "Handy steuern")) { selectTab(it) }
        tabs = tabItems
        root.addView(tabTrack)

        // --- PC panel
        val pcPanel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        pcStatus = label("", 13f, Pal.MUTED).apply { setPadding(dp(4), dp(12), 0, 0) }
        pcPanel.addView(pcStatus)
        pcPanel.addView(section("Modus"))
        val (modeTrack, modeItems) = segmented(listOf("Auto", "Browser", "PC")) {
            mode = listOf("Auto", "Browser", "PC")[it]; selectGame(null); paintSegments(modeButtons, it)
        }
        modeButtons = modeItems
        paintSegments(modeButtons, 0)
        pcPanel.addView(modeTrack)
        pcPanel.addView(section("Spiele"))
        gamesBox = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        pcPanel.addView(gamesBox)
        pcComposer = Composer(pcLog, "", ::startPc, ::stopPc)
        pcComposer.build(pcPanel)
        selectGame(null)

        // --- Phone panel
        val phonePanel = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        a11yCard = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            background = rounded(Pal.SIDEBAR, 12, 1, Pal.LINE)
            setPadding(dp(14), dp(12), dp(14), dp(12))
            addView(label("Bedienungshilfe ist aus", 14f, Pal.YELLOW, true))
            addView(label("Damit Jev dein Handy bedienen kann: Einstellungen → Bedienungshilfen → " +
                "Installierte Apps → JevPilot → einschalten.", 13f, Pal.MUTED).apply { setPadding(0, dp(4), 0, dp(10)) })
            addView(label("Aktivieren", 14f, 0xFFFFFFFF.toInt(), true).apply {
                background = rounded(Pal.ACCENT, 9); setPadding(dp(16), dp(8), dp(16), dp(8))
                setOnClickListener { startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)) }
            }, lp(ViewGroup.LayoutParams.WRAP_CONTENT))
        }
        phonePanel.addView(a11yCard, lp().apply { topMargin = dp(12) })
        phoneComposer = Composer(PhoneAgent.log,
            "Was soll Jev auf dem Handy tun?  z. B.  öffne youtube und suche \"lofi hip hop\"",
            ::startPhone, { PhoneAgent.requestStop() })
        phoneComposer.build(phonePanel)
        PhoneAgent.onBusyChange = { phoneComposer.setBusy(it) }

        val stack = FrameLayout(this)
        stack.addView(pcPanel); stack.addView(phonePanel)
        panels = listOf(pcPanel, phonePanel)
        root.addView(stack, lp(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f))
        // Android 15+ always draws edge-to-edge: keep content clear of status bar, nav bar and keyboard.
        applyInsets(root)
        setContentView(if (prefs.apiKey.isBlank()) welcomeView(root) else root)
        selectTab(prefs.tab)

        if (pcLog.lines.isEmpty()) pcLog.add("Verbinde mit JevPilot am PC …", "meta")
        if (PhoneAgent.log.lines.isEmpty()) PhoneAgent.log.add("Bereit. Jev bedient dieses Handy, oben erscheint eine orange Leiste – antippen stoppt.", "ok")
    }

    private fun applyInsets(v: View) = v.setOnApplyWindowInsetsListener { view, ins ->
        val b = ins.getInsets(android.view.WindowInsets.Type.systemBars() or android.view.WindowInsets.Type.ime())
        view.setPadding(dp(16), b.top + dp(10), dp(16), b.bottom)
        ins
    }

    /** First start: JevPilot only works with the user's own TypeSafe key, stored on this phone. */
    private fun welcomeView(main: View): View {
        val box = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setBackgroundColor(Pal.BG)
        }
        val inner = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(8), 0, dp(8), 0) }
        inner.addView(label("✻", 48f, Pal.ACCENT))
        inner.addView(label("Willkommen bei JevPilot", 26f, Pal.TEXT).apply {
            typeface = Typeface.SERIF; setPadding(0, dp(4), 0, dp(10))
        })
        inner.addView(label("JevPilot lässt TypeSafe Jev dein Handy bedienen und schickt Aufgaben an " +
            "JevPilot auf deinem PC. Dafür brauchst du deinen eigenen TypeSafe API-Key.", 15f, Pal.MUTED))
        val key = EditText(this).apply {
            hint = "API-Key einfügen"; setHintTextColor(Pal.FAINT); setTextColor(Pal.TEXT); textSize = 15f
            background = rounded(Pal.INPUT, 12, 1, Pal.LINE); setPadding(dp(14), dp(12), dp(14), dp(12))
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            isSingleLine = true
        }
        inner.addView(key, lp().apply { topMargin = dp(22) })
        inner.addView(label("Wird nur auf diesem Handy gespeichert.", 12f, Pal.FAINT).apply { setPadding(dp(4), dp(6), 0, 0) })
        val status = label("", 13f, Pal.MUTED).apply { setPadding(dp(4), dp(10), 0, 0) }
        inner.addView(status)
        val go = label("Prüfen & loslegen", 15f, 0xFFFFFFFF.toInt(), true).apply {
            gravity = Gravity.CENTER; background = rounded(Pal.ACCENT, 10)
            setPadding(dp(18), dp(12), dp(18), dp(12))
        }
        go.setOnClickListener {
            val k = key.text.toString().trim()
            if (k.isEmpty()) { status.text = "Bitte einen Key einfügen."; status.setTextColor(Pal.YELLOW); return@setOnClickListener }
            status.text = "Teste Key …"; status.setTextColor(Pal.MUTED); go.isEnabled = false
            thread {
                val err = try {
                    Jev(k).ask("ping", JSONObject().put("t", Jev.noul("This is a test"))); null
                } catch (e: Exception) { e.message ?: "Fehler" }
                runOnUiThread {
                    go.isEnabled = true
                    if (err != null) { status.text = "✗ $err"; status.setTextColor(Pal.RED) }
                    else {
                        prefs.apiKey = k
                        setContentView(main)
                        main.requestApplyInsets()
                        toast("✓ Key gespeichert. Mit dem PC verbinden: ⚙")
                    }
                }
            }
        }
        inner.addView(go, lp().apply { topMargin = dp(16) })
        box.addView(inner)
        applyInsets(box)
        return box
    }

    override fun onResume() {
        super.onResume()
        a11yCard.visibility = if (JevAccessibilityService.instance == null) View.VISIBLE else View.GONE
        phoneComposer.setBusy(PhoneAgent.busy)
        startPolling()
    }

    override fun onPause() {
        polling = false
        super.onPause()
    }

    private fun selectTab(i: Int) {
        prefs.tab = i
        paintSegments(tabs, i)
        panels.forEachIndexed { j, p -> p.visibility = if (i == j) View.VISIBLE else View.GONE }
    }

    // ------------------------------------------------------------------ PC

    private fun selectGame(name: String?) {
        selectedGame = name
        pcComposer.target.text = if (name != null) "Spiel: $name  ·  Ziel oder Spielstil (optional), dann Start"
        else "Was soll Jev am PC tun?  z. B.  öffne youtube und suche \"lofi hip hop\""
        pcComposer.target.setTextColor(if (name != null) Pal.ACCENT else Pal.MUTED)
        renderGames()
    }

    private fun renderGames() {
        gamesBox.removeAllViews()
        gameNames.forEachIndexed { i, name ->
            val state = if (name == selectedGame) "selected" else "idle"
            val img = ImageView(this).apply {
                scaleType = ImageView.ScaleType.FIT_XY
                cardCache["$name/$state"]?.let { setImageBitmap(it) } ?: run {
                    background = rounded(Pal.SIDEBAR, 9, 1, Pal.LINE); loadCard(i, name)
                }
                setOnClickListener { selectGame(if (selectedGame == name) null else name) }
            }
            gamesBox.addView(img, lp(ViewGroup.LayoutParams.MATCH_PARENT, dp(58)).apply { bottomMargin = dp(6) })
        }
        gamesBox.addView(moreGamesCard())
    }

    /** Last card of the library: new games come from a coding agent, via a ready-made prompt. */
    private fun moreGamesCard() = LinearLayout(this).apply {
        gravity = Gravity.CENTER_VERTICAL
        background = rounded(0, 9, 1, Pal.LINE)
        setPadding(dp(14), dp(10), dp(10), dp(10))
        val text = LinearLayout(this@MainActivity).apply { orientation = LinearLayout.VERTICAL }
        text.addView(label("+  Mehr Spiele", 14f, Pal.TEXT, true))
        text.addView(label("Frag Claude Code oder Codex – Prompt kopieren, Spielnamen eintragen.", 12f, Pal.MUTED))
        addView(text, lp(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
        addView(label("Prompt\nkopieren", 12f, Pal.TEXT, true).apply {
            gravity = Gravity.CENTER
            background = rounded(Pal.INPUT, 8, 1, Pal.ACCENT_DIM)
            setPadding(dp(12), dp(6), dp(12), dp(6))
            setOnClickListener {
                val cm = getSystemService(CLIPBOARD_SERVICE) as android.content.ClipboardManager
                cm.setPrimaryClip(android.content.ClipData.newPlainText("JevPilot-Spiele-Prompt", adapterPrompt()))
                toast("Prompt kopiert – in Claude Code oder Codex einfügen und den Spielnamen eintragen.")
            }
        }, lp(ViewGroup.LayoutParams.WRAP_CONTENT).apply { marginStart = dp(10) })
    }

    private fun adapterPrompt() = """Ich nutze JevPilot ($REPO_URL) und will ein neues Spiel.
Bau mir einen Spiel-Adapter für: <SPIELNAME HIER EINTRAGEN>

So funktioniert JevPilot:
- Adapter sind .py-Dateien im Ordner "games" neben JevPilot.exe (Standard: %LOCALAPPDATA%\Programs\JevPilot\games). Sie werden beim Start geladen, die Exe muss nicht neu gebaut werden.
- Vorlagen im Repo: jevpilot/games.py (Klasse GameAdapter, Doku oben in der Datei) und games/rounds.py.
- Jev (TypeSafe System One) sieht keine Bilder und schreibt keinen Text. Er beantwortet nur Choice (max. 255 Optionen), Score und Noul (ja/nein). Der Adapter muss den Spielzustand als Text/JSON liefern und jeden möglichen Zug als kurzen englischen Satz anbieten.
- Hat das Spiel keinen lesbaren Zustand, bau eine Brücke: z. B. einen BepInEx-Mod wie ROUNDS-Bridge/JevBridge, eine Speicherdatei, eine Web-API oder Bildschirm-Auslese.
- Leg ein breites Titelbild als games/<dateiname>.jpg dazu (wird in der Bibliothek rechts abgedunkelt).

Teste den Adapter am Ende und sag mir, wie ich ihn in JevPilot starte."""

    companion object {
        /** Same link as REPO_URL in jevpilot/games.py on the PC. */
        const val REPO_URL = "https://github.com/InfamousCube/JevPilot"
    }

    private fun loadCard(i: Int, name: String) = thread {
        val w = (resources.displayMetrics.widthPixels / resources.displayMetrics.density).toInt() - 32
        for (st in listOf("idle", "selected")) {
            try {
                val bytes = pc.request("GET", "/api/card?i=$i&w=$w&h=58&state=$st")
                BitmapFactory.decodeByteArray(bytes, 0, bytes.size)?.let { cardCache["$name/$st"] = it }
            } catch (_: Exception) { return@thread }
        }
        runOnUiThread { renderGames() }
    }

    private fun startPc(prompt: String, steps: Int, risky: Boolean) {
        if (selectedGame == null && prompt.isEmpty()) return toast("Erst eine Aufgabe eingeben.")
        val body = JSONObject().put("prompt", prompt).put("mode", mode).put("steps", steps)
            .put("risky", risky).put("game", selectedGame ?: JSONObject.NULL)
        thread {
            try { pc.json("POST", "/api/run", body); runOnUiThread { pcComposer.input.setText("") } }
            catch (e: Exception) { runOnUiThread { toast(e.message ?: "Fehler") } }
        }
    }

    private fun stopPc() = thread { try { pc.json("POST", "/api/stop") } catch (_: Exception) {} }

    private fun startPolling() {
        if (polling) return
        polling = true
        thread(name = "pc-poll") {
            var failures = 0
            while (polling) {
                try {
                    val s = pc.json("GET", "/api/status?since=$pcNext")
                    failures = 0
                    runOnUiThread { applyStatus(s) }
                    Thread.sleep(if (pcBusy) 500 else 1200)
                } catch (e: Exception) {
                    failures++
                    val msg = if (e is PcError && e.code == 401) "✗ Falscher Kopplungscode (⚙)"
                    else "○ PC nicht erreichbar – JevPilot am PC offen? Gleiches WLAN oder USB?"
                    runOnUiThread { pcStatus.text = msg; pcStatus.setTextColor(if (failures > 1) Pal.RED else Pal.MUTED) }
                    Thread.sleep(2000)
                }
            }
        }
    }

    private fun applyStatus(s: JSONObject) {
        val host = s.optString("pc")
        if (pcHostName != host) { pcHostName = host; if (pcNext == 0) pcLog.replaceAll(emptyList()) }
        pcStatus.text = "● Verbunden mit $host" + if (pc.activeHost?.startsWith("127.") == true) " (USB)" else ""
        pcStatus.setTextColor(Pal.GREEN)
        val lines = s.optJSONArray("lines")
        if (lines != null && lines.length() > 0) pcLog.addAll((0 until lines.length()).map {
            val l = lines.getJSONArray(it); LogLine(l.getString(1), l.getString(2))
        })
        pcNext = s.optInt("next", pcNext)
        pcBusy = s.optBoolean("busy")
        pcComposer.setBusy(pcBusy)
        val games = s.optJSONArray("games")
        val names = (0 until (games?.length() ?: 0)).map { games!!.getJSONObject(it).getString("name") }
        if (names != gameNames) { gameNames = names; cardCache.clear(); renderGames() }
        val c = s.optJSONObject("confirm")
        if (c != null && c.getInt("id") != shownConfirm) {
            shownConfirm = c.getInt("id")
            showPcConfirm(shownConfirm, c.getString("text"))
        } else if (c == null && confirmDialog?.isShowing == true) {
            confirmDialog?.dismiss()
        }
    }

    private fun showPcConfirm(id: Int, text: String) {
        fun answer(yes: Boolean) = thread {
            try { pc.json("POST", "/api/confirm", JSONObject().put("id", id).put("yes", yes)) } catch (_: Exception) {}
        }
        confirmDialog = AlertDialog.Builder(this, R.style.JevDialog)
            .setTitle("✻ Am PC bestätigen")
            .setMessage(text)
            .setPositiveButton("Erlauben") { _, _ -> answer(true) }
            .setNegativeButton("Ablehnen") { _, _ -> answer(false) }
            .setCancelable(false)
            .create().also { styleDialog(it); it.show() }
    }

    // ------------------------------------------------------------------ phone

    private fun startPhone(prompt: String, steps: Int, risky: Boolean) {
        val err = PhoneAgent.start(prefs.apiKey, prompt, steps, risky)
        if (err != null) {
            toast(err)
            if (JevAccessibilityService.instance == null) a11yCard.visibility = View.VISIBLE
        } else phoneComposer.input.setText("")
    }

    // ------------------------------------------------------------------ settings

    private fun openSettings() {
        val box = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(dp(22), dp(8), dp(22), 0) }
        fun field(title: String, value: String, secret: Boolean, hint: String): EditText {
            box.addView(label(title, 12f, Pal.MUTED).apply { setPadding(0, dp(12), 0, dp(4)) })
            return EditText(this).apply {
                setText(value); this.hint = hint; setHintTextColor(Pal.FAINT); setTextColor(Pal.TEXT); textSize = 14f
                background = rounded(Pal.BG, 9, 1, Pal.LINE); setPadding(dp(12), dp(10), dp(12), dp(10))
                inputType = if (secret) InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
                else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
                isSingleLine = true
            }.also { box.addView(it) }
        }
        val key = field("TypeSafe API-Key (für Handy steuern)", prefs.apiKey, true, "apikey_…")
        val host = field("PC-Adresse", prefs.pcHost, false, "192.168.x.x:8765")
        val token = field("Kopplungscode", prefs.pcToken, false, "steht am PC unter ⚙ Einstellungen")
        box.addView(label("Über USB klappt es auch ohne WLAN (adb reverse). Alles bleibt nur auf diesem Handy gespeichert.",
            12f, Pal.FAINT).apply { setPadding(0, dp(10), 0, dp(4)) })
        AlertDialog.Builder(this, R.style.JevDialog)
            .setTitle("Einstellungen")
            .setView(box)
            .setPositiveButton("Speichern") { _, _ ->
                prefs.apiKey = key.text.toString(); prefs.pcHost = host.text.toString(); prefs.pcToken = token.text.toString()
                pc.activeHost = null; pcNext = 0; pcHostName = null
            }
            .setNegativeButton("Abbrechen", null)
            .create().also { styleDialog(it); it.show() }
    }

    private fun styleDialog(d: AlertDialog) {
        d.window?.setBackgroundDrawable(rounded(Pal.INPUT, 16, 1, Pal.LINE))
        d.setOnShowListener {
            d.getButton(AlertDialog.BUTTON_POSITIVE)?.setTextColor(Pal.ACCENT)
            d.getButton(AlertDialog.BUTTON_NEGATIVE)?.setTextColor(Pal.MUTED)
            val titleId = resources.getIdentifier("alertTitle", "id", "android")
            d.findViewById<TextView>(titleId)?.setTextColor(Pal.TEXT)
            d.findViewById<TextView>(android.R.id.message)?.setTextColor(Pal.TEXT)
        }
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()
}
