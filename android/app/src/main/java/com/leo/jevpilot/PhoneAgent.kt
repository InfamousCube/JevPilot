package com.leo.jevpilot

import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.concurrent.thread

/**
 * Decide/act loop for the phone (port of jevpilot/agent.py). Each step the
 * accessibility service lists every possible action as an English sentence,
 * Jev picks one and says whether the task is done. Risky taps need a yes on
 * the overlay card first.
 */
object PhoneAgent {
    val log = LogModel()
    @Volatile var busy = false
        private set
    private val stop = AtomicBoolean(false)
    var onBusyChange: ((Boolean) -> Unit)? = null

    private val RISKY_WORDS = Regex(
        "\\b(buy|kaufen|kauf|bestell\\w*|order|pay|bezahl\\w*|zahlungspflichtig|checkout|kasse|" +
            "send|senden|absenden|abschicken|post|posten|veröffentlich\\w*|publish|tweet|" +
            "delete|löschen|lösch\\w*|entfernen|remove|uninstall|deinstall\\w*|" +
            "submit|confirm|bestätigen|abonnieren|subscribe|überweis\\w*|transfer|format\\w*|call|anrufen)\\b",
        RegexOption.IGNORE_CASE)

    private const val DECIDE_INSTR =
        "You control an Android phone for the user. Pick the single next action that best moves the " +
            "user's task forward from the current screen. Use the history to avoid repeating actions " +
            "that did not help. To start an app, prefer 'Open the app'. If a cookie or permission " +
            "dialog blocks the screen, prefer rejecting optional cookies. Pick 'Finish' only when the " +
            "task is completely done."
    private const val DONE_INSTR =
        "Given the task, the current phone screen and the history of actions, the user's task is " +
            "already completely finished and nothing else needs to be done."
    private const val RISK_INSTR =
        "Doing the proposed action would buy or pay for something, send a message or email, " +
            "post or publish something publicly, start a phone call, delete data, or change account " +
            "or security settings."

    fun requestStop() = stop.set(true)

    private fun setBusy(b: Boolean) {
        busy = b
        android.os.Handler(android.os.Looper.getMainLooper()).post { onBusyChange?.invoke(b) }
    }

    /** Returns an error text, or null when the task started. */
    fun start(apiKey: String, prompt: String, maxSteps: Int, askRisky: Boolean): String? {
        val svc = JevAccessibilityService.instance
            ?: return "Bedienungshilfe für JevPilot ist aus – oben auf „Aktivieren“ tippen."
        if (busy) return "Jev arbeitet schon."
        if (apiKey.isBlank()) return "Kein API-Key gesetzt (⚙)."
        if (prompt.isBlank()) return "Prompt ist leer."
        stop.set(false)
        setBusy(true)
        log.add("\n> $prompt", "user")
        thread(name = "jev-agent") {
            try {
                svc.showPill("✻ Jev startet …  ·  tippen = Stop")
                svc.goHome()
                Thread.sleep(900)
                run(Jev(apiKey), svc, prompt, maxSteps, askRisky)
            } catch (e: JevError) {
                log.add("Jev: ${e.message}", "err")
            } catch (e: Exception) {
                log.add("Fehler: ${e.javaClass.simpleName}: ${e.message}", "err")
            } finally {
                svc.showPill(if (stop.get()) "✻ Gestoppt" else "✻ Jev ist fertig")
                svc.hidePill(2500)
                setBusy(false)
            }
        }
        return null
    }

    private fun overlap(text: String, words: Set<String>) =
        Regex("\\w{3,}").findAll(text.lowercase()).map { it.value }.toSet().intersect(words).size

    private fun trim(options: List<Opt>, prompt: String): List<Opt> {
        if (options.size <= Jev.MAX_CHOICE_OPTIONS) return options
        val words = Regex("\\w{3,}").findAll(prompt.lowercase()).map { it.value }.toSet()
        val keep = options.sortedByDescending { it.priority + overlap(it.desc, words) }
            .take(Jev.MAX_CHOICE_OPTIONS).toSet()
        return options.filter { it in keep }
    }

    private fun run(jev: Jev, svc: JevAccessibilityService, prompt: String, maxSteps: Int, askRisky: Boolean) {
        val history = mutableListOf<String>()
        val repeats = HashMap<String, Int>()
        val banned = HashSet<String>()
        for (step in 1..maxSteps) {
            if (stop.get()) { log.add("Gestoppt.", "warn"); return }
            val (screen, found) = svc.observe(prompt)
            var options = found.filter { it.desc !in banned } +
                Opt("Finish: the task is complete, stop here", "finish", priority = 99.0)
            options = trim(options, prompt)
            val keys = options.withIndex().associate { (i, o) -> "a$i" to o }
            val state = JSONObject(screen.toString())
                .put("task", prompt).put("step", step)
                .put("history", JSONArray(history.takeLast(10).ifEmpty { listOf("(nothing done yet)") }))
            val (answers, dt) = jev.ask(state, JSONObject()
                .put("next", Jev.choice(DECIDE_INSTR, keys.mapValues { it.value.desc }))
                .put("done", Jev.noul(DONE_INSTR)))
            val next = answers.getJSONObject("next")
            val key = next.getString("choice")
            val opt = keys[key] ?: continue
            val prob = next.optJSONObject("probabilities")?.optDouble(key, 0.0) ?: 0.0
            val doneP = answers.getJSONObject("done").getDouble("noul")
            log.add("[$step] ${opt.desc}", "act")
            log.add("p=%.2f  fertig=%.2f  %d ms  (%d Optionen)".format(prob, doneP, (dt * 1000).toInt(), options.size), "meta")
            svc.showPill("✻ ${opt.desc}  ·  tippen = Stop")

            if (opt.kind == "finish" || (doneP > 0.8 && step > 1)) {
                log.add("Jev meldet: Aufgabe erledigt.", "ok"); return
            }
            if (stop.get()) { log.add("Gestoppt.", "warn"); return }
            if (askRisky && isRisky(jev, opt, state)) {
                if (!svc.confirm("Jev will jetzt ausführen:\n\n${opt.desc}\n\nErlauben?") { stop.get() }) {
                    log.add("Vom Nutzer abgelehnt, Aktion gesperrt.", "warn")
                    banned.add(opt.desc)
                    history.add("${opt.desc} -> REFUSED by user, do something else")
                    continue
                }
            }
            val result = try {
                svc.execute(opt)
            } catch (e: Exception) {
                "failed: ${e.message?.take(150)}".also { log.add(it, "err") }
            }
            history.add("${opt.desc} -> $result")
            val n = (repeats[opt.desc] ?: 0) + 1
            repeats[opt.desc] = n
            if (n >= 3) banned.add(opt.desc)
        }
        log.add("Schritt-Limit ($maxSteps) erreicht.", "warn")
    }

    private fun isRisky(jev: Jev, opt: Opt, state: JSONObject): Boolean {
        if (!opt.mayCommit) return false
        if (RISKY_WORDS.containsMatchIn(opt.desc)) return true
        val (a, _) = jev.ask(JSONObject(state.toString()).put("proposed_action", opt.desc),
            JSONObject().put("risky", Jev.noul(RISK_INSTR)))
        return a.getJSONObject("risky").getDouble("noul") > 0.5
    }
}
