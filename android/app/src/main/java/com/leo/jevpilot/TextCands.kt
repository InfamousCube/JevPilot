package com.leo.jevpilot

/**
 * Pull typeable text out of the user's prompt (port of jevpilot/textcands.py).
 * Jev cannot generate text, so anything typed must already be in the prompt.
 */
object TextCands {
    private val QUOTES = Regex("\"([^\"]+)\"|'([^']+)'|„([^“”\"]+)[“”\"]|«([^»]+)»")
    val URL = Regex("\\b((?:https?://)?(?:[a-z0-9-]+\\.)+[a-z]{2,}(?:/\\S*)?)", RegexOption.IGNORE_CASE)
    private const val TRIGGERS =
        "suche(?:\\s+nach)?|such(?:\\s+nach)?|nach|search(?:\\s+for)?|for|tippe|tipp|type|" +
        "schreib(?:e)?|write|gib\\s+ein|eingeben|enter|namens|called|titel|title|" +
        "nachricht|message|text"
    private val TRIGGER_RE = Regex("\\b(?:$TRIGGERS)\\b[:\\s]+(.+)", RegexOption.IGNORE_CASE)
    private val STOP_RE = Regex(
        "[,.;!?]|\\s(?:und|and|dann|then|auf|on|in|bei|at|mit|with|über|via)\\s", RegexOption.IGNORE_CASE)
    private val LEAD_RE = Regex("^(?:in|ins|into|im|to|an)\\s+\\S+\\s+", RegexOption.IGNORE_CASE)

    private fun clean(s: String) = s.trim().trim('"', '\'', '„', '“', '”', '«', '»', ':').trim()

    fun candidates(prompt: String, limit: Int = 10): List<String> {
        val out = mutableListOf<String>()
        fun add(raw: String) {
            val s = clean(raw)
            if (s.length in 1..300 && out.none { it.equals(s, ignoreCase = true) }) out.add(s)
        }
        QUOTES.findAll(prompt).forEach { m -> m.groupValues.drop(1).firstOrNull { it.isNotEmpty() }?.let(::add) }
        TRIGGER_RE.findAll(prompt).forEach { m ->
            val rest = m.groupValues[1]
            val cut = STOP_RE.find(rest)
            add(if (cut != null) rest.substring(0, cut.range.first) else rest)
            add(LEAD_RE.replace(rest, ""))
            add(rest)
        }
        URL.findAll(prompt).forEach { add(it.groupValues[1]) }
        for (part in prompt.split(Regex("[,;\\n]"))) {
            val words = part.trim().split(Regex("\\s+")).filter { it.isNotEmpty() }
            for (n in listOf(2, 3, 1)) if (words.size > n) add(words.takeLast(n).joinToString(" "))
            if (words.size <= 6) add(part)
        }
        return out.take(limit)
    }

    fun urls(prompt: String): List<String> = URL.findAll(prompt).map { it.groupValues[1] }.toList()
}
