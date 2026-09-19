"""JevPilot - type a prompt, Jev operates the browser or the PC."""
import json
import os
import queue
import threading
import tkinter as tk

import customtkinter as ctk
import keyboard

from jevpilot.agent import Agent, pick_mode
from jevpilot.cards import find_image, render_card
from jevpilot.games import adapter_prompt, games_dir, load_adapters, play
from jevpilot.jev import Jev, JevError
from jevpilot.remote import PORT, Remote, ensure_token, lan_ip

APP_TITLE = "JevPilot"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", "."), "JevPilot")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
STOP_HOTKEY = "ctrl+alt+x"

# Claude Code palette: warm charcoal, cream text, terracotta accent.
BG, SIDEBAR, INPUT, LINE = "#262624", "#1f1e1d", "#30302e", "#3e3d39"
ACCENT, ACCENT_HI, ACCENT_DIM = "#d97757", "#c6613f", "#8a4a35"
TEXT, MUTED, FAINT = "#faf9f5", "#a6a39b", "#6f6c64"
GREEN, RED, YELLOW = "#7fb87a", "#e0715f", "#e0b25f"
TAG_COLORS = {"act": TEXT, "bullet": ACCENT, "meta": MUTED, "ok": GREEN, "warn": YELLOW,
              "err": RED, "user": "#c9c5bb"}
SIDEBAR_W, CARD_W, CARD_H = 272, 236, 58


def hex_rgb(h: str) -> tuple:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    if not cfg.get("api_key") and os.environ.get("TYPESAFE_API_KEY"):
        cfg["api_key"] = os.environ["TYPESAFE_API_KEY"]
    return cfg


