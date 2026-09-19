# Spiele

Jev sieht keine Pixel. Darum braucht jedes Spiel einen **Adapter**: eine `.py`-Datei mit zwei Aufgaben.
- Sie gibt den Spielzustand als Text aus.
- Sie listet die möglichen Züge als kurze englische Sätze auf.

Adapter liegen im Ordner `games` neben `JevPilot.exe` (Standard: `%LOCALAPPDATA%\Programs\JevPilot\games`). JevPilot lädt sie beim Start. Mit ↻ in der Bibliothek lädst du sie neu. Die Exe musst du dafür nicht neu bauen.

| Spiel | Adapter | Anleitung |
|---|---|---|
| ROUNDS | `games/rounds.py` + BepInEx-Mod `JevBridge` | [ROUNDS](rounds.md) |

## Neues Spiel von Claude Code oder Codex bauen lassen
1. In der Spiele-Bibliothek (PC oder Handy) auf **Prompt kopieren** klicken.
2. Den Prompt in [Claude Code](https://claude.com/claude-code) oder Codex einfügen.
3. `<SPIELNAME HIER EINTRAGEN>` durch den Namen deines Spiels ersetzen.
4. Den Agenten den Adapter bauen und testen lassen.
5. Den fertigen Adapter und sein Titelbild (`<name>.jpg`) in den `games`-Ordner legen.
6. In der Bibliothek auf ↻ klicken.

## Adapter selbst schreiben
Für einfache Spiele mit einem Zug pro Takt:
```python
from jevpilot.games import GameAdapter

class Adapter(GameAdapter):
    name = "Snake"
    description = "Klassisches Snake"
    hz = 10                                    # Entscheidungen pro Sekunde
    image = "snake.jpg"                        # optional, sonst games/<datei>.jpg/.png
    instructions = "Pick the move that keeps the snake alive and reaches food."

    def start(self): ...                       # Spiel verbinden / fokussieren
    def observe(self) -> dict: ...             # Zustand als JSON-fähiges dict
    def actions(self) -> dict[str, str]: ...   # key -> englische Beschreibung
    def act(self, key: str): ...               # Tasten für diesen Zug drücken
    def stop(self): ...
```
Komplexe Echtzeit-Spiele definieren stattdessen `run(self, jev, prompt, stop, log)` und steuern alles selbst. Ein Beispiel ist [`games/rounds.py`](../games/rounds.py). Es nutzt mehrere parallele Jev-Anfragen, wählt Karten und spricht über eine Mod-Brücke mit dem Spiel.

**Was Jev kann:** Choice (bis 255 Optionen), Score und Noul (ja/nein). Jev erzeugt keinen Text und sieht keine Bilder.

**Tipps**
- Reflexe wie Zielen oder Timing gehören in den Code. Jev entscheidet die Taktik.
- Liefert das Spiel keinen lesbaren Zustand, bau eine Brücke: einen Mod (BepInEx, Forge …), eine Speicherdatei, eine API oder eine Bildschirm-Auslese.
