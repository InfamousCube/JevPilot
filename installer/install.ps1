# Installs JevPilot for the current user (no admin needed):
#   %LOCALAPPDATA%\Programs\JevPilot\JevPilot.exe + games\
#   Start menu shortcut "JevPilot" -> findable in Windows search.
# Run from the unzipped release folder: right-click -> "Run with PowerShell",
# or: powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$src = $PSScriptRoot
$target = Join-Path $env:LOCALAPPDATA "Programs\JevPilot"

Get-Process JevPilot -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500
New-Item -ItemType Directory -Force "$target\games" | Out-Null
Copy-Item "$src\JevPilot.exe" $target -Force
# Keep games the user already added; only add/update the shipped ones.
if (Test-Path "$src\games") { Copy-Item "$src\games\*" "$target\games\" -Force -Exclude "__pycache__" }

$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\JevPilot.lnk"
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)
$s.TargetPath = "$target\JevPilot.exe"
$s.WorkingDirectory = $target
$s.IconLocation = "$target\JevPilot.exe,0"
$s.Description = "Computer use with TypeSafe Jev"
$s.Save()
Write-Host "JevPilot installed: $target"
Write-Host "Find it in the Start menu / Windows search: JevPilot"
