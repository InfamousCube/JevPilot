"""Environment-agnostic decide/act loop.

Each step: the environment lists everything it could do right now as short
English sentences, Jev picks one (Choice) and says whether the task is done
(Noul). Code stays in control: it builds the options, runs the action, and
blocks risky clicks until the user agrees.
"""
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from .jev import MAX_CHOICE_OPTIONS, Jev, choice, noul

RISKY_WORDS = re.compile(
    r"\b(buy|kaufen|kauf|bestell\w*|order|pay|bezahl\w*|zahlungspflichtig|checkout|kasse|"
    r"send|senden|absenden|abschicken|post|posten|veröffentlich\w*|publish|tweet|"
    r"delete|löschen|lösch\w*|entfernen|remove|uninstall|deinstall\w*|"
    r"submit|confirm|bestätigen|abonnieren|subscribe|überweis\w*|transfer|format\w*)\b",
    re.I,
)


@dataclass
class Option:
    desc: str                     # English sentence shown to Jev and in the log
    kind: str                     # click | type | key | nav | scroll | finish | ...
    data: dict = field(default_factory=dict)
    priority: float = 0.0         # higher survives truncation to 255 options
    may_commit: bool = False      # action could submit/send/buy -> risk check


class Environment:
    name = "env"

    def observe(self) -> tuple[dict, list[Option]]:
        raise NotImplementedError

    def execute(self, opt: Option) -> str:
        raise NotImplementedError

    def close(self):
        pass


DECIDE_INSTR = (
    "You control a computer for the user. Pick the single next action that best moves the "
    "user's task forward from the current state. Use the history to avoid repeating actions "
    "that did not help. If a cookie banner blocks the page, prefer the option that rejects "
    "optional cookies. Pick 'Finish' only when the task is completely done."
)
DONE_INSTR = (
    "Given the task, the current state and the history of actions, the user's task is "
    "already completely finished and nothing else needs to be done."
)
RISK_INSTR = (
    "Doing the proposed action would buy or pay for something, send a message or email, "
    "post or publish something publicly, delete data, or change account or security settings."
)


def overlap_score(text: str, prompt_words: set[str]) -> float:
    words = set(re.findall(r"\w{3,}", text.lower()))
    return len(words & prompt_words)


class Agent:
    def __init__(self, jev: Jev, log: Callable[[str, str], None],
                 confirm: Callable[[str], bool], stop: threading.Event):
        self.jev = jev
        self.log = log            # log(text, tag)
        self.confirm = confirm    # confirm(question) -> bool, blocks
        self.stop = stop

    def run(self, prompt: str, env: Environment, max_steps: int = 25, ask_risky: bool = True):
        history: list[str] = []
        repeats: dict[str, int] = {}
        banned: set[str] = set()
        for step in range(1, max_steps + 1):
            if self.stop.is_set():
                self.log("Gestoppt.", "warn")
                return
            try:
                state, options = env.observe()
            except Exception as e:  # noqa: BLE001 - surface any env failure to the log
                self.log(f"Beobachten fehlgeschlagen: {e}", "err")
                return
            options = [o for o in options if o.desc not in banned]
            options.append(Option("Finish: the task is complete, stop here", "finish", priority=99))
            options = self._trim(options, prompt)
            keys = {f"a{i}": o for i, o in enumerate(options)}
            full_state = {"task": prompt, "step": step, **state,
                          "history": history[-10:] or ["(nothing done yet)"]}
            answers, dt = self.jev.ask(full_state, {
                "next": choice(DECIDE_INSTR, {k: o.desc for k, o in keys.items()}),
                "done": noul(DONE_INSTR),
            })
            nxt, done_p = answers["next"], answers["done"]["noul"]
            opt = keys[nxt["choice"]]
            prob = nxt["probabilities"].get(nxt["choice"], 0)
            self.log(f"[{step}] {opt.desc}", "act")
            self.log(f"     p={prob:.2f}  conf={nxt.get('confidence', 0):.2f}  "
                     f"fertig={done_p:.2f}  {dt*1000:.0f} ms  ({len(options)} Optionen)", "meta")

            if opt.kind == "finish" or (done_p > 0.8 and step > 1):
                self.log("Jev meldet: Aufgabe erledigt.", "ok")
                return
            if self.stop.is_set():
                self.log("Gestoppt.", "warn")
                return
            if ask_risky and self._is_risky(opt, full_state):
                if not self.confirm(f"Jev will jetzt ausführen:\n\n{opt.desc}\n\nErlauben?"):
                    self.log("Vom Nutzer abgelehnt, Aktion gesperrt.", "warn")
                    banned.add(opt.desc)
                    history.append(f"{opt.desc} -> REFUSED by user, do something else")
                    continue
            try:
                result = env.execute(opt)
            except Exception as e:  # noqa: BLE001
                result = f"failed: {str(e).splitlines()[0][:150]}"
                self.log(f"     Fehler: {result}", "err")
            history.append(f"{opt.desc} -> {result}")
            repeats[opt.desc] = repeats.get(opt.desc, 0) + 1
            if repeats[opt.desc] >= 3:
                banned.add(opt.desc)
        self.log(f"Schritt-Limit ({max_steps}) erreicht.", "warn")

    def _trim(self, options: list[Option], prompt: str) -> list[Option]:
        if len(options) <= MAX_CHOICE_OPTIONS:
            return options
        words = set(re.findall(r"\w{3,}", prompt.lower()))
        ranked = sorted(options, key=lambda o: -(o.priority + overlap_score(o.desc, words)))
        keep = set(map(id, ranked[:MAX_CHOICE_OPTIONS]))
        return [o for o in options if id(o) in keep]

    def _is_risky(self, opt: Option, state: dict) -> bool:
        if not opt.may_commit:
            return False
        if RISKY_WORDS.search(opt.desc):
            return True
        answers, _ = self.jev.ask({**state, "proposed_action": opt.desc},
                                  {"risky": noul(RISK_INSTR)})
        return answers["risky"]["noul"] > 0.5


def pick_mode(jev: Jev, prompt: str) -> str:
    answers, _ = jev.ask({"task": prompt}, {"mode": choice(
        "Where does this computer task mainly happen?",
        {"browser": "On a website or web app in the web browser (search, YouTube, email "
                    "in the browser, online shops, any URL)",
         "desktop": "In a Windows program, the file explorer, Windows settings, or an app "
                    "installed on the PC"})})
    return answers["mode"]["choice"]
