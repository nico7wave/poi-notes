# meow — campus map annotations

A desktop app for annotating a campus map with time-stamped notes, built with Python/tkinter and running via WSL on Windows.

---

## What it does

- **Map tab** — place markers on the campus map, attach text notes and images to each marker, navigate by date and hour
- **Neighbors tab** — anonymous swipe-style neighbor matching (browse, like/pass, mutual match reveals contact info)
- **Inbox tab** — view mutual matches and open a chat window

---

## Requirements

- Windows 10/11 with WSL (Ubuntu)
- Python 3.10+ inside WSL
- Python packages inside WSL: `pillow`

Install Pillow if you haven't:
```bash
pip3 install pillow
```

- The TCNJ map image at: `/mnt/c/Users/antho/Downloads/TCNJ_2017MAP.png`
  (change `IMAGE_PATH` at the bottom of `poi_notes.py` if your path differs)

---

## How to launch

### Normal launch (login screen)
Double-click **`launch.vbs`** — opens the app with no console window, goes to the login screen.

`launch.bat` does the same thing if you prefer a `.bat` file.

### Dev launch (skip login, go straight to map)
Double-click **`meow.vbs`** — bypasses login for development/testing.

---

## First-time setup

1. Run `launch.vbs`
2. Click **Create Account**, enter your name, email, and a password (8+ chars)
3. Click **Send Verification Code**
4. Enter the 6-digit code (see [Email setup](#email-verification-setup) below — if SMTP isn't configured, the code shows on screen)
5. You're in — your session is saved so you won't need to log in again on the same machine

---

## Email verification setup

The app sends a 6-digit code to verify new accounts. To enable real email delivery:

1. Go to your Google Account → **Security** → **2-Step Verification** (enable if not on)
2. Go to **App Passwords** → create one (type: Mail, device: Windows)
3. Copy the 16-character app password
4. Edit `mail_config.json`:

```json
{
  "sender": "your-actual-gmail@gmail.com",
  "password": "xxxx xxxx xxxx xxxx"
}
```

> **Without SMTP configured:** the code is displayed on screen during registration (development fallback). The app still works — email just won't be sent.

---

## Project structure

```
poi-notes/
├── poi_notes.py       — main application (all UI and logic)
├── launch.vbs         — production launcher (no console, login screen)
├── meow.vbs           — dev launcher (no console, skips login via --dev)
├── launch.bat         — batch wrapper that calls launch.vbs silently
├── mail_config.json   — Gmail SMTP credentials for email verification
├── .gitignore         — ignores accounts.json, session.json, poi_media/
│
│   (generated at runtime, not committed)
├── accounts.json      — registered user accounts (hashed passwords)
├── session.json       — saved login session
└── *_poi.json         — map annotation data per image
```

---

## Branches

| Branch | Description |
|--------|-------------|
| `antho-dev` | **Main development branch** — most up to date, has auth system + all map features |
| `map-pan` | Older branch — map pan/zoom work, no auth system (already merged into antho-dev) |
| `main` | Base branch |

---

## Auth system notes

- Passwords are hashed with PBKDF2-HMAC-SHA256 (260,000 rounds) + random salt
- Sessions are stored locally in `session.json` — logging out clears it
- `--dev` flag (used by `meow.vbs`) skips auth entirely for development

---

## Changing the map image

Edit this line near the bottom of `poi_notes.py`:

```python
IMAGE_PATH = "/mnt/c/Users/antho/Downloads/TCNJ_2017MAP.png"
```

Replace with your image path (WSL-style path, e.g. `/mnt/c/Users/you/Pictures/map.png`).

---

## Common issues

**App doesn't open at all**
- Make sure WSL is installed and `python3` works in a WSL terminal
- Run `pip3 install pillow` inside WSL

**"File not found" error on launch**
- The map image isn't at `IMAGE_PATH` — update the path in `poi_notes.py`

**Verification code never arrives**
- `mail_config.json` still has placeholder values — fill in real Gmail credentials (see above)
- Check your spam folder
- The code is shown on screen as a fallback if SMTP fails
