"""Desktop environment: Windows UI Automation.

Windows exposes most normal apps as a tree of named controls (buttons, menus,
text fields). We read that tree as text and let Jev pick. Apps that draw their
own pixels (games, some Electron/Canvas views) show up as nearly empty.
"""
import json
import os
import re
import subprocess
import time

import keyboard
import uiautomation as auto

from .agent import Environment, Option, overlap_score
from .textcands import text_candidates

CLICKABLE = {
    "ButtonControl", "MenuItemControl", "ListItemControl", "TreeItemControl",
    "TabItemControl", "HyperlinkControl", "CheckBoxControl", "RadioButtonControl",
    "DataItemControl", "SplitButtonControl", "ComboBoxControl", "MenuBarControl",
}
EDITABLE = {"EditControl", "DocumentControl"}
LABELS = {
    "ButtonControl": "button", "MenuItemControl": "menu item", "ListItemControl": "list item",
    "TreeItemControl": "tree item", "TabItemControl": "tab", "HyperlinkControl": "link",
    "CheckBoxControl": "checkbox", "RadioButtonControl": "radio button",
    "DataItemControl": "item", "SplitButtonControl": "button", "ComboBoxControl": "dropdown",
    "EditControl": "text field", "DocumentControl": "document",
}
KEYS = [
    ("Press Enter", "enter", True), ("Press Escape", "esc", False), ("Press Tab", "tab", False),
    ("Save with Ctrl+S", "ctrl+s", False), ("Select all with Ctrl+A", "ctrl+a", False),
    ("Copy with Ctrl+C", "ctrl+c", False), ("Paste with Ctrl+V", "ctrl+v", False),
    ("Undo with Ctrl+Z", "ctrl+z", False), ("Open new tab/document with Ctrl+N", "ctrl+n", False),
    ("Close current window with Alt+F4", "alt+f4", True),
]


