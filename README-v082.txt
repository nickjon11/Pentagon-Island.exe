Pentagon Island v0.8.2 - AI Difficulty Update
Changes:
- Sticky top navigation bar for web and desktop.
- Per-AI Easy/Normal/Hard/Aggressive selection in lobby, host-only.
- Server-side difficulty locking once the match starts.
- Difficulty-sensitive AI placement and construction preferences.
- Hard/Aggressive AI evaluate and may reject unfavorable trades.
- Aggressive AI prioritizes roads when opponents threaten Longest Road.
- Desktop launcher handles windowed stdout/stderr Uvicorn logging issue.

Note: This is an incremental heuristic AI update, not a full search/planning engine.
Multiplayer still uses FastAPI/WebSockets, not WebRTC peer-to-peer.
Windows .exe must be built on Windows with build-windows.bat.
