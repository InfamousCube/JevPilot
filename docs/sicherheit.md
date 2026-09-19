# Sicherheit & Datenschutz

- **Dein API-Key bleibt bei dir.**
  - PC: `%APPDATA%\JevPilot\config.json`.
  - Handy: privater Speicher der App.
  - Er geht nur an `api.typesafe.ai`. Er steht weder in diesem Repo noch in den Release-Dateien.
- **Was an TypeSafe geht:**
  - deine Aufgabe
  - eine Textbeschreibung des Bildschirms: Texte, Buttons, Felder
  - die möglichen Aktionen

  Screenshots gehen nicht an TypeSafe.
- **Bestätigung:** Vor riskanten Aktionen fragt Jev nach, z. B. Kaufen, Senden, Posten, Löschen oder Anrufen. Der Schalter „Vor Kaufen/Senden/Löschen fragen“ ist standardmäßig an.
- **Passwortfelder:** JevPilot fasst sie nie an.
- **Stopp:** am PC `Ctrl+Alt+X`, am Handy die orange Leiste antippen.
- **Handy-Verbindung:**
  - JevPilot am PC öffnet Port **8765** im lokalen Netz.
  - Jede Anfrage braucht den Kopplungscode.
  - Die Verbindung ist unverschlüsselt (HTTP). Nutze sie nur im eigenen WLAN.
  - Neuen Code erzeugen: `remote_token` aus `config.json` löschen und JevPilot neu starten.
- **Bedienungshilfe (Android):** Sie kann alles auf dem Bildschirm lesen. JevPilot liest nur, während eine Aufgabe läuft. Den Inhalt schickt es nur an Jev.

Du hast eine Sicherheitslücke gefunden? Bitte melde sie privat über ein [Security Advisory](../../../security/advisories/new), nicht in einem öffentlichen Issue.
