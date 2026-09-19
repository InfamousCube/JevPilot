"""ROUNDS adapter: Jev fights and picks cards through the JevBridge BepInEx plugin.

Split of work:
  - JevBridge (in the game) reads positions, health, ammo, bullets and cards,
    and does the frame-exact parts: ballistic aim at the chosen target (with lead
    and bullet drop learned from our own shots) and the block reflex timing.
  - Jev decides everything tactical, several times per second: move toward /
    away / stay, jump, shoot, arm the block, which enemy to target, and which
    card to take after each round.
Works only in local games (the plugin refuses online rooms).
"""
import json
import os
import re
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from jevpilot.games import GameAdapter
from jevpilot.jev import choice, noul

HOST, PORT = "127.0.0.1", 5577


def _find_game_exe() -> str:
    """ROUNDS.exe in any Steam library (Steam registry key + libraryfolders.vdf)."""
    roots = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
            roots.append(winreg.QueryValueEx(k, "SteamPath")[0])
    except OSError:
        pass
    roots.append(r"C:\Program Files (x86)\Steam")
    libs = []
    for root in roots:
        libs.append(root)
        try:
            with open(os.path.join(root, "steamapps", "libraryfolders.vdf"), encoding="utf-8") as f:
                libs += [p.replace("\\\\", "\\") for p in re.findall(r'"path"\s+"([^"]+)"', f.read())]
        except OSError:
            pass
    for lib in libs:
        exe = os.path.join(lib, "steamapps", "common", "ROUNDS", "ROUNDS.exe")
        if os.path.isfile(exe):
            return os.path.normpath(exe)
    return ""


GAME_EXE = _find_game_exe()
STEAM_URL = "steam://rungameid/1557740"   # BepInEx + JevBridge sit in the game folder
DECISION_EVERY = 0.12      # seconds between new Jev requests (3 in flight, ~8/s)
KEEPALIVE_EVERY = 0.05     # re-send the current command so the plugin never goes stale

MOVE_OPTS = {
    "toward": "Move toward the targeted enemy",
    "away": "Move away from the targeted enemy",
    "stay": "Stand still",
}
FIGHT_INSTR = (
    "You control a player in ROUNDS, a 2D side-view 1v1 shooter where one hit can matter. "
    "Aiming is automatic. "
)
PICK_INSTR = (
    "After each round in ROUNDS the player picks one card that permanently changes their "
    "gun, health, movement or block. Pick the card that most increases this player's chance "
    "to win the next rounds in a fast 2D shooter, considering synergy with the cards they "
    "already have and the user's goal."
)


def _side(dx: float, dy: float) -> str:
    h = "right" if dx > 0.5 else "left" if dx < -0.5 else "directly"
    v = "above" if dy > 1.5 else "below" if dy < -1.5 else "level"
    return f"{h}, {v}"


