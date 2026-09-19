"""Browser environment: Edge (or Chrome) driven by Playwright.

The page is turned into text: every visible interactive element gets a
data-jp id and a readable label; those become Jev's options.
"""
import os
import re
import time
from urllib.parse import quote_plus

from .agent import Environment, Option, overlap_score
from .textcands import text_candidates, urls_in

PROFILE_DIR = os.path.join(os.environ.get("LOCALAPPDATA", "."), "JevPilot", "browser-profile")

SITES = {
    "youtube": "https://www.youtube.com", "google": "https://www.google.com",
    "wikipedia": "https://de.wikipedia.org", "amazon": "https://www.amazon.de",
    "netflix": "https://www.netflix.com", "twitch": "https://www.twitch.tv",
    "reddit": "https://www.reddit.com", "github": "https://github.com",
    "gmail": "https://mail.google.com", "outlook": "https://outlook.live.com",
    "maps": "https://www.google.com/maps", "spotify": "https://open.spotify.com",
    "instagram": "https://www.instagram.com", "tiktok": "https://www.tiktok.com",
    "twitter": "https://x.com", "facebook": "https://www.facebook.com",
    "chatgpt": "https://chatgpt.com", "claude": "https://claude.ai",
    "discord": "https://discord.com/app", "ebay": "https://www.ebay.de",
    "roblox": "https://www.roblox.com", "steam": "https://store.steampowered.com",
    "fiverr": "https://www.fiverr.com", "translate": "https://translate.google.com",
    "übersetzer": "https://translate.google.com", "wetter": "https://wetter.com",
    "weather": "https://weather.com", "kleinanzeigen": "https://www.kleinanzeigen.de",
    "linkedin": "https://www.linkedin.com", "pinterest": "https://www.pinterest.com",
    "duckduckgo": "https://duckduckgo.com", "bing": "https://www.bing.com",
    "modrinth": "https://modrinth.com", "curseforge": "https://www.curseforge.com",
}

OBSERVE_JS = r"""
() => {
  const sel = 'a[href],button,input,textarea,select,summary,[role=button],[role=link],' +
    '[role=tab],[role=menuitem],[role=option],[role=checkbox],[role=switch],[role=combobox],' +
    '[role=searchbox],[role=textbox],[contenteditable=""],[contenteditable=true],[onclick]';
  const vh = innerHeight, vw = innerWidth, out = [];
  let n = 0;
  document.querySelectorAll('[data-jp]').forEach(e => e.removeAttribute('data-jp'));
  for (const el of document.querySelectorAll(sel)) {
    const r = el.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || cs.display === 'none' || +cs.opacity === 0) continue;
    if (el.disabled || el.getAttribute('aria-hidden') === 'true') continue;
    const tag = el.tagName.toLowerCase(), type = (el.type || '').toLowerCase();
    if (type === 'hidden') continue;
    const text = (el.innerText || '').replace(/\s+/g, ' ').trim();
    const name = (el.getAttribute('aria-label') || text || el.placeholder || el.title ||
      el.getAttribute('alt') || (el.querySelector && el.querySelector('img[alt]')?.alt) ||
      el.name || el.value || '').toString().replace(/\s+/g, ' ').trim().slice(0, 90);
    const editable = tag === 'textarea' || el.isContentEditable ||
      (tag === 'input' && !['button','submit','checkbox','radio','file','image','reset','range','color'].includes(type)) ||
      ['textbox','searchbox','combobox'].includes(el.getAttribute('role'));
    if (!name && !editable) continue;
    const id = String(n++);
    el.setAttribute('data-jp', id);
    const opts = tag === 'select' ? [...el.options].slice(0, 15).map(o => o.text.trim()) : [];
    out.push({id, tag, type, role: el.getAttribute('role') || '', name, editable,
      password: type === 'password', value: editable ? String(el.value || '').slice(0, 60) : '',
      href: tag === 'a' ? (el.getAttribute('href') || '').slice(0, 80) : '',
      inView: r.bottom > 0 && r.top < vh && r.right > 0 && r.left < vw, opts});
    if (n >= 400) break;
  }
  const text = (document.body ? document.body.innerText : '').replace(/\n{2,}/g, '\n').slice(0, 1500);
  return {elements: out, text, scrollY, maxScroll: document.documentElement.scrollHeight - vh};
}
"""


def _kind_label(e: dict) -> str:
    if e["editable"]:
        return "search box" if "search" in (e["type"] + e["role"] + e["name"]).lower() else "text field"
    if e["tag"] == "a" or e["role"] == "link":
        return "link"
    if e["tag"] == "select":
        return "dropdown"
    if e["type"] in ("checkbox", "radio") or e["role"] in ("checkbox", "switch"):
        return "checkbox"
    if e["role"] == "tab":
        return "tab"
    return "button"


