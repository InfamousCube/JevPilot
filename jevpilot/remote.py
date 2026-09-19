"""Small HTTP API so the JevPilot phone app can start tasks on this PC.

Every request needs the pairing code (config "remote_token") in the
X-JevPilot-Token header. The phone reaches the PC over Wi-Fi (LAN IP) or over
USB via `adb reverse tcp:8765 tcp:8765` (then it is plain 127.0.0.1).

  GET  /api/status?since=N   log lines since N, busy flag, pending confirm, games
  GET  /api/card?i=&w=&h=&state=   rendered game card (PNG, same look as the sidebar)
  POST /api/run      {"prompt", "mode", "steps", "risky", "game"}
  POST /api/stop
  POST /api/confirm  {"id", "yes"}
"""
import hmac
import io
import itertools
import json
import secrets
import socket
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT = 8765


def lan_ip() -> str:
    """IP of the interface that routes to the internet (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def ensure_token(cfg: dict) -> str:
    if not cfg.get("remote_token"):
        cfg["remote_token"] = secrets.token_hex(8)
    return cfg["remote_token"]


class ConfirmRequest:
    _ids = itertools.count(1)

    def __init__(self, text: str):
        self.id = next(self._ids)
        self.text = text
        self.answer = False
        self.event = threading.Event()

    def resolve(self, yes: bool):
        if not self.event.is_set():
            self.answer = bool(yes)
            self.event.set()


class Remote:
    def __init__(self, app):
        self.app = app
        self.lines: deque = deque(maxlen=2000)
        self.next_index = 0
        self.lock = threading.Lock()
        self.confirm: ConfirmRequest | None = None
        self.server = None
        self.error = None

    # -- called by the app ------------------------------------------------
    def add_line(self, text: str, tag: str):
        with self.lock:
            self.lines.append((self.next_index, text, tag))
            self.next_index += 1

    def open_confirm(self, text: str) -> ConfirmRequest:
        req = ConfirmRequest(text)
        self.confirm = req
        return req

    def close_confirm(self, req: ConfirmRequest):
        if self.confirm is req:
            self.confirm = None

    def start(self):
        remote = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # keep the console quiet
                pass

            def _authorized(self) -> bool:
                sent = self.headers.get("X-JevPilot-Token", "")
                return hmac.compare_digest(sent, remote.app.cfg.get("remote_token", "") or "\0")

            def _send(self, code: int, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if not self._authorized():
                    return self._send(401, {"error": "Falscher Kopplungscode"})
                url = urlparse(self.path)
                q = {k: v[0] for k, v in parse_qs(url.query).items()}
                if url.path == "/api/status":
                    return self._send(200, remote.status(int(q.get("since", 0))))
                if url.path == "/api/card":
                    png = remote.card(int(q.get("i", 0)), int(q.get("w", 900)),
                                      int(q.get("h", 150)), q.get("state", "idle"))
                    if png is None:
                        return self._send(404, {"error": "no such game"})
                    return self._send(200, png, "image/png")
                self._send(404, {"error": "unknown path"})

            def do_POST(self):
                if not self._authorized():
                    return self._send(401, {"error": "Falscher Kopplungscode"})
                n = int(self.headers.get("Content-Length", 0) or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._send(400, {"error": "bad json"})
                path = urlparse(self.path).path
                if path == "/api/run":
                    err = remote.app.remote_run(
                        str(body.get("prompt", "")).strip(), body.get("mode", "Auto"),
                        int(body.get("steps", 25)), bool(body.get("risky", True)),
                        body.get("game"))
                    return self._send(200 if not err else 409, {"error": err} if err else {"ok": True})
                if path == "/api/stop":
                    remote.app.stop_task()
                    return self._send(200, {"ok": True})
                if path == "/api/confirm":
                    req = remote.confirm
                    if req and req.id == body.get("id"):
                        req.resolve(bool(body.get("yes")))
                    return self._send(200, {"ok": True})
                self._send(404, {"error": "unknown path"})

        try:
            self.server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
        except OSError as e:
            self.error = str(e)
            return False
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return True

    # -- API bodies ------------------------------------------------------
    def status(self, since: int) -> dict:
        with self.lock:
            lines = [list(l) for l in self.lines if l[0] >= since]
            nxt = self.next_index
        req = self.confirm
        return {
            "pc": socket.gethostname(),
            "busy": self.app.busy,
            "lines": lines,
            "next": nxt,
            "confirm": {"id": req.id, "text": req.text} if req and not req.event.is_set() else None,
            "games": [{"name": a.name, "description": getattr(a, "description", "")}
                      for a in self.app.adapters],
        }

    def card(self, i: int, w: int, h: int, state: str) -> bytes | None:
        from .cards import find_image, render_card
        from .games import games_dir
        adapters = self.app.adapters
        if not 0 <= i < len(adapters):
            return None
        a = adapters[i]
        w, h = max(100, min(w, 2000)), max(30, min(h, 600))
        img = render_card(a.name, find_image(games_dir(), a.file_stem, a.image), w, h,
                          self.app.sidebar_rgb, state if state in ("idle", "selected") else "idle",
                          self.app.accent_rgb)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()

    def shutdown(self):
        if self.server:
            self.server.shutdown()
