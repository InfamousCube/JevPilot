# Builds JevPilot.exe and installs it for the current user:
#   %LOCALAPPDATA%\Programs\JevPilot\JevPilot.exe (+ games\)
#   Start menu shortcut "JevPilot" -> findable in Windows search.
# Usage: powershell -ExecutionPolicy Bypass -File build_install.ps1
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$work = Join-Path $env:TEMP "JevPilot-build"   # keep PyInstaller's 80 MB of temp files out of OneDrive
$target = Join-Path $env:LOCALAPPDATA "Programs\JevPilot"

Set-Location $src
python make_icon.py
python -m PyInstaller --noconfirm --onefile --windowed --name JevPilot --icon "$src\JevPilot.ico" `
    --add-data "$src\JevPilot.ico;." `
    --collect-all playwright --collect-all uiautomation --collect-data customtkinter `
    --hidden-import concurrent.futures --hidden-import socket --hidden-import subprocess `
    --workpath "$work\build" --distpath "$work\dist" --specpath $work "$src\app.py"
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

Get-Process JevPilot -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
New-Item -ItemType Directory -Force "$target\games" | Out-Null
Copy-Item "$work\dist\JevPilot.exe" $target -Force
Copy-Item "$src\JevPilot.ico" $target -Force
Copy-Item "$src\games\*" "$target\games\" -Force -Exclude "__pycache__"

$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\JevPilot.lnk"
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)
$s.TargetPath = "$target\JevPilot.exe"
$s.WorkingDirectory = $target
$s.IconLocation = "$target\JevPilot.ico"
$s.Description = "Computer use with TypeSafe Jev"
$s.Save()
Write-Host "Installed:  $target\JevPilot.exe"
Write-Host "Start menu: $lnk"
