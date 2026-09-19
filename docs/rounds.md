# ROUNDS

Play ROUNDS against Jev. Jev moves, jumps, shoots, blocks and picks a card after every round. The mod handles aiming and block timing, and Jev makes about 7 decisions per second.

## Setup (once)
1. Download [BepInEx 5 (Windows x64)](https://github.com/BepInEx/BepInEx/releases) and unzip it into the ROUNDS folder.
   To find the folder, right-click ROUNDS in Steam → Manage → Browse local files.
2. Start ROUNDS once, then close it. This lets BepInEx create its folders.
3. Copy `JevBridge.dll` from the [releases](../../../releases/latest) to `ROUNDS\BepInEx\plugins\JevBridge\`.

## Play
1. In JevPilot, select **ROUNDS** on the left and press **Start**. If ROUNDS isn't running, JevPilot starts it through Steam.
2. In the game, do this in order:
   1. Choose **Local** → **Versus**.
   2. Press **Space** to join.
   3. Press **B** to add a bot. Jev takes over the bot.
   4. Press **Space** again to ready up.
3. Stop with `Ctrl+Alt+X` or the Stop button. The normal bot AI then takes over again.

To make Jev control a specific player, write e.g. `player 1` in the prompt.

The mod only acts in local games, never online.

## Troubleshooting
| Message | Fix |
|---|---|
| "ROUNDS is running without JevBridge" | BepInEx or JevBridge is missing, or ROUNDS was already running when you started. Close ROUNDS and start it again. |
| "Waiting for a bot – press B in the lobby" | Add a bot in the lobby with **B**. |
