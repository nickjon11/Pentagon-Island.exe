# Pentagon Island — multiplayer game screen prototype

A retro game interface with FastAPI room creation, authenticated host game start, WebSocket room synchronization, dice rolls, turn passing, and a scrollable log. The island illustration is **decorative** in this phase; roads, settlements, trading, robber, real resource accounting, spectators, and multi-player ping broadcasting are not implemented yet. The 'Cards' column for a 7 uses placeholder resource counts until resource mechanics are built.

## Run (WSL / Linux)

```bash
cd ~/catan-game
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 in two tabs, create a room, join with a second name, and start the game. Room state is in memory and resets on server restart. Do not use multiple Uvicorn workers.

## Installing into your existing project

Back up `app/main.py`, `app/rooms.py`, `templates/index.html`, `static/js/main.js`, and `static/css/style.css`. Copy the provided project files into the matching paths. This version updates the HTTP start endpoint to require a per-player token; you must update both frontend and backend together.

## Known limitations

- The illustration is a static background, not an interactive board.
- Ping is measured browser-to-server for the local player; other connected players display `Online` until we add server aggregation.
- Card counts and victory points are prototype values.
- Room and session state is not persisted across restarts.
