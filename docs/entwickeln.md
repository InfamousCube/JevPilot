# Selbst bauen

## Windows-App (Python 3.12)
```powershell
pip install -r requirements.txt
python app.py                                                  # direkt starten
powershell -ExecutionPolicy Bypass -File build_install.ps1     # Exe bauen + lokal installieren
```
- `--selftest out.txt` prüft Key, Browser und UI Automation ohne Oberfläche.
- Mit Store-Python beim Testen den Key per Umgebungsvariable `TYPESAFE_API_KEY` übergeben.

## Android-App
Du brauchst das Android SDK und ein JDK 17 oder neuer (z. B. `Android Studio\jbr`).
```powershell
cd android
.\gradlew.bat assembleDebug      # Debug-APK
.\gradlew.bat assembleRelease    # signiert, siehe unten
```
Für die signierte Release-APK legst du `%APPDATA%\JevPilot\android-release.properties` an:
```
storeFile=C:/pfad/zu/deinem.jks
storePassword=...
keyAlias=...
keyPassword=...
```
Keystore und Passwörter gehören nie ins Repo.

## ROUNDS-Mod
Du brauchst ROUNDS mit BepInEx 5 und das .NET SDK.
```powershell
cd ROUNDS-Bridge\JevBridge
dotnet build -c Release -p:GameDir="D:\SteamLibrary\steamapps\common\ROUNDS"
```
Kopier danach `bin\Release\JevBridge.dll` nach `ROUNDS\BepInEx\plugins\JevBridge\`.

## Release
```powershell
powershell -ExecutionPolicy Bypass -File release.ps1
```
Das Skript baut `JevPilot-Windows.zip`, `JevPilot-Android.apk` und `JevBridge.dll` nach `%TEMP%\JevPilot-release`.

## Aufbau
```
app.py                 Windows-Oberfläche (customtkinter), Worker-Thread
jevpilot/
  jev.py               TypeSafe System One Client
  agent.py             Schleife: beobachten → Jev wählt → ausführen
  browser_env.py       Playwright/Edge: DOM → Aktionsliste
  desktop_env.py       UI Automation: Fenster → Aktionsliste
  textcands.py         tippbare Textstücke aus dem Prompt
  games.py             Adapter laden, Spiele-Prompt
  cards.py             Spielkarten-Grafik der Bibliothek
  remote.py            HTTP-Schnittstelle für die Handy-App (:8765)
games/                 Spiel-Adapter
android/               Android-App (Kotlin, ohne Fremdbibliotheken)
ROUNDS-Bridge/         BepInEx-Mod für ROUNDS
installer/install.ps1  Installer aus der Release-ZIP
```