class BrowserEnv(Environment):
    name = "Browser"

    def __init__(self, log):
        self.log = log
        self.pw = None
        self.ctx = None
        self.page = None
        self.prompt = ""

    # -- lifecycle ---------------------------------------------------------
    def ensure(self):
        if self.ctx is not None:
            try:
                _ = self.ctx.pages
                if self.page is None or self.page.is_closed():
                    self.page = self.ctx.pages[-1] if self.ctx.pages else self.ctx.new_page()
                return
            except Exception:  # noqa: BLE001 - browser was closed by the user
                self.ctx = None
        from playwright.sync_api import sync_playwright
        if self.pw is None:
            self.pw = sync_playwright().start()
        os.makedirs(PROFILE_DIR, exist_ok=True)
        last = None
        for channel in ("msedge", "chrome", None):
            try:
                self.ctx = self.pw.chromium.launch_persistent_context(
                    PROFILE_DIR, channel=channel, headless=False, no_viewport=True,
                    args=["--start-maximized"])
                break
            except Exception as e:  # noqa: BLE001 - try the next installed browser
                last = e
        if self.ctx is None:
            raise RuntimeError(f"Could not start a browser (Edge/Chrome): {last}")
        self.ctx.on("page", self._on_page)
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()

    def _on_page(self, page):
        self.page = page

    def start_task(self, prompt: str):
        self.prompt = prompt
        self.ensure()
        self.page.bring_to_front()

    def close(self):
        try:
            if self.ctx:
                self.ctx.close()
            if self.pw:
                self.pw.stop()
        except Exception:  # noqa: BLE001
            pass
        self.ctx = self.pw = self.page = None

    # -- observe -----------------------------------------------------------
    def observe(self):
        self.ensure()
        page = self.page
        try:
            page.wait_for_load_state("domcontentloaded", timeout=5000)
        except Exception:  # noqa: BLE001 - slow pages still get observed
            pass
        data = page.evaluate(OBSERVE_JS)
        words = set(re.findall(r"\w{3,}", self.prompt.lower()))
        texts = text_candidates(self.prompt)
        opts: list[Option] = []

        # Visible elements first, then the rest (Jev sees them in this order).
        els = sorted(data["elements"], key=lambda e: (not e["inView"], int(e["id"])))
        for e in els:
            if e["password"]:
                continue  # never let the agent handle passwords
            label = _kind_label(e)
            name = e["name"] or "(unnamed)"
            where = "" if e["inView"] else " (below/above, not visible)"
            base = 1.0 if e["inView"] else 0.0
            if e["editable"]:
                val = f", currently contains \"{e['value']}\"" if e["value"] else ""
                for t in texts:
                    pr = base + 2 + overlap_score(t, words)
                    opts.append(Option(f'Type "{t}" into {label} "{name}"{val}{where}', "type",
                                       {"id": e["id"], "text": t, "enter": False}, pr))
                    opts.append(Option(f'Type "{t}" into {label} "{name}" and press Enter{where}',
                                       "type", {"id": e["id"], "text": t, "enter": True}, pr + 0.5,
                                       may_commit=True))
                continue
            if e["tag"] == "select":
                for o in e["opts"]:
                    opts.append(Option(f'Select "{o}" in dropdown "{name}"', "select",
                                       {"id": e["id"], "value": o}, base + overlap_score(o, words)))
                continue
            href = f" -> {e['href']}" if e["href"] and not e["href"].startswith(("#", "javascript")) else ""
            opts.append(Option(f'Click {label} "{name}"{href}{where}', "click", {"id": e["id"]},
                               base + overlap_score(name, words), may_commit=label == "button"))

        for u in urls_in(self.prompt):
            opts.append(Option(f"Open website {u}", "nav", {"url": u}, 5))
        low = self.prompt.lower()
        for key, url in SITES.items():
            if key in low:
                opts.append(Option(f"Open website {key} ({url})", "nav", {"url": url}, 5))
        for t in texts:
            opts.append(Option(f'Search Google for "{t}"', "nav",
                               {"url": "https://www.google.com/search?q=" + quote_plus(t)}, 3))
        if data["scrollY"] < data["maxScroll"] - 5:
            opts.append(Option("Scroll down to see more of the page", "scroll", {"dy": 700}, 4))
        if data["scrollY"] > 5:
            opts.append(Option("Scroll up", "scroll", {"dy": -700}, 1))
        opts.append(Option("Press Enter", "key", {"key": "Enter"}, 1, may_commit=True))
        opts.append(Option("Press Escape (close popup or menu)", "key", {"key": "Escape"}, 1))
        opts.append(Option("Go back to the previous page", "back", {}, 1))

        state = {"browser": {"url": page.url, "title": page.title(),
                             "visible_text": data["text"]}}
        return state, opts

    # -- act ---------------------------------------------------------------
    def execute(self, opt: Option) -> str:
        page, d = self.page, opt.data
        loc = page.locator(f'[data-jp="{d["id"]}"]').first if "id" in d else None
        if opt.kind == "click":
            self._reveal(loc)
            loc.click(timeout=5000)
        elif opt.kind == "type":
            self._reveal(loc)
            try:
                loc.fill(d["text"], timeout=4000)
            except Exception:  # noqa: BLE001 - contenteditable etc.
                loc.click(timeout=4000)
                page.keyboard.press("Control+A")
                page.keyboard.type(d["text"], delay=15)
            if d["enter"]:
                loc.press("Enter")
        elif opt.kind == "select":
            loc.select_option(label=d["value"], timeout=4000)
        elif opt.kind == "nav":
            url = d["url"] if d["url"].startswith("http") else "https://" + d["url"]
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
        elif opt.kind == "scroll":
            page.mouse.wheel(0, d["dy"])
        elif opt.kind == "key":
            page.keyboard.press(d["key"])
        elif opt.kind == "back":
            page.go_back(timeout=10000)
        self._settle()
        return "ok"

    def _settle(self):
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=4000)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.8)

    @staticmethod
    def _reveal(loc):
        try:
            loc.scroll_into_view_if_needed(timeout=2000)
        except Exception:  # noqa: BLE001 - element may still be clickable
            pass
