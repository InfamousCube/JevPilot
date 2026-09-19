# ✻ JevPilot

**Computer use with [TypeSafe](https://typesafe.ai) Jev.** Describe a task, and Jev operates your PC, your browser, your games and your Android phone.

```
› open youtube and search "lofi hip hop"
⏺ [1] Open the website youtube.com
⏺ [2] Type "lofi hip hop" into the field 'Search'
⏺ [3] Press Enter
  ⎿  Jev reports: task done.
```

<p align="center">
  <img src="docs/images/windows.png" alt="JevPilot on Windows" width="68%">
  &nbsp;
  <img src="docs/images/android.jpg" alt="JevPilot on Android" width="24%">
</p>

## Downloads
Get these from the **[latest release](../../releases/latest)**:

| File | What it is |
|---|---|
| `JevPilot-Windows.zip` | Windows app with installer |
| `JevPilot-Android.apk` | Android app: remote-control the PC and let Jev operate the phone |
| `JevBridge.dll` | Mod for the game ROUNDS (optional) |

> You need **your own TypeSafe API key**. Each app asks for it on first start and keeps it on your device.

## Quick start
1. **Windows:** unzip the file → right-click `install.ps1` → **Run with PowerShell** → open **JevPilot** from Windows search → paste your API key.
2. **Android (optional):** install the APK → paste your API key. Under ⚙, enter the PC address and pairing code. You find both on the PC under ⚙ Settings.
3. Type a prompt → **Start**. To stop, press `Ctrl+Alt+X` on the PC, or tap the orange bar on the phone.

## Guides
| | |
|---|---|
| 🖥️ [Windows app](docs/windows.md) | Install, modes, settings, uninstall |
| 📱 [Android app](docs/android.md) | Accessibility service, pairing with your PC |
| 🎮 [Games](docs/games.md) | Game library, new games with Claude Code/Codex, writing adapters |
| 🔫 [ROUNDS](docs/rounds.md) | Play against Jev: installing the mod, lobby steps |
| 🔒 [Security](docs/security.md) | What goes to TypeSafe, confirmations, phone connection |
| 🛠️ [Building](docs/building.md) | Python, Android, mod, releases, project layout |

## How it works
Jev can't see images and can't write free text. It only answers choice, score and yes/no questions. So JevPilot works step by step:
1. It reads the screen: the web page (DOM), the Windows window (UI Automation) or the phone screen (accessibility).
2. It turns that into a list of possible actions, each as an English sentence.
3. Jev picks one action.
4. JevPilot carries it out.

Text for typing comes from your prompt.

## Games
Every game is an adapter: a `.py` file in the `games` folder. To add a game, click **Copy prompt** in the library, paste the prompt into Claude Code or Codex and fill in the game name. See [Games](docs/games.md).

## License
[MIT](LICENSE). This is an unofficial hobby project. It isn't affiliated with TypeSafe, Landfall (ROUNDS) or Valve.
