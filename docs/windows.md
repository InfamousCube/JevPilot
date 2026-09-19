# Windows-App

## Installieren
1. `JevPilot-Windows.zip` aus den [Releases](../../../releases/latest) laden und entpacken.
2. `install.ps1` mit Rechtsklick → **Mit PowerShell ausführen**.
   - JevPilot landet in `%LOCALAPPDATA%\Programs\JevPilot`.
   - Im Startmenü erscheint ein Eintrag, also findest du es in der Windows-Suche.
   - Admin-Rechte brauchst du nicht.
3. **JevPilot** starten und deinen TypeSafe API-Key einfügen. Ohne Key geht es nicht weiter.

> Windows SmartScreen warnt eventuell, weil die Exe nicht signiert ist. Dann „Weitere Informationen“ → „Trotzdem ausführen“.

Voraussetzungen: Windows 10/11 und Microsoft Edge (ist normalerweise vorinstalliert). JevPilot steuert den Browser über Edge.

## Benutzen
| Element | Funktion |
|---|---|
| **Modus** | **Auto**: Jev entscheidet. **Browser**: eigenes Edge-Profil. **PC**: Windows-Programme. |
| **Prompt-Feld** | Aufgabe, z. B. `öffne youtube und suche "lofi hip hop"`. Text in Anführungszeichen tippt Jev genau so ein. `Ctrl+Enter` startet. |
| **Vor Kaufen/Senden/Löschen fragen** | Vor riskanten Aktionen fragt Jev nach. Die Frage kommt am PC und in der Handy-App. |
| **Schritte** | Höchstzahl der Aktionen pro Aufgabe. |
| **Spiele** | Spiel wählen, dann Start. Siehe [Spiele](spiele.md). |
| **⚙ Einstellungen** | API-Key ändern. Außerdem PC-Adresse und Kopplungscode für die Handy-App. |

**Stopp überall:** `Ctrl+Alt+X`. Während Jev den PC steuert, zeigt oben eine orange Leiste, was er gerade tut.

## Daten
| Datei | Inhalt |
|---|---|
| `%APPDATA%\JevPilot\config.json` | API-Key und Kopplungscode, nur lokal |
| `%LOCALAPPDATA%\JevPilot\browser-profile` | Edge-Profil von JevPilot, getrennt von deinem normalen Edge |

## Deinstallieren
Diese drei Dinge löschen: `%LOCALAPPDATA%\Programs\JevPilot`, `%APPDATA%\JevPilot` und den Startmenü-Eintrag `JevPilot`.