def save_config(cfg: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


class Worker(threading.Thread):
    """Owns the browser and runs every task, so Playwright stays on one thread."""

    def __init__(self, ui: "App"):
        super().__init__(daemon=True)
        self.ui = ui
        self.jobs: queue.Queue = queue.Queue()
        self.stop = threading.Event()
        self.browser = None
        self.desktop = None

    def run(self):
        while True:
            job = self.jobs.get()
            if job is None:
                break
            self.stop.clear()
            self.ui.set_busy(True)
            try:
                job()
            except JevError as e:
                self.ui.log(f"Jev: {e}", "err")
            except Exception as e:  # noqa: BLE001 - keep the worker alive
                self.ui.log(f"Error: {type(e).__name__}: {e}", "err")
            finally:
                self.ui.set_busy(False)
        if self.browser:
            self.browser.close()

    def task(self, prompt: str, mode: str, max_steps: int, ask_risky: bool):
        jev = Jev(self.ui.cfg.get("api_key", ""))
        if mode == "Auto":
            mode = "Browser" if pick_mode(jev, prompt) == "browser" else "PC"
            self.ui.log(f"Jev picked mode: {mode}", "meta")
        if mode == "Browser":
            from jevpilot.browser_env import BrowserEnv
            if self.browser is None:
                self.browser = BrowserEnv(self.ui.log)
            env = self.browser
        else:
            from jevpilot.desktop_env import DesktopEnv
            if self.desktop is None:
                self.desktop = DesktopEnv(self.ui.log, APP_TITLE)
            env = self.desktop
            self.ui.shrink(True)
        try:
            env.start_task(prompt)
            Agent(jev, self.ui.log, self.ui.confirm, self.stop).run(
                prompt, env, max_steps=max_steps, ask_risky=ask_risky)
        finally:
            if mode == "PC":
                self.ui.shrink(False)
        self.ui.log(f"Tokens so far: {jev.tokens_in:,}", "meta")

    def game(self, adapter, prompt: str):
        play(adapter, Jev(self.ui.cfg.get("api_key", "")), prompt, self.stop, self.ui.log)


class App(ctk.CTk):
    def __init__(self):
        super().__init__(fg_color=BG)
        self.cfg = load_config()
        self.title(APP_TITLE)
        self.geometry("1120x720")
        self.minsize(860, 540)
        self.busy = False
        self.selected_game = None
        self.adapters = []
        self.cards = []
        self.sidebar_rgb, self.accent_rgb = hex_rgb(SIDEBAR), hex_rgb(ACCENT)
        self.remote = Remote(self)
        if not self.cfg.get("remote_token"):
            ensure_token(self.cfg)
            save_config(self.cfg)
        self.worker = Worker(self)
        self.worker.start()
        self._build()
        self.refresh_games()
        try:
            keyboard.add_hotkey(STOP_HOTKEY, self.stop_task)
        except Exception:  # noqa: BLE001 - hotkey needs no admin, but don't crash if it fails
            pass
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(50, self._dark_titlebar)
        if not self.cfg.get("api_key"):
            self.after(300, self.welcome)
        self.log("Ready. Type a prompt, Ctrl+Enter starts, Ctrl+Alt+X stops everywhere.", "ok")
        if self.remote.start():
            self.log(f"Phone app: {lan_ip()}:{PORT} · pairing code {self.cfg['remote_token']}",
                     "meta")
        else:
            self.log(f"Phone connection off (port {PORT} in use: {self.remote.error})", "warn")

    # -- layout ------------------------------------------------------------
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        side = ctk.CTkFrame(self, width=SIDEBAR_W, fg_color=SIDEBAR, corner_radius=0)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.pack_propagate(False)
        ctk.CTkFrame(self, width=1, fg_color=LINE, corner_radius=0).grid(
            row=0, column=0, sticky="nse")

        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(anchor="w", padx=18, pady=(22, 0))
        ctk.CTkLabel(brand, text="✻", font=("Segoe UI Symbol", 22), text_color=ACCENT
                     ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(brand, text="JevPilot", font=("Georgia", 22), text_color=TEXT
                     ).pack(side="left")
        ctk.CTkLabel(side, text="Computer use with TypeSafe Jev", font=("Segoe UI", 11),
                     text_color=MUTED).pack(anchor="w", padx=20, pady=(2, 0))

        self._section(side, "Mode").pack(anchor="w", padx=20, pady=(24, 6))
        self.mode = ctk.CTkSegmentedButton(
            side, values=["Auto", "Browser", "PC"], command=lambda _: self.select_game(None),
            fg_color=INPUT, unselected_color=INPUT, unselected_hover_color=LINE,
            selected_color=ACCENT, selected_hover_color=ACCENT_HI, text_color=TEXT,
            font=("Segoe UI Semibold", 12), corner_radius=8, height=32)
        self.mode.set("Auto")
        self.mode.pack(fill="x", padx=16)

        ctk.CTkButton(side, text="⚙  Settings", anchor="w", fg_color="transparent",
                      hover_color=LINE, text_color=MUTED, font=("Segoe UI", 12),
                      command=self.open_settings).pack(fill="x", padx=12, pady=14, side="bottom")

        head = ctk.CTkFrame(side, fg_color="transparent")
        head.pack(fill="x", padx=20, pady=(26, 6))
        self._section(head, "Games").pack(side="left")
        ctk.CTkButton(head, text="↻", width=24, height=22, fg_color="transparent",
                      hover_color=LINE, text_color=MUTED, command=self.refresh_games
                      ).pack(side="right")
        ctk.CTkButton(head, text="Folder", width=50, height=22, fg_color="transparent",
                      hover_color=LINE, text_color=MUTED, font=("Segoe UI", 11),
                      command=lambda: os.startfile(games_dir())).pack(side="right")
        self.games_box = ctk.CTkScrollableFrame(
            side, fg_color="transparent", scrollbar_button_color=SIDEBAR,
            scrollbar_button_hover_color=LINE)
        self.games_box.pack(fill="both", expand=True, padx=(10, 2))

        main = ctk.CTkFrame(self, fg_color=BG)
        main.grid(row=0, column=1, sticky="nsew", padx=28, pady=22)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(3, weight=1)

        self.target = ctk.CTkLabel(main, text="", font=("Segoe UI", 12), text_color=MUTED)
        self.target.grid(row=0, column=0, sticky="w", padx=2)

        box = ctk.CTkFrame(main, fg_color=INPUT, border_color=LINE, border_width=1,
                           corner_radius=14)
        box.grid(row=1, column=0, sticky="ew", pady=(6, 14))
        box.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(box, text="›", font=("Segoe UI Semibold", 22), text_color=ACCENT
                     ).grid(row=0, column=0, sticky="n", padx=(14, 2), pady=(6, 0))
        self.prompt = ctk.CTkTextbox(box, height=84, font=("Segoe UI", 14), fg_color=INPUT,
                                     text_color=TEXT, border_width=0, wrap="word",
                                     scrollbar_button_color=INPUT)
        self.prompt.grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=(8, 2))
        self.prompt.bind("<Control-Return>", lambda e: (self.start_task(), "break")[1])
        self.prompt.bind("<FocusIn>", lambda e: box.configure(border_color=ACCENT_DIM))
        self.prompt.bind("<FocusOut>", lambda e: box.configure(border_color=LINE))

        foot = ctk.CTkFrame(box, fg_color="transparent")
        foot.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 10))
        self.risky = ctk.CTkSwitch(foot, text="Ask before buying/sending/deleting",
                                   progress_color=ACCENT, button_color=TEXT,
                                   button_hover_color="#ffffff", fg_color=LINE,
                                   text_color=MUTED, font=("Segoe UI", 12))
        self.risky.select()
        self.risky.pack(side="left", padx=(6, 0))
        self.start_btn = ctk.CTkButton(foot, text="Start  ↵", width=104, height=34,
                                       corner_radius=9, fg_color=ACCENT, hover_color=ACCENT_HI,
                                       text_color="#ffffff", font=("Segoe UI Semibold", 13),
                                       text_color_disabled="#f3d5c9", command=self.start_task)
        self.start_btn.pack(side="right")
        self.stop_btn = ctk.CTkButton(foot, text="Stop", width=76, height=34, corner_radius=9,
                                      fg_color="transparent", border_width=1, border_color=LINE,
                                      hover_color=LINE, text_color=MUTED, state="disabled",
                                      text_color_disabled=FAINT,
                                      font=("Segoe UI Semibold", 13), command=self.stop_task)
        self.stop_btn.pack(side="right", padx=8)
        self.steps_lbl = ctk.CTkLabel(foot, text="25 steps", text_color=MUTED, width=74,
                                      font=("Segoe UI", 12))
        self.steps_lbl.pack(side="right", padx=(0, 10))
        self.steps = ctk.CTkSlider(foot, from_=5, to=80, number_of_steps=15, width=120,
                                   progress_color=ACCENT, button_color=TEXT,
                                   button_hover_color="#ffffff", fg_color=LINE,
                                   command=lambda v: self.steps_lbl.configure(
                                       text=f"{int(v)} steps"))
        self.steps.set(25)
        self.steps.pack(side="right")

        self.logbox = ctk.CTkTextbox(main, font=("Cascadia Mono", 12), fg_color=BG,
                                     text_color=TEXT, border_width=0, wrap="word",
                                     scrollbar_button_color=LINE)
        self.logbox.grid(row=3, column=0, sticky="nsew")
        for tag, col in TAG_COLORS.items():
            self.logbox.tag_config(tag, foreground=col)
        self.logbox.configure(state="disabled")
        self.select_game(None)

        # Small always-on-top pill shown while Jev drives the desktop.
        self.pill = tk.Toplevel(self)
        self.pill.overrideredirect(True)
        self.pill.attributes("-topmost", True)
        self.pill.configure(bg=ACCENT)
        self.pill_lbl = tk.Label(self.pill, text="✻ JevPilot is in control · Ctrl+Alt+X stops",
                                 bg=ACCENT, fg="white", font=("Segoe UI Semibold", 10),
                                 padx=14, pady=5)
        self.pill_lbl.pack()
        self.pill.withdraw()

    def _dark_titlebar(self):
        """Windows 11: dark title bar tinted like the sidebar."""
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            dwm = ctypes.windll.dwmapi.DwmSetWindowAttribute
            on = ctypes.c_int(1)
            dwm(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))  # DWMWA_USE_IMMERSIVE_DARK_MODE
            r, g, b = hex_rgb(SIDEBAR)
            color = ctypes.c_int(r | g << 8 | b << 16)
            dwm(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))  # DWMWA_CAPTION_COLOR
        except (AttributeError, OSError):
            pass

    @staticmethod
    def _section(parent, text):
        return ctk.CTkLabel(parent, text=text.upper(), font=("Segoe UI Semibold", 10),
                            text_color=FAINT)

    # -- games -------------------------------------------------------------
    def refresh_games(self):
        for w in self.games_box.winfo_children():
            w.destroy()
        self.cards = []
        self.adapters = load_adapters(self.log)
        if self.selected_game and self.selected_game.name not in [a.name for a in self.adapters]:
            self.select_game(None)
        for a in self.adapters:
            img_path = find_image(games_dir(), a.file_stem, a.image)
            imgs = {st: ctk.CTkImage(render_card(a.name, img_path, CARD_W, CARD_H,
                                                 hex_rgb(SIDEBAR), st, hex_rgb(ACCENT)),
                                     size=(CARD_W, CARD_H))
                    for st in ("idle", "hover", "selected")}
            lbl = ctk.CTkLabel(self.games_box, text="", image=imgs["idle"], cursor="hand2")
            lbl.pack(pady=3, anchor="w")
            card = {"adapter": a, "label": lbl, "imgs": imgs}
            lbl.bind("<Button-1>", lambda e, a=a: self.select_game(
                None if self.selected_game is a else a))
            lbl.bind("<Enter>", lambda e, c=card: self._paint(c, hover=True))
            lbl.bind("<Leave>", lambda e, c=card: self._paint(c, hover=False))
            self.cards.append(card)
        self._more_games_card()
        self._paint_all()

    def _more_games_card(self):
        """Last card in the library: how to get more games (ask a coding agent)."""
        box = ctk.CTkFrame(self.games_box, fg_color="transparent", border_width=1,
                           border_color=LINE, corner_radius=9, width=CARD_W)
        box.pack(pady=(3, 6), anchor="w")
        ctk.CTkLabel(box, text="+  More games", text_color=TEXT, font=("Segoe UI Semibold", 12)
                     ).pack(anchor="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(box, text="Ask Claude Code or Codex – copy the\nprompt, fill in the game name.",
                     text_color=MUTED, font=("Segoe UI", 11), justify="left"
                     ).pack(anchor="w", padx=12)
        btn = ctk.CTkButton(box, text="Copy prompt", height=26, width=CARD_W - 24,
                            corner_radius=7, fg_color=INPUT, hover_color=LINE, text_color=TEXT,
                            border_width=1, border_color=ACCENT_DIM, font=("Segoe UI", 11))

        def copy():
            self.clipboard_clear()
            self.clipboard_append(adapter_prompt())
            btn.configure(text="✓ Copied")
            self.log("Game prompt copied – paste it into Claude Code or Codex and fill in "
                     "the game name.", "ok")
            self.after(1800, lambda: btn.configure(text="Copy prompt"))
        btn.configure(command=copy)
        btn.pack(padx=12, pady=(6, 10))

    def _paint(self, card, hover=False):
        st = "selected" if card["adapter"] is self.selected_game else ("hover" if hover else "idle")
        card["label"].configure(image=card["imgs"][st])

    def _paint_all(self):
        for c in self.cards:
            self._paint(c)

    def select_game(self, adapter):
        self.selected_game = adapter
        if adapter:
            self.target.configure(text=f"Game: {adapter.name}  ·  describe a goal or play style "
                                       "(optional), then Start", text_color=ACCENT)
        else:
            self.target.configure(text="What should Jev do?  e.g.  open youtube and search "
                                       "\"lofi hip hop\"", text_color=MUTED)
        self._paint_all()

    # -- actions -----------------------------------------------------------
    def start_task(self):
        if self.busy:
            return
        prompt = self.prompt.get("1.0", "end").strip()
        if not self.cfg.get("api_key"):
            self.open_settings()
            return
        if self.selected_game:
            game = self.selected_game
            self.log(f"\n> Game: {game.name}", "user")
            self.worker.jobs.put(lambda: self.worker.game(game, prompt))
            return
        if not prompt:
            return
        self.log(f"\n> {prompt}", "user")
        mode, steps, risky = self.mode.get(), int(self.steps.get()), bool(self.risky.get())
        self.worker.jobs.put(lambda: self.worker.task(prompt, mode, steps, risky))

    def stop_task(self):
        self.worker.stop.set()

    def remote_run(self, prompt: str, mode: str, steps: int, risky: bool, game) -> str | None:
        """Start a job sent from the phone app. Returns an error text or None."""
        if self.busy:
            return "JevPilot is already busy – stop it first."
        if not self.cfg.get("api_key"):
            return "No API key is set on the PC."
        if game:
            adapter = next((a for a in self.adapters if a.name == game), None)
            if adapter is None:
                return f"Game {game} is not installed on the PC."
            self.busy = True
            self.log(f"\n> (phone) Game: {adapter.name}", "user")
            self.worker.jobs.put(lambda: self.worker.game(adapter, prompt))
            return None
        if not prompt:
            return "The prompt is empty."
        if mode not in ("Auto", "Browser", "PC"):
            mode = "Auto"
        self.busy = True
        self.log(f"\n> (phone) {prompt}", "user")
        steps = max(3, min(steps, 120))
        self.worker.jobs.put(lambda: self.worker.task(prompt, mode, steps, risky))
        return None

    # -- thread-safe UI helpers --------------------------------------------
    def log(self, text: str, tag: str = "act"):
        self.remote.add_line(text, tag)

        def do():
            self.logbox.configure(state="normal")
            body = text.strip("\n")
            if text.startswith("\n"):
                self.logbox.insert("end", "\n")
            if tag == "act":
                self.logbox.insert("end", "⏺ ", "bullet")
                self.logbox.insert("end", body + "\n", "act")
            elif tag == "meta":
                self.logbox.insert("end", "  ⎿  " + body.strip() + "\n", "meta")
            else:
                self.logbox.insert("end", body + "\n", tag)
            self.logbox.see("end")
            self.logbox.configure(state="disabled")
            self.pill_lbl.configure(text=f"✻ {body.strip()[:70]}  ·  Ctrl+Alt+X stops")
        self.after(0, do)

    def set_busy(self, busy: bool):
        def do():
            self.busy = busy
            self.start_btn.configure(state="disabled" if busy else "normal",
                                     text="Running …" if busy else "Start  ↵")
            self.stop_btn.configure(state="normal" if busy else "disabled",
                                    text_color=TEXT if busy else MUTED,
                                    border_color=ACCENT if busy else LINE)
        self.after(0, do)

    def shrink(self, on: bool):
        done = threading.Event()

        def do():
            if on:
                self.iconify()
                self.pill.update_idletasks()
                x = (self.winfo_screenwidth() - 460) // 2
                self.pill.geometry(f"+{x}+8")
                self.pill.deiconify()
            else:
                self.pill.withdraw()
                self.deiconify()
            done.set()
        self.after(0, do)
        done.wait(3)
        if on:
            threading.Event().wait(0.6)  # let the previous window regain focus

    def confirm(self, question: str) -> bool:
        """Ask on the PC and in the phone app at once; the first answer wins."""
        req = self.remote.open_confirm(question)

        def do():
            win = ctk.CTkToplevel(self, fg_color=BG)
            win.title("JevPilot – Confirm")
            win.attributes("-topmost", True)
            win.resizable(False, False)
            win.protocol("WM_DELETE_WINDOW", lambda: req.resolve(False))
            ctk.CTkLabel(win, text=question, text_color=TEXT, font=("Segoe UI", 13),
                         justify="left", wraplength=420).pack(padx=22, pady=(20, 12), anchor="w")
            row = ctk.CTkFrame(win, fg_color="transparent")
            row.pack(fill="x", padx=22, pady=(0, 18))
            ctk.CTkButton(row, text="Allow", fg_color=ACCENT, hover_color=ACCENT_HI,
                          corner_radius=9, width=110, command=lambda: req.resolve(True)
                          ).pack(side="right")
            ctk.CTkButton(row, text="Deny", fg_color="transparent", border_width=1,
                          border_color=LINE, hover_color=LINE, text_color=MUTED, corner_radius=9,
                          width=110, command=lambda: req.resolve(False)).pack(side="right", padx=8)

            def poll():
                if req.event.is_set():
                    win.destroy()
                else:
                    win.after(150, poll)
            poll()
        self.after(0, do)
        req.event.wait()
        self.remote.close_confirm(req)
        return req.answer

    def welcome(self):
        """First start: JevPilot only works with the user's own TypeSafe key."""
        dlg = ctk.CTkToplevel(self, fg_color=BG)
        dlg.title("Welcome to JevPilot")
        dlg.geometry("560x330")
        dlg.resizable(False, False)
        dlg.transient(self)
        dlg.after(100, dlg.grab_set)
        # Without a key JevPilot can't do anything, so closing this closes the app.
        dlg.protocol("WM_DELETE_WINDOW", self.on_close)
        head = ctk.CTkFrame(dlg, fg_color="transparent")
        head.pack(anchor="w", padx=24, pady=(24, 0))
        ctk.CTkLabel(head, text="✻", font=("Segoe UI Symbol", 24), text_color=ACCENT
                     ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(head, text="Welcome to JevPilot", font=("Georgia", 20), text_color=TEXT
                     ).pack(side="left")
        ctk.CTkLabel(dlg, text="JevPilot lets TypeSafe Jev operate your PC, browser and games.\n"
                               "To use it you need your own TypeSafe API key.",
                     text_color=MUTED, font=("Segoe UI", 12), justify="left"
                     ).pack(anchor="w", padx=24, pady=(10, 12))
        entry = ctk.CTkEntry(dlg, show="•", width=512, height=38, fg_color=INPUT,
                             border_color=LINE, text_color=TEXT, corner_radius=9,
                             placeholder_text="Paste your API key")
        entry.pack(padx=24)
        ctk.CTkLabel(dlg, text=f"Stored only on this PC: {CONFIG_PATH}",
                     text_color=FAINT, font=("Segoe UI", 11)).pack(anchor="w", padx=24, pady=4)
        status = ctk.CTkLabel(dlg, text="", text_color=MUTED)
        status.pack(anchor="w", padx=24)

        def go():
            key = entry.get().strip()
            if not key:
                status.configure(text="Please paste a key.", text_color=YELLOW)
                return
            status.configure(text="Testing key …", text_color=MUTED)

            def test():
                try:
                    Jev(key).ask("ping", {"t": {"type": "noul", "instructions": "This is a test"}})
                except JevError as e:
                    self.after(0, lambda: status.configure(text=f"✗ {e}", text_color=RED))
                    return

                def ok():
                    self.cfg["api_key"] = key
                    save_config(self.cfg)
                    self.log("✓ API key saved. Let's go.", "ok")
                    dlg.destroy()
                self.after(0, ok)
            threading.Thread(target=test, daemon=True).start()
        entry.bind("<Return>", lambda e: go())
        ctk.CTkButton(dlg, text="Check & start", fg_color=ACCENT, hover_color=ACCENT_HI,
                      corner_radius=9, height=36, font=("Segoe UI Semibold", 13),
                      command=go).pack(anchor="e", padx=24, pady=10)
        dlg.after(200, entry.focus_set)

    def open_settings(self):
        dlg = ctk.CTkToplevel(self, fg_color=BG)
        dlg.title("Settings")
        dlg.geometry("540x300")
        dlg.transient(self)
        dlg.after(100, dlg.grab_set)
        ctk.CTkLabel(dlg, text="TypeSafe API key", font=("Georgia", 16), text_color=TEXT
                     ).pack(anchor="w", padx=22, pady=(22, 6))
        entry = ctk.CTkEntry(dlg, show="•", width=496, height=36, fg_color=INPUT,
                             border_color=LINE, text_color=TEXT, corner_radius=9)
        entry.insert(0, self.cfg.get("api_key", ""))
        entry.pack(padx=22)
        ctk.CTkLabel(dlg, text=f"Stored locally only: {CONFIG_PATH}", text_color=FAINT,
                     font=("Segoe UI", 11)).pack(anchor="w", padx=22, pady=4)
        status = ctk.CTkLabel(dlg, text="", text_color=MUTED)
        status.pack(anchor="w", padx=22)
        ctk.CTkLabel(dlg, text="Phone app", font=("Georgia", 16), text_color=TEXT
                     ).pack(anchor="w", padx=22, pady=(8, 2))
        ctk.CTkLabel(dlg, text=f"PC address  {lan_ip()}:{PORT}     Pairing code  "
                               f"{self.cfg.get('remote_token', '')}",
                     text_color=MUTED, font=("Cascadia Mono", 12)).pack(anchor="w", padx=22)

        def save():
            self.cfg["api_key"] = entry.get().strip()
            save_config(self.cfg)
            status.configure(text="Testing key …", text_color=MUTED)

            def test():
                try:
                    Jev(self.cfg["api_key"]).ask("ping", {"t": {"type": "noul",
                                                              "instructions": "This is a test"}})
                    self.after(0, lambda: (status.configure(text="✓ Key works",
                                                            text_color=GREEN),
                                           dlg.after(700, dlg.destroy)))
                except JevError as e:
                    self.after(0, lambda: status.configure(text=f"✗ {e}", text_color=RED))
            threading.Thread(target=test, daemon=True).start()
        ctk.CTkButton(dlg, text="Save & test", fg_color=ACCENT, hover_color=ACCENT_HI,
                      corner_radius=9, height=34, font=("Segoe UI Semibold", 13),
                      command=save).pack(anchor="e", padx=22, pady=10)

    def on_close(self):
        self.remote.shutdown()
        self.worker.stop.set()
        self.worker.jobs.put(None)
        self.after(400, self.destroy)


def selftest(out_path: str):
    """`JevPilot.exe --selftest out.txt`: checks key, browser and UI Automation headlessly."""
    import sys
    lines = []
    try:
        Jev(load_config().get("api_key", "")).ask("ping", {"t": {"type": "noul",
                                                             "instructions": "This is a test"}})
        lines.append("jev ok")
        from jevpilot.browser_env import BrowserEnv
        env = BrowserEnv(print)
        env.start_task("open example.com")
        env.page.goto("https://example.com")
        state, opts = env.observe()
        lines.append(f"browser ok: {state['browser']['title']} / {len(opts)} options")
        env.close()
        from jevpilot.desktop_env import DesktopEnv
        d = DesktopEnv(print, APP_TITLE)
        lines.append(f"desktop ok: {len(d.apps)} apps")
    except Exception as e:  # noqa: BLE001
        lines.append(f"FAIL {type(e).__name__}: {e}")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    sys.exit(0)


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--selftest":
        selftest(sys.argv[2])
    ctk.set_appearance_mode("dark")
    App().mainloop()
