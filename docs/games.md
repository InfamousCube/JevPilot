# Games

Jev can't see pixels, so every game needs an **adapter**. An adapter is a `.py` file that:
- turns the game state into text
- lists the possible moves as short English sentences

Adapters live in the `games` folder next to `JevPilot.exe` (default: `%LOCALAPPDATA%\Programs\JevPilot\games`). JevPilot loads them at startup, or when you click ↻ in the library. You don't need to rebuild the exe.

| Game | Adapter | Guide |
|---|---|---|
| ROUNDS | `games/rounds.py` + BepInEx mod `JevBridge` | [ROUNDS](rounds.md) |

## Let Claude Code or Codex build a new game
1. In the game library (PC or phone), click **Copy prompt**.
2. Paste it into [Claude Code](https://claude.com/claude-code) or Codex.
3. Replace `<PUT THE GAME NAME HERE>` with your game.
4. Let the agent build and test the adapter.
5. Put the adapter and a cover image (`<name>.jpg`) into the `games` folder.
6. Click ↻ in the library.

## Write an adapter yourself
A simple turn-based game with one move per tick:
```python
from jevpilot.games import GameAdapter

class Adapter(GameAdapter):
    name = "Snake"
    description = "Classic snake"
    hz = 10                                    # decisions per second
    image = "snake.jpg"                        # optional, else games/<file>.jpg/.png
    instructions = "Pick the move that keeps the snake alive and reaches food."

    def start(self): ...                       # connect to / focus the game
    def observe(self) -> dict: ...             # game state as a JSON-able dict
    def actions(self) -> dict[str, str]: ...   # key -> English description
    def act(self, key: str): ...               # press the keys for that move
    def stop(self): ...
```
For complex real-time games, define `run(self, jev, prompt, stop, log)` instead and drive everything yourself. See [`games/rounds.py`](../games/rounds.py) for an example with parallel Jev requests, card picks and a mod bridge.

**What Jev can answer:** Choice (up to 255 options), Score and Noul (yes/no). It doesn't generate text and doesn't see images.

**Tips**
- Put reflexes like aiming and timing in code. Let Jev make the tactical decisions.
- If the game has no readable state, build a bridge: a mod (BepInEx, Forge, …), a save file, an API or screen reading.
