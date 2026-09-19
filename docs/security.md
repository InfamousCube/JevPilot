# Security & privacy

- **Your API key stays on your devices.**
  - PC: `%APPDATA%\JevPilot\config.json`
  - Phone: the app's private storage
  - It is only sent to `api.typesafe.ai`. It is not in this repo and not in the release files.
- **What is sent to TypeSafe:**
  - your task
  - a text description of the screen (texts, buttons, fields)
  - the list of possible actions

  No screenshots are sent.
- **Confirmation:** Jev asks before risky actions such as buying, sending, posting, deleting or calling. The "Ask before buying/sending/deleting" switch is on by default.
- **Password fields:** JevPilot never touches them.
- **Stop:** `Ctrl+Alt+X` on the PC. On the phone, tap the orange bar.
- **Phone connection:**
  - JevPilot on the PC opens port **8765** on your local network.
  - Every request must include the pairing code.
  - The connection is not encrypted (HTTP). Only use it on your own Wi-Fi.
  - To get a new code, delete `remote_token` from `config.json` and restart JevPilot.
- **Accessibility service (Android):** it can read everything on the screen. JevPilot reads the screen only while a task is running and sends it only to Jev.

Found a vulnerability? Please report it privately through a [security advisory](../../../security/advisories/new), not in a public issue.
