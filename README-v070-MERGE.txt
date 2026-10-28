Pentagon Island v0.7.0 — multiplayer-first UI merge preview

BASE: Pentagon-Island.exe-main.zip (Python FastAPI/WebSocket engine).
REFERENCE: pentagon_island_v0.7.0_final(1).zip (portfolio browser-only demo).

INCLUDED:
- New collapsible Turn Details panel synchronized with server state.
- Compact sidebar inventory and special-card arrangement adapted from website.
- Website trophy asset staged for a future server-authoritative victory screen.
- Updated preview version label.

NOT YET MERGED:
- Browser-only trading and AI counteroffers (require server-side transaction validation).
- Browser-only victory modal (requires server-side winner and game-over state).
- Reconnection and public deployment (separate multiplayer milestones).

Existing FastAPI rooms, AI and WebSocket multiplayer remain the source of truth.

Install: back up ~/catan-game, then extract the contents of this archive there.
Run: source venv/bin/activate && uvicorn app.main:app --reload
