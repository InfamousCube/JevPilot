"""Pull typeable text out of the user's prompt.

Jev cannot generate text, so anything the agent types must already be in the
prompt. We offer Jev a short list of prompt fragments and let it pick one.
"""
import re

QUOTES = re.compile(r'"([^"]+)"|\'([^\']+)\'|„([^“”"]+)[“”"]|«([^»]+)»')
URL = re.compile(r"\b((?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/[^\s]*)?)", re.I)
TRIGGERS = (
    r"suche(?:\s+nach)?|such(?:\s+nach)?|nach|search(?:\s+for)?|for|tippe|tipp|type|"
    r"schreib(?:e)?|write|gib\s+ein|eingeben|enter|namens|called|titel|title|"
    r"nachricht|message|text"
)
TRIGGER_RE = re.compile(rf"\b(?:{TRIGGERS})\b[:\s]+(.+)", re.I)
STOP_RE = re.compile(
    r"[,.;!?]|\s(?:und|and|dann|then|auf|on|in|bei|at|mit|with|über|via)\s", re.I
)


def _clean(s: str) -> str:
    return s.strip().strip("\"'„“”«»:").strip()


def text_candidates(prompt: str, limit: int = 10) -> list[str]:
    out: list[str] = []

    def add(s: str):
        s = _clean(s)
        if 1 <= len(s) <= 300 and s.lower() not in (x.lower() for x in out):
            out.append(s)

    for m in QUOTES.finditer(prompt):
        add(next(g for g in m.groups() if g))
    for m in TRIGGER_RE.finditer(prompt):
        rest = m.group(1)
        cut = STOP_RE.search(rest)
        add(rest[: cut.start()] if cut else rest)
        # "schreib in notepad hallo welt" -> "hallo welt"
        add(re.sub(r"^(?:in|ins|into|im|to|an)\s+\S+\s+", "", rest, flags=re.I))
        add(rest)
    for m in URL.finditer(prompt):
        add(m.group(1))
    # Clause tails, e.g. "google wetter berlin" -> "wetter berlin", "berlin".
    for part in re.split(r"[,;\n]", prompt):
        words = part.split()
        for n in (2, 3, 1):
            if len(words) > n:
                add(" ".join(words[-n:]))
        if len(words) <= 6:
            add(part)
    return out[:limit]


def urls_in(prompt: str) -> list[str]:
    return [m.group(1) for m in URL.finditer(prompt)]