def _start_menu_apps() -> dict[str, str]:
    """Name -> AppsFolder id for every Start menu entry, Store apps included."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
             "Get-StartApps | ConvertTo-Json -Compress"],
            capture_output=True, text=True, encoding="utf-8", timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW).stdout
        rows = json.loads(out or "[]")
    except (OSError, ValueError, subprocess.SubprocessError):
        rows = []
    if isinstance(rows, dict):
        rows = [rows]
    apps = {}
    for r in rows:
        name, app_id = r.get("Name", ""), r.get("AppID", "")
        if name and app_id and not re.search(r"uninstall|deinstall|readme|help|hilfe", name, re.I):
            apps.setdefault(name, app_id)
    return apps


class DesktopEnv(Environment):
    name = "PC"

    def __init__(self, log, own_title: str):
        self.log = log
        self.own_title = own_title
        self.prompt = ""
        self.apps = _start_menu_apps()
        self.controls: dict[int, auto.Control] = {}

    def start_task(self, prompt: str):
        self.prompt = prompt
        self.apps = _start_menu_apps()

    def _windows(self):
        wins = []
        for w in auto.GetRootControl().GetChildren():
            try:
                if (w.ControlTypeName == "WindowControl" and w.Name and not w.IsOffscreen
                        and self.own_title not in w.Name and w.Name != "Program Manager"):
                    wins.append(w)
            except Exception:  # noqa: BLE001 - windows vanish while we look
                pass
        return wins

    def _target_window(self):
        fg = auto.GetForegroundControl()
        top = fg.GetTopLevelControl() if fg else None
        if top and top.Name and self.own_title not in top.Name:
            return top
        wins = self._windows()
        return wins[0] if wins else None

    def observe(self):
        with auto.UIAutomationInitializerInThread():
            return self._observe()

    def _observe(self):
        words = set(re.findall(r"\w{3,}", self.prompt.lower()))
        texts = text_candidates(self.prompt)
        win = self._target_window()
        opts: list[Option] = []
        self.controls = {}
        seen = 0
        if win is not None:
            for ctrl, depth in auto.WalkControl(win, maxDepth=14):
                seen += 1
                if seen > 1500 or len(self.controls) > 220:
                    break
                try:
                    ctype = ctrl.ControlTypeName
                    if ctype not in CLICKABLE and ctype not in EDITABLE:
                        continue
                    if ctrl.IsOffscreen or not ctrl.IsEnabled:
                        continue
                    r = ctrl.BoundingRectangle
                    if r.width() < 3 or r.height() < 3:
                        continue
                    name = (ctrl.Name or "").replace("\n", " ").strip()[:90]
                    label = LABELS.get(ctype, "control")
                    cid = len(self.controls)
                    if ctype in EDITABLE:
                        if ctype == "EditControl" and ctrl.GetPropertyValue(30019):  # IsPassword
                            continue
                        self.controls[cid] = ctrl
                        nm = name or "(unnamed)"
                        for t in texts:
                            pr = 2 + overlap_score(t, words)
                            opts.append(Option(f'Type "{t}" into {label} "{nm}"', "type",
                                               {"cid": cid, "text": t, "enter": False}, pr))
                            opts.append(Option(f'Type "{t}" into {label} "{nm}" and press Enter',
                                               "type", {"cid": cid, "text": t, "enter": True},
                                               pr + 0.5, may_commit=True))
                    elif name:
                        self.controls[cid] = ctrl
                        opts.append(Option(f'Click {label} "{name}"', "click", {"cid": cid},
                                           1 + overlap_score(name, words),
                                           may_commit=label == "button"))
                except Exception:  # noqa: BLE001 - controls can die mid-walk
                    continue

        for w in self._windows()[:15]:
            if win is None or w.NativeWindowHandle != win.NativeWindowHandle:
                opts.append(Option(f'Switch to window "{w.Name[:80]}"', "focus",
                                   {"hwnd": w.NativeWindowHandle}, 2 + overlap_score(w.Name, words)))
        ranked = sorted(self.apps, key=lambda n: -overlap_score(n, words))
        for name in ranked[:40]:
            opts.append(Option(f'Open app "{name}"', "app", {"id": self.apps[name]},
                               3 + 2 * overlap_score(name, words)))
        focused = auto.GetFocusedControl()
        if focused is not None and focused.ControlTypeName in EDITABLE and win is not None:
            fname = focused.Name or "(unnamed)"
            for t in texts:
                opts.append(Option(f'Type "{t}" into the focused text field "{fname}"', "rawtype",
                                   {"text": t}, 1))
        for desc, combo, commit in KEYS:
            opts.append(Option(desc, "key", {"combo": combo}, 0.5, may_commit=commit))
        opts.append(Option("Scroll down", "scroll", {"n": -5}, 1))
        opts.append(Option("Scroll up", "scroll", {"n": 5}, 0.5))
        opts.append(Option("Wait a moment for the app to load", "wait", {}, 0.5))

        state = {"desktop": {
            "active_window": win.Name if win is not None else "(none)",
            "open_windows": [w.Name[:60] for w in self._windows()[:15]],
            "visible_controls": len(self.controls),
        }}
        return state, opts

    def execute(self, opt: Option) -> str:
        with auto.UIAutomationInitializerInThread():
            return self._execute(opt)

    def _execute(self, opt: Option) -> str:
        d = opt.data
        if opt.kind == "click":
            ctrl = self.controls[d["cid"]]
            try:
                ctrl.GetInvokePattern().Invoke()
            except Exception:  # noqa: BLE001 - not invokable, click its center
                ctrl.Click(simulateMove=False)
        elif opt.kind == "type":
            ctrl = self.controls[d["cid"]]
            try:
                ctrl.GetValuePattern().SetValue(d["text"])
                ctrl.SetFocus()
            except Exception:  # noqa: BLE001
                ctrl.Click(simulateMove=False)
                keyboard.send("ctrl+a")
                keyboard.write(d["text"], delay=0.01)
            if d["enter"]:
                time.sleep(0.1)
                keyboard.send("enter")
        elif opt.kind == "rawtype":
            keyboard.write(d["text"], delay=0.01)
        elif opt.kind == "key":
            keyboard.send(d["combo"])
        elif opt.kind == "focus":
            ctrl = auto.ControlFromHandle(d["hwnd"])
            ctrl.SetActive()
            ctrl.SetFocus()
        elif opt.kind == "app":
            subprocess.Popen(["explorer.exe", "shell:AppsFolder\\" + d["id"]])
            time.sleep(2.5)
        elif opt.kind == "scroll":
            if d["n"] < 0:
                auto.WheelDown(-d["n"])
            else:
                auto.WheelUp(d["n"])
        elif opt.kind == "wait":
            time.sleep(2)
        time.sleep(0.6)
        return "ok"
