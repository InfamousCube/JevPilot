# Builds everything that goes into a GitHub release, into %TEMP%\JevPilot-release:
#   JevPilot-Windows.zip   JevPilot.exe + games\ + install.ps1
#   JevPilot-Android.apk   signed release build (needs %APPDATA%\JevPilot\android-release.properties)
#   JevBridge.dll          ROUNDS BepInEx plugin (needs ROUNDS + BepInEx 5 installed)
# Usage: powershell -ExecutionPolicy Bypass -File release.ps1
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$work = Join-Path $env:TEMP "JevPilot-build"
$out = Join-Path $env:TEMP "JevPilot-release"
Remove-Item $out -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force "$out\zip\games" | Out-Null

Set-Location $src
python make_icon.py
python -m PyInstaller --noconfirm --onefile --windowed --name JevPilot --icon "$src\JevPilot.ico" `
    --add-data "$src\JevPilot.ico;." `
    --collect-all playwright --collect-all uiautomation --collect-data customtkinter `
    --hidden-import concurrent.futures --hidden-import socket --hidden-import subprocess `
    --workpath "$work\build" --distpath "$work\dist" --specpath $work "$src\app.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
Copy-Item "$work\dist\JevPilot.exe" "$out\zip\"
Copy-Item "$src\games\*.py" "$out\zip\games\"
Copy-Item "$src\installer\install.ps1" "$out\zip\"
Compress-Archive -Path "$out\zip\*" -DestinationPath "$out\JevPilot-Windows.zip"

$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
Push-Location "$src\android"
.\gradlew.bat --project-cache-dir "$env:TEMP\JevPilotMobile-build\.gradle" assembleRelease -q
if ($LASTEXITCODE -ne 0) { throw "Android build failed" }
Pop-Location
Copy-Item "$env:TEMP\JevPilotMobile-build\app\outputs\apk\release\app-release.apk" "$out\JevPilot-Android.apk"

# Find ROUNDS in any Steam library (same lookup as games/rounds.py).
$steam = (Get-ItemProperty "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
$libs = @($steam)
$vdf = Join-Path "$steam" "steamapps\libraryfolders.vdf"
if (Test-Path $vdf) {
    $libs += (Select-String -Path $vdf -Pattern '"path"\s+"([^"]+)"').Matches | ForEach-Object { $_.Groups[1].Value -replace '\\\\', '\' }
}
$gameDir = $libs | Where-Object { $_ } | ForEach-Object { Join-Path $_ "steamapps\common\ROUNDS" } |
    Where-Object { Test-Path (Join-Path $_ "ROUNDS.exe") } | Select-Object -First 1

Push-Location "$src\ROUNDS-Bridge\JevBridge"
if ($gameDir) { dotnet build -c Release "-p:GameDir=$gameDir" } else { $LASTEXITCODE = 1 }
if ($LASTEXITCODE -eq 0) { Copy-Item "bin\Release\JevBridge.dll" $out } else { Write-Warning "JevBridge not built" }
Pop-Location

Remove-Item "$out\zip" -Recurse -Force
Get-ChildItem $out | Format-Table Name, Length
