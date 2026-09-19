# Building from source

## Windows app (Python 3.12)
```powershell
pip install -r requirements.txt
python app.py                                                  # run directly
powershell -ExecutionPolicy Bypass -File build_install.ps1     # build the exe + install locally
```
- `--selftest out.txt` checks the key, browser and UI Automation without a window.
- With the Microsoft Store Python, pass the key in the `TYPESAFE_API_KEY` environment variable when testing.

## Android app
You need the Android SDK and JDK 17+ (e.g. `Android Studio\jbr`).
```powershell
cd android
.\gradlew.bat assembleDebug      # debug APK
.\gradlew.bat assembleRelease    # signed, see below
```
For a signed release APK, create `%APPDATA%\JevPilot\android-release.properties`:
```
storeFile=C:/path/to/your.jks
storePassword=...
keyAlias=...
keyPassword=...
```
Never commit the keystore or its passwords.

## ROUNDS mod
You need ROUNDS with BepInEx 5 and the .NET SDK.
```powershell
cd ROUNDS-Bridge\JevBridge
dotnet build -c Release -p:GameDir="D:\SteamLibrary\steamapps\common\ROUNDS"
```
Copy `bin\Release\JevBridge.dll` to `ROUNDS\BepInEx\plugins\JevBridge\`.

## Release
```powershell
powershell -ExecutionPolicy Bypass -File release.ps1
```
This builds `JevPilot-Windows.zip`, `JevPilot-Android.apk` and `JevBridge.dll` into `%TEMP%\JevPilot-release`.

## Project layout
```
app.py                 Windows UI (customtkinter), worker thread
jevpilot/
  jev.py               TypeSafe System One client
  agent.py             loop: observe → Jev picks → execute
  browser_env.py       Playwright/Edge: DOM → action list
  desktop_env.py       UI Automation: window → action list
  textcands.py         typeable text snippets from the prompt
  games.py             adapter loading, game prompt
  cards.py             game card artwork for the library
  remote.py            HTTP API for the phone app (:8765)
games/                 game adapters
android/               Android app (Kotlin, no third-party libraries)
ROUNDS-Bridge/         BepInEx mod for ROUNDS
installer/install.ps1  installer inside the release zip
```
