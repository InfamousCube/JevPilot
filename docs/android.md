# Android-App

Die App hat zwei Tabs:
- **PC steuern:** schickt Aufgaben an JevPilot auf deinem PC und zeigt das Protokoll live.
- **Handy steuern:** Jev bedient das Handy selbst.

## Installieren (ab Android 11)
1. `JevPilot-Android.apk` aus den [Releases](../../../releases/latest) aufs Handy laden.
2. Datei öffnen und die Installation aus dieser Quelle erlauben.
3. JevPilot öffnen und deinen TypeSafe API-Key einfügen. Er bleibt nur auf dem Handy.

## Handy steuern einrichten
Jev liest den Bildschirm über die Android-**Bedienungshilfe** und tippt dann selbst.
1. Im Tab „Handy steuern“ auf **Aktivieren** tippen.
2. Bedienungshilfen → Installierte (oder heruntergeladene) Apps → **JevPilot** → einschalten.
3. Kommt die Meldung **„Eingeschränkte Einstellung“**:
   1. Einstellungen → Apps → JevPilot → ⋮ (oben rechts) → **Eingeschränkte Einstellungen zulassen**.
   2. Danach die Bedienungshilfe nochmal einschalten.

Während Jev arbeitet, siehst du oben eine **orange Leiste**. Antippen stoppt ihn sofort. Vor riskanten Aktionen (Senden, Kaufen, Anrufen, Löschen) zeigt Jev eine Karte zum Bestätigen.

## Mit dem PC koppeln
1. Am PC in JevPilot **⚙ Einstellungen** öffnen. Dort stehen **PC-Adresse** (z. B. `192.168.178.20:8765`) und **Kopplungscode**.
2. Beides in der Handy-App unter **⚙** eintragen.
3. Handy und PC müssen im **selben WLAN** sein.
4. Beim ersten Start fragt die Windows-Firewall nach. JevPilot für **private Netzwerke** erlauben.

Es geht auch über USB ohne WLAN. Dafür brauchst du USB-Debugging (Entwickleroptionen):
```
adb reverse tcp:8765 tcp:8765
```
Die App versucht danach automatisch `127.0.0.1:8765`.

Sobald alles passt, steht oben im Tab **● Verbunden mit <PC-Name>**.
