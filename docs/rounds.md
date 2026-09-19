# ROUNDS

In ROUNDS spielst du gegen Jev. Jev bewegt sich, springt, schießt, blockt und wählt nach jeder Runde eine Karte. Zielen und Block-Timing übernimmt der Mod. Jev trifft etwa 7 Entscheidungen pro Sekunde.

## Einrichten (einmalig)
1. [BepInEx 5 (Windows x64)](https://github.com/BepInEx/BepInEx/releases) laden und in den ROUNDS-Ordner entpacken.
   Den Ordner findest du so: in Steam Rechtsklick auf ROUNDS → Verwalten → Lokale Dateien durchsuchen.
2. ROUNDS einmal starten und wieder schließen. BepInEx legt dabei seine Ordner an.
3. `JevBridge.dll` aus den [Releases](../../../releases/latest) nach `ROUNDS\BepInEx\plugins\JevBridge\` kopieren.

## Spielen
1. In JevPilot links **ROUNDS** wählen und **Start** drücken. Läuft ROUNDS noch nicht, startet JevPilot es über Steam.
2. Im Spiel nacheinander:
   1. **Lokal** → **Versus** wählen.
   2. **Leertaste** drücken: du trittst bei.
   3. **B** drücken: ein Bot tritt bei, Jev übernimmt ihn.
   4. **Leertaste** drücken: bereit.
3. Aufhören: `Ctrl+Alt+X` oder Stop. Danach spielt wieder die normale Bot-KI.

Soll Jev einen bestimmten Spieler steuern, schreib zum Beispiel `spieler 1` in den Prompt.

Der Mod greift nur in lokalen Spielen ein, nie online.

## Fehler
| Meldung | Lösung |
|---|---|
| „ROUNDS läuft, aber ohne JevBridge“ | BepInEx oder JevBridge fehlt, oder ROUNDS lief schon vorher. ROUNDS schließen und neu starten. |
| „Warte auf Bot – drück B in der Lobby“ | In der Lobby mit **B** einen Bot hinzufügen. |
