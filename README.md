# ✻ JevPilot

**Computer Use mit [TypeSafe](https://typesafe.ai) Jev.** Du schreibst eine Aufgabe, und Jev bedient deinen PC, den Browser, Spiele und dein Android-Handy.

```
› öffne youtube und suche "lofi hip hop"
⏺ [1] Open the website youtube.com
⏺ [2] Type "lofi hip hop" into the field 'Search'
⏺ [3] Press Enter
  ⎿  Jev meldet: Aufgabe erledigt.
```

## Downloads
In den **[Releases](../../releases/latest)**:

| Datei | Wofür |
|---|---|
| `JevPilot-Windows.zip` | Windows-App mit Installer |
| `JevPilot-Android.apk` | Android-App: PC fernsteuern und das Handy bedienen lassen |
| `JevBridge.dll` | Mod für das Spiel ROUNDS (optional) |

> Du brauchst einen **eigenen TypeSafe API-Key**. Beim ersten Start fragt jede App danach. Der Key bleibt lokal auf deinem Gerät.

## Schnellstart
1. **Windows:** ZIP entpacken → `install.ps1` mit Rechtsklick → **Mit PowerShell ausführen** → **JevPilot** in der Windows-Suche öffnen → API-Key einfügen.
2. **Android (optional):** APK installieren → API-Key einfügen. Unter ⚙ PC-Adresse und Kopplungscode eintragen. Beides steht am PC unter ⚙ Einstellungen.
3. Prompt schreiben → **Start**. Stoppen kannst du jederzeit: am PC mit `Ctrl+Alt+X`, am Handy durch Antippen der orangen Leiste.

## Anleitungen
| | |
|---|---|
| 🖥️ [Windows-App](docs/windows.md) | Installieren, Modi, Einstellungen, Deinstallieren |
| 📱 [Android-App](docs/android.md) | Bedienungshilfe aktivieren, mit dem PC koppeln |
| 🎮 [Spiele](docs/spiele.md) | Spiele-Bibliothek, neue Spiele mit Claude Code/Codex, eigene Adapter |
| 🔫 [ROUNDS](docs/rounds.md) | Gegen Jev spielen: Mod installieren, Lobby-Ablauf |
| 🔒 [Sicherheit](docs/sicherheit.md) | Was an TypeSafe geht, Bestätigungen, Handy-Verbindung |
| 🛠️ [Selbst bauen](docs/entwickeln.md) | Python, Android, Mod, Release, Projektaufbau |

## So funktioniert es
Jev sieht keine Bilder und schreibt keinen freien Text. Er beantwortet nur Auswahl-, Bewertungs- und Ja/Nein-Fragen. Deshalb läuft jeder Schritt so ab:
1. JevPilot liest den Bildschirm: die Webseite (DOM), das Windows-Fenster (UI Automation) oder den Handy-Screen (Bedienungshilfe).
2. Daraus baut es eine Liste aller möglichen Aktionen als englische Sätze.
3. Jev wählt eine Aktion aus.
4. JevPilot führt sie aus.

Text zum Eintippen nimmt JevPilot aus deinem Prompt.

## Spiele
Jedes Spiel ist ein Adapter, also eine `.py`-Datei im `games`-Ordner. Für ein neues Spiel klickst du in der Bibliothek auf **Prompt kopieren**, fügst den Prompt in Claude Code oder Codex ein und trägst den Spielnamen ein. Mehr dazu in [Spiele](docs/spiele.md).

## Lizenz
[MIT](LICENSE). Dies ist ein privates Projekt. Es ist nicht mit TypeSafe, Landfall (ROUNDS) oder Valve verbunden.
