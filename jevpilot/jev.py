"""Thin HTTP client for TypeSafe's System One endpoint (Jev)."""
import time

import requests

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-latest"
MAX_CHOICE_OPTIONS = 255


class JevError(RuntimeError):
    pass


class Jev:
    def __init__(self, api_key: str, model: str = MODEL):
        self.api_key = api_key.strip()
        self.model = model
        self.session = requests.Session()
        self.tokens_in = 0

    def ask(self, state, questions: dict, retries: int = 3) -> tuple[dict, float]:
        """Send one System One request. Returns (answers, seconds)."""
        if not self.api_key:
            raise JevError("Kein API-Key gesetzt (Einstellungen).")
        body = {"model": self.model, "state": state, "questions": questions}
        headers = {"Authorization": f"Bearer {self.api_key}"}
        delay = 1.0
        for attempt in range(retries + 1):
            t0 = time.perf_counter()
            try:
                r = self.session.post(ENDPOINT, json=body, headers=headers, timeout=30)
            except requests.RequestException as e:
                if attempt == retries:
                    raise JevError(f"Netzwerkfehler: {e}") from e
                time.sleep(delay)
                delay *= 2
                continue
            dt = time.perf_counter() - t0
            if r.status_code == 200:
                data = r.json()
                self.tokens_in += data.get("usage", {}).get("input_tokens", 0)
                return data["answers"], dt
            if r.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(delay)
                delay *= 2
                continue
            if r.status_code in (401, 403):
                raise JevError("API-Key ungültig oder ohne Rechte (HTTP %d)." % r.status_code)
            raise JevError(f"HTTP {r.status_code}: {r.text[:300]}")
        raise JevError("Keine Antwort von Jev.")


def choice(instructions: str, options: dict) -> dict:
    return {"type": "choice", "instructions": instructions, "criteria": options}


def noul(instructions: str) -> dict:
    return {"type": "noul", "instructions": instructions}
