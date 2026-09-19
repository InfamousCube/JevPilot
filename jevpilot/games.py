"""Game adapters, loaded at runtime from the `games` folder next to the .exe.

Jev cannot see pixels, so every game needs an adapter that turns the game
into text (observe) and a fixed list of moves (actions). Dropping a new
adapter file into the folder adds it to the sidebar without rebuilding.

Adapter file contract (games/<name>.py):

    from jevpilot.games import GameAdapter

    class Adapter(GameAdapter):
        name = "Snake"
        description = "Classic snake"
        hz = 10                                   # decisions per second
        image = "snake.png"                       # optional; else games/<file>.png/.jpg

        def start(self): ...                     # connect / focus the game
        def observe(self) -> dict: ...           # game state as JSON-able dict
        def actions(self) -> dict[str, str]: ... # key -> English description
        def act(self, key: str): ...             # press the keys for that move
        def stop(self): ...
        instructions = "Pick the move that keeps the snake alive and reaches food."

    Complex games can instead define run(self, jev, prompt, stop, log) and
    drive everything themselves (see rounds.py).
"""
import importlib.util
import os
import sys
import threading
import time

from .jev import Jev, choice

README = __doc__


class GameAdapter:
    name = "Game"
    description = ""
    hz = 5
    image = None
    file_stem = ""
    instructions = "Pick the best move for the player right now."

    def start(self):
        pass

    def observe(self) -> dict:
        raise NotImplementedError

    def actions(self) -> dict:
        raise NotImplementedError

    def act(self, key: str):
        raise NotImplementedError

    def stop(self):
        pass

    def goal(self, prompt: str) -> str:
        return prompt


def games_dir() -> str:
    base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(base, "games")
    os.makedirs(path, exist_ok=True)
    readme = os.path.join(path, "README.txt")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write(README)
    return path


def load_adapters(log) -> list[GameAdapter]:
    found = []
    for fn in sorted(os.listdir(games_dir())):
        if not fn.endswith(".py") or fn.startswith("_"):
            continue
        path = os.path.join(games_dir(), fn)
        try:
            spec = importlib.util.spec_from_file_location(f"jp_game_{fn[:-3]}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            adapter = mod.Adapter()
            adapter.file_stem = fn[:-3]
            found.append(adapter)
        except Exception as e:  # noqa: BLE001 - one broken adapter must not kill the app
            log(f"Spiel-Adapter {fn} fehlerhaft: {e}", "err")
    return found


def play(adapter: GameAdapter, jev: Jev, prompt: str, stop: threading.Event, log):
    # Adapters with their own loop (several questions per tick, menus, ...) take over here.
    if hasattr(adapter, "run"):
        adapter.run(jev, prompt, stop, log)
        return
    adapter.start()
    log(f"Spiele {adapter.name} mit {adapter.hz} Entscheidungen/s. Stop: Ctrl+Alt+X", "ok")
    n = 0
    try:
        while not stop.is_set():
            t0 = time.perf_counter()
            acts = adapter.actions()
            answers, dt = jev.ask({"goal": adapter.goal(prompt), "game": adapter.observe()},
                                  {"move": choice(adapter.instructions, acts)})
            move = answers["move"]["choice"]
            adapter.act(move)
            n += 1
            if n % max(1, adapter.hz) == 0:
                log(f"  #{n} {acts[move]}  ({dt*1000:.0f} ms)", "meta")
            time.sleep(max(0.0, 1 / adapter.hz - (time.perf_counter() - t0)))
    finally:
        adapter.stop()
        log(f"{adapter.name} beendet nach {n} Zügen.", "warn")


# Repo link used in the "more games" prompt (also in the Android app, MainActivity.REPO_URL).
REPO_URL = "https://github.com/InfamousCube/JevPilot"

ADAPTER_PROMPT = """Ich nutze JevPilot ({repo}) und will ein neues Spiel.
Bau mir einen Spiel-Adapter für: <SPIELNAME HIER EINTRAGEN>

So funktioniert JevPilot:
- Adapter sind .py-Dateien im Ordner "games" neben JevPilot.exe (Standard: %LOCALAPPDATA%\\Programs\\JevPilot\\games). Sie werden beim Start geladen, die Exe muss nicht neu gebaut werden.
- Vorlagen im Repo: jevpilot/games.py (Klasse GameAdapter, Doku oben in der Datei) und games/rounds.py.
- Jev (TypeSafe System One) sieht keine Bilder und schreibt keinen Text. Er beantwortet nur Choice (max. 255 Optionen), Score und Noul (ja/nein). Der Adapter muss den Spielzustand als Text/JSON liefern und jeden möglichen Zug als kurzen englischen Satz anbieten.
- Hat das Spiel keinen lesbaren Zustand, bau eine Brücke: z. B. einen BepInEx-Mod wie ROUNDS-Bridge/JevBridge, eine Speicherdatei, eine Web-API oder Bildschirm-Auslese.
- Leg ein breites Titelbild als games/<dateiname>.jpg dazu (wird in der Bibliothek rechts abgedunkelt).

Teste den Adapter am Ende und sag mir, wie ich ihn in JevPilot starte."""


def adapter_prompt() -> str:
    return ADAPTER_PROMPT.format(repo=REPO_URL)