class Adapter(GameAdapter):
    name = "ROUNDS"
    description = "1v1 physics shooter – Jev moves, aims, blocks and picks cards"
    image = "rounds.jpg"

    def __init__(self):
        self.sock = None
        self.reader = None
        self.io_lock = threading.Lock()

    # ------------------------------------------------------------ bridge I/O
    def _try_connect(self) -> bool:
        try:
            self.sock = socket.create_connection((HOST, PORT), timeout=3)
        except OSError:
            return False
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.sock.settimeout(20)  # level loads freeze the game's main thread for seconds
        self.reader = self.sock.makefile("r", encoding="utf-8")
        return True

    def _connect(self, log, stop):
        if self._try_connect():
            return
        running = subprocess.run(["tasklist", "/FI", "IMAGENAME eq ROUNDS.exe", "/NH"],
                                 capture_output=True, text=True,
                                 creationflags=subprocess.CREATE_NO_WINDOW).stdout
        if "ROUNDS.exe" in running:
            log("ROUNDS is running without JevBridge. Close ROUNDS and start it again – "
                "waiting here.", "warn")
        else:
            log("Starting ROUNDS …", "meta")
            try:
                os.startfile(STEAM_URL)
            except OSError:
                if not GAME_EXE:
                    raise RuntimeError("ROUNDS not found – is it installed through Steam?")
                subprocess.Popen([GAME_EXE], cwd=os.path.dirname(GAME_EXE))
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline and not stop.is_set():
            time.sleep(2)
            if self._try_connect():
                return
        raise RuntimeError("ROUNDS started, but JevBridge does not answer.")

    def _cmd(self, line: str) -> dict:
        with self.io_lock:
            self.sock.sendall((line + "\n").encode())
            reply = self.reader.readline()
        if not reply:
            raise RuntimeError("Connection to ROUNDS lost.")
        return json.loads(reply)

    # ------------------------------------------------------------ main loop
    def run(self, jev, prompt, stop, log):
        m = re.search(r"(?:spieler|player|p)\s*(\d)", prompt, re.I)
        fixed_id = int(m.group(1)) - 1 if m else None
        self._connect(log, stop)
        log("ROUNDS connected. Stop: Ctrl+Alt+X", "ok")
        if fixed_id is None:
            log("Lobby: Local → Versus → Space (you) → B (bot = Jev). "
                "Jev takes over the bot.", "meta")
        else:
            self._cmd(f"CONTROL {fixed_id}")
            log(f"Jev controls player {fixed_id + 1}.", "meta")
        controlling = fixed_id

        pool = ThreadPoolExecutor(max_workers=3)
        decision = {"move": "stay", "shoot": False, "jump": False, "arm": False, "target": -1,
                    "seq": 0}
        applied_seq = [0]
        seq = [0]
        last_req = last_send = last_log = 0.0
        picked_for = None
        warned_online = False
        stats = {"n": 0, "ms": 0.0}

        def decide(state, my_seq):
            try:
                q, ctx = self._fight_questions(state, prompt)
                answers, dt = jev.ask(ctx, q)
            except Exception as e:  # noqa: BLE001 - one failed call must not stop the match
                log(f"  Jev error: {e}", "err")
                return
            if my_seq <= applied_seq[0]:
                return  # a newer answer already landed
            applied_seq[0] = my_seq
            decision.update(
                move=answers["move"]["choice"],
                shoot=answers["shoot"]["noul"] > 0.5,
                jump=answers["jump"]["noul"] > 0.5,
                arm=answers["danger"]["noul"] > 0.4,
                target=int(answers["target"]["choice"][1:]) if "target" in answers else -1,
                seq=my_seq, p=answers["move"]["probabilities"])
            stats["n"] += 1
            stats["ms"] += dt * 1000

        try:
            while not stop.is_set():
                now = time.monotonic()
                state = self._cmd("STATE")
                if not state.get("offline"):
                    if not warned_online:
                        log("Online game detected – JevBridge only acts in local games.",
                            "warn")
                        warned_online = True
                    time.sleep(0.5)
                    continue
                phase = state.get("phase")

                # Default: Jev drives the vanilla bot (key B), the user plays on keyboard.
                # Player objects are recreated between matches, so re-check every tick.
                if fixed_id is None:
                    bot = next((p for p in state.get("players", []) if p.get("bot")), None)
                    want = bot["id"] if bot else None
                    if want is not None and (want != controlling or state.get("controlled") != want):
                        self._cmd(f"CONTROL {want}")
                        if want != controlling:
                            log(f"Jev takes over the bot (player {want + 1}).", "ok")
                        controlling = want
                    if want is None:
                        if controlling is not None or now - last_log >= 10:
                            log("Waiting for a bot – press B in the lobby.", "meta")
                            last_log = now
                        controlling = None
                        time.sleep(0.3)
                        continue

                if phase == "pick" and state.get("my_pick") and state.get("cards_ready"):
                    key = tuple(c["name"] if c else "" for c in state.get("cards", []))
                    if key and key != picked_for:
                        picked_for = key
                        self._pick(jev, state, prompt, log)
                    time.sleep(0.2)
                    continue

                if phase == "fight":
                    me = self._me(state)
                    if now - last_req >= DECISION_EVERY:
                        seq[0] += 1
                        pool.submit(decide, state, seq[0])
                        last_req = now
                    if now - last_send >= KEEPALIVE_EVERY:
                        self._send_action(state, me, decision)
                        decision["jump"] = False  # one jump per decision
                        last_send = now
                    if now - last_log >= 1.5 and stats["n"]:
                        log(f"  {MOVE_OPTS[decision['move']].lower()}"
                            f"{', shooting' if decision['shoot'] else ''}"
                            f"{', block armed' if decision['arm'] else ''}"
                            f"  ·  {stats['n']} decisions, avg {stats['ms'] / stats['n']:.0f} ms",
                            "meta")
                        stats.update(n=0, ms=0.0)
                        last_log = now
                    time.sleep(0.02)
                    continue
                time.sleep(0.25)
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
            try:
                self._cmd("RELEASE")
                self.sock.close()
            except OSError:
                pass
            log("ROUNDS: control handed back.", "warn")

    # ------------------------------------------------------------ fighting
    @staticmethod
    def _me(state):
        return next((p for p in state["players"] if p["id"] == state["controlled"]), None)

    @staticmethod
    def _enemies(state, me):
        return [p for p in state["players"]
                if me and p["team"] != me["team"] and not p["dead"]]

    def _fight_questions(self, state, prompt):
        me = self._me(state)
        enemies = self._enemies(state, me)
        env = state.get("env", {})
        impact = env.get("bullet_impact_in", -1)
        ctx = {
            "goal": prompt or "Win the round.",
            "me": {
                "health": f"{me['hp']:.0f} of {me['max_hp']:.0f}",
                "ammo": f"{me.get('ammo', '?')} of {me.get('max_ammo', '?')}",
                "block_ready": me.get("block_ready"),
                "on_ground": me["grounded"], "jumps_left": me["jumps_left"],
                "wall_left": env.get("wall_left"), "wall_right": env.get("wall_right"),
                "ground_ahead_left": env.get("ground_left"),
                "ground_ahead_right": env.get("ground_right"),
                "ceiling_above": env.get("ceiling"),
                "cards": me["cards"],
            },
            "incoming_bullet": (f"an enemy bullet will hit in {impact:.2f} s" if impact >= 0
                                else "no bullet is heading at the player"),
            "enemies": [{
                "id": e["id"],
                "where": _side(e["x"] - me["x"], e["y"] - me["y"]),
                "distance": round(((e["x"] - me["x"]) ** 2 + (e["y"] - me["y"]) ** 2) ** 0.5, 1),
                "health": f"{e['hp']:.0f} of {e['max_hp']:.0f}",
                "can_see_enemy": e.get("line_of_sight"),
                "enemy_ammo": e.get("ammo"),
                "enemy_block_ready": e.get("block_ready"),
                "cards": e["cards"][-6:],
            } for e in enemies],
        }
        q = {
            "move": choice(FIGHT_INSTR + "Choose how the player should move right now.",
                           MOVE_OPTS),
            "shoot": noul(FIGHT_INSTR + "The player should shoot right now: an enemy is "
                                        "visible and the player has ammo."),
            "jump": noul(FIGHT_INSTR + "The player should jump right now, to dodge an incoming "
                                       "bullet, get over a wall or gap, reach higher ground, or "
                                       "get line of sight on the enemy."),
            "danger": noul(FIGHT_INSTR + "An enemy bullet is about to hit the player, so the "
                                         "block should be ready to trigger."),
        }
        if len(enemies) > 1:
            q["target"] = choice(FIGHT_INSTR + "Which enemy should the player target?",
                                 {f"e{e['id']}": f"Enemy {e['id']}: {_side(e['x'] - me['x'], e['y'] - me['y'])}, "
                                                 f"health {e['hp']:.0f}" for e in enemies})
        return q, ctx

    def _send_action(self, state, me, d):
        if me is None or me["dead"]:
            return
        enemies = self._enemies(state, me)
        tgt = next((e for e in enemies if e["id"] == d["target"]), None) or (
            min(enemies, key=lambda e: abs(e["x"] - me["x"]) + abs(e["y"] - me["y"]))
            if enemies else None)
        move = 0.0
        if tgt and d["move"] != "stay":
            toward = 1.0 if tgt["x"] > me["x"] else -1.0
            move = toward if d["move"] == "toward" else -toward
            if d["move"] == "toward" and abs(tgt["x"] - me["x"]) < 1.5:
                move = 0.0
        env = state.get("env", {})
        jump = d["jump"]
        # Code-side safety: never walk off a ledge without jumping.
        if move and me["grounded"] and not env.get("ground_right" if move > 0 else "ground_left", True):
            jump = jump or me["jumps_left"] > 0 and d["move"] == "toward"
            if not jump:
                move = 0.0
        self._cmd(f"ACT {move:.2f} {int(d['shoot'])} {int(jump)} {int(d['arm'])} 0 "
                  f"{tgt['id'] if tgt else -1}")

    # ------------------------------------------------------------ cards
    def _pick(self, jev, state, prompt, log):
        me = self._me(state)
        cards = state.get("cards", [])
        opts = {}
        for i, c in enumerate(cards):
            if not c:
                continue
            stats = ", ".join(f"{s['stat']} {s['amount']}".strip() for s in c["stats"] if s["stat"])
            opts[f"c{i}"] = f"{c['name']} ({c['rarity']}): {c['description']} [{stats}]".strip()
        if not opts:
            return
        ctx = {"goal": prompt or "Win the match.",
               "my_cards": me["cards"] if me else [],
               "my_health": me["max_hp"] if me else None,
               "my_ammo": me.get("max_ammo") if me else None,
               "enemy_cards": [p["cards"] for p in state["players"]
                               if me and p["team"] != me["team"]]}
        answers, dt = jev.ask(ctx, {"card": choice(PICK_INSTR, opts)})
        key = answers["card"]["choice"]
        idx = int(key[1:])
        prob = answers["card"]["probabilities"].get(key, 0)
        log(f"Card picked: {cards[idx]['name']}  (p={prob:.2f}, {dt * 1000:.0f} ms)", "act")
        r = self._cmd(f"PICK {idx}")
        if "error" in r:
            log(f"  Pick failed: {r['error']}", "err")
