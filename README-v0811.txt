PENTAGON ISLAND v0.8.1.1 - Web/App Client Test

WHAT IS INCLUDED
- Existing v0.7.0 game, lobby, AI and FastAPI multiplayer logic.
- Responsive game-board width constrained by both viewport width and height.
- Matching terrain/construction SVG coordinate geometry.
- Updated visible version label and browser title.
- Desktop test launcher that starts the bundled local FastAPI server only while the app is open.
- Windows PyInstaller build script (build-windows.bat).

WEB DEVELOPMENT
  pip install -r requirements.txt
  uvicorn app.main:app --reload
  Open http://127.0.0.1:8000

WINDOWS DESKTOP BUILD (run on Windows with Python 3.11-3.13)
  build-windows.bat
  The resulting dist/PentagonIsland.exe can run without Python installed.
  Building the exe requires Python; PLAYERS do not need Python.
  Build not performed in this environment.

IMPORTANT NETWORKING LIMITATIONS
- This is a WEB/APP CLIENT TEST, not a completed WebRTC P2P release.
- Existing room-code multiplayer still depends on a shared FastAPI server.
- Desktop test launcher binds only to localhost, so the .exe runs a local
  single-computer test, not an internet-accessible P2P host.
- Joining remotely requires a reachable game server; a room code alone
  cannot connect two independent local game servers.
- WebRTC signaling, NAT traversal, TURN fallback, host-authoritative
  browser game state, and cross-client P2P sync remain future work.
- The executable is NOT precompiled in this ZIP; build-windows.bat produces it.
