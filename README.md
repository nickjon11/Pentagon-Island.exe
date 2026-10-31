# Pentagon Island v1.0.0

**A retro-inspired multiplayer strategy board game for Windows and the web.**

Pentagon Island is a Catan-inspired strategy game built with Python, FastAPI, WebSockets, HTML, CSS, and JavaScript. It combines a classic Windows 98-inspired interface with multiplayer rooms, resource management, trading, AI opponents, and island-based strategy gameplay.

## Download and Install

The Windows version is distributed as a standalone installer.

**[Download Pentagon Island from GitHub Releases](https://github.com/nickjon11/Pentagon-Island.exe/releases)**

1. Download `PentagonIsland-Setup-v1.0.0.exe` from the latest release.
2. Run the installer and select an installation directory.
3. Optionally create a desktop shortcut.
4. Launch Pentagon Island from the Start Menu or desktop.

Players do not need to install Python, configure WSL, or run a batch file.

## Gameplay Features

- Multiplayer rooms with six-character room codes.
- Up to four players, with support for human and AI opponents.
- Randomized island terrain and resource collection.
- Roads, settlements, and cities.
- Dice rolls and turn-based gameplay.
- Player-to-player trading and AI trading.
- Robber mechanics, Knight cards, Longest Road, and Largest Army.
- Victory point tracking and a 10-point victory target.
- Spectator support and multiplayer game-state synchronization.
- Light and dark themes with a retro Windows-inspired interface.

## Multiplayer

### Local Multiplayer

The Windows desktop application starts its own local FastAPI game server when launched.

Players connected to an accessible game server can create or join rooms using room codes.

### Internet Multiplayer Preview

The repository also includes an experimental internet-hosting utility using Cloudflare Tunnel.

This allows a host to expose a temporary game server address that can be shared with browser players on other networks.

The current internet-hosting utility requires `cloudflared` to be installed separately. Fully automatic internet hosting from the Windows application has not yet been verified.

Internet multiplayer is still considered a preview feature and requires further cross-network testing.

## Running from Source

For development on Windows, Linux, or macOS:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

On Windows, activate the environment with `.venv\Scripts\activate` instead.

Open `http://127.0.0.1:8000` in your browser.

Room state is stored in memory and resets when the server restarts. Use a single Uvicorn worker.

### Experimental Internet Hosting

Install Cloudflare Tunnel (`cloudflared`) and make it available on your PATH.

Then, from the project root:

```bash
python -m desktop.host_internet
```

The terminal displays a temporary HTTPS host URL. Share that address with other players, who can then use the game's room code to join.

Closing the hosting process ends the hosted session.

## Building the Windows Installer

The repository uses GitHub Actions to automate Windows packaging.

The build process:

1. Installs the Python build dependencies.
2. Packages the desktop application using PyInstaller.
3. Installs Inno Setup 6.
4. Compiles the Windows setup executable.
5. Uploads the installer as a GitHub Actions artifact.

To build it, open the repository's **Actions** tab and run **Build Pentagon Island v1.0.0 Installer**.

The generated installer can then be published through GitHub Releases.

## Current Limitations

- Internet multiplayer hosting requires additional testing.
- The standalone desktop launcher currently starts a local server; automatic Cloudflare Tunnel integration is not yet confirmed.
- Game sessions are not persisted after a server restart.
- Hosting requires the server process to remain active.
- Unsigned Windows installers may display a Microsoft SmartScreen warning.

## Technology

- **Backend:** Python, FastAPI, Uvicorn
- **Multiplayer:** WebSockets
- **Frontend:** HTML, CSS, JavaScript
- **Windows Desktop:** pywebview
- **Packaging:** PyInstaller
- **Installer:** Inno Setup 6
- **Automation:** GitHub Actions
- **Optional Internet Hosting:** Cloudflare Tunnel

## Version

**Current version:** v1.0.0 — Windows Installer & Internet Multiplayer Preview

## Developer

Developed by Jonathan Lachman, 2026.

Pentagon Island is an independent, Catan-inspired strategy game project.
