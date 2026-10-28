import asyncio
import sys
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from app.rooms import room_manager
from app.geometry import VERTEX_POINTS, EDGE_PAIRS

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
app = FastAPI()
# The public GitHub Pages client makes cross-origin requests to the temporary host.
app.add_middleware(CORSMiddleware, allow_origins=[
    "https://nickjon11.github.io",
    "http://localhost:8000", "http://127.0.0.1:8000"
], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

app.mount('/static', StaticFiles(directory=BASE / 'static'), name='static')
templates = Jinja2Templates(directory=BASE / 'templates')

class PlayerRequest(BaseModel):
    player_name: str
class TokenRequest(BaseModel):
    token: str
class BuildRequest(TokenRequest):
    kind: str
    location: str
class KickRequest(TokenRequest):
    player_name: str
class RobberRequest(TokenRequest):
    tile_id: str
    victim: str | None = None
class TradeRequest(TokenRequest):
    recipient: str
    offer: dict
    request: dict
class TradeCounter(TokenRequest):
    trade_id: str
    offer: dict
    request: dict
class TradeResponse(TokenRequest):
    trade_id: str
    accept: bool
class AIDifficultyRequest(TokenRequest):
    player_name: str
    difficulty: str
class AIRequest(TokenRequest):
    player_name: str = ""

@app.get('/')
async def home(request: Request):
    return templates.TemplateResponse(request=request, name='index.html')
@app.get('/api/board-geometry')
async def board_geometry():
    return {'vertices': VERTEX_POINTS, 'edges': EDGE_PAIRS}
@app.post('/api/rooms')
async def create_room(data: PlayerRequest):
    name = data.player_name.strip()[:16]
    if not name: return {'success': False, 'error': 'Player name is required.'}
    code, token = room_manager.create_room(name)
    return {'success': True, 'room_code': code, 'player_name': name, 'token': token}
@app.get('/api/rooms/{room_code}')
async def get_room(room_code: str):
    room = room_manager.public_room(room_code)
    return {'success': True, 'room': room} if room else {'success': False, 'error': 'Room not found.'}
@app.post('/api/rooms/{room_code}/join')
async def join_room(room_code: str, data: PlayerRequest):
    name = data.player_name.strip()[:16]
    if not name: return {'success': False, 'error': 'Player name is required.'}
    token = room_manager.join_room(room_code, name)
    if not token: return {'success': False, 'error': 'Room unavailable, full, started, or name already taken.'}
    await room_manager.broadcast_room(room_code)
    return {'success': True, 'room_code': room_code.upper(), 'player_name': name, 'token': token}
@app.post('/api/rooms/{room_code}/spectate')
async def spectate(room_code: str, data: PlayerRequest):
    name = data.player_name.strip()[:16]
    token = room_manager.join_spectator(room_code, name)
    if not token: return {'success': False, 'error': 'Spectating requires an active game and a unique name.'}
    await room_manager.broadcast_room(room_code)
    return {'success': True, 'room_code': room_code.upper(), 'player_name': name, 'token': token, 'spectator': True}
@app.post('/api/rooms/{room_code}/ai/add')
async def add_ai(room_code: str, data: TokenRequest):
    ok, error = room_manager.add_ai(room_code, data.token)
    if ok: await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.post('/api/rooms/{room_code}/ai/difficulty')
async def change_ai_difficulty(room_code: str, data: AIDifficultyRequest):
    ok, error = room_manager.set_ai_difficulty(room_code, data.token, data.player_name, data.difficulty)
    if ok: await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.post('/api/rooms/{room_code}/ai/remove')
async def remove_ai(room_code: str, data: AIRequest):
    ok, error = room_manager.remove_ai(room_code, data.token, data.player_name)
    if ok: await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

_ai_tasks = {}
async def drive_ai(room_code):
    code = room_code.upper()
    room = room_manager.get_room(code)
    try:
        # One driver per room; AI actions use the same validated game methods as humans.
        while room_manager.get_room(code) is room and room['started']:
            name = room['players'][room['turn_index']]
            if name not in room['ai_players']:
                break
            await asyncio.sleep(0.55)
            if room_manager.get_room(code) is not room or not room['started'] or room['players'][room['turn_index']] != name:
                break
            token = room_manager.ai_token(room, name)
            if room['phase'] == 'setup':
                kind = room['setup_step']
                options = room_manager.valid_build_locations(room, name, kind)
                choice = room_manager.ai_build_choice(room, name, kind, options)
                if not choice:
                    room_manager.log(code, f'{name} has no legal setup placement.')
                    await room_manager.broadcast_room(code)
                    break
                ok, _ = room_manager.build(code, token, kind, choice)
            else:
                if room.get('robber_pending'):
                    tiles = [t['id'] for t in room['board']['tiles'] if t['id'] != room['robber_tile']]
                    # Prefer blocking resource tiles touching an opponent; break ties randomly.
                    tiles.sort(key=lambda t: (len(room_manager.robber_victims(room, t, name)), t != room['robber_tile']), reverse=True)
                    tile_id = tiles[0]
                    victims = room_manager.robber_victims(room, tile_id, name)
                    ok, _ = room_manager.move_robber(code, token, tile_id, victims[0] if victims else None)
                elif not room['rolled']:
                    ok, _ = room_manager.roll_dice(code, token)
                else:
                    ok = True
                    # AI uses previously recruited knights before buying new ones.
                    if room.get('knights_ready', {}).get(name, 0) and not room.get('knight_used'):
                        room_manager.play_knight(code, token)
                        await room_manager.broadcast_room(code)
                        continue
                    # Keep turns bounded; build a city/settlement first, then at most two roads.
                    difficulty = room_manager.ai_difficulty(room, name)
                    road_threat = max((room.get('road_lengths', {}).get(p, 0)
                                       for p in room['players'] if p != name), default=0)
                    if difficulty == 'Aggressive' and road_threat >= 3:
                        priorities = [('road', 3), ('settlement', 1), ('city', 1)]
                    elif difficulty in ('Hard', 'Aggressive'):
                        priorities = [('city', 1), ('settlement', 1), ('road', 2)]
                    elif difficulty == 'Easy':
                        priorities = [('settlement', 1), ('road', 1), ('city', 1)]
                    else:
                        priorities = [('city', 1), ('settlement', 1), ('road', 2)]
                    for kind, maximum in priorities:
                        for _ in range(maximum):
                            options = room_manager.valid_build_locations(room, name, kind)
                            choice = room_manager.ai_build_choice(room, name, kind, options)
                            if not choice:
                                break
                            built, _ = room_manager.build(code, token, kind, choice)
                            if not built:
                                break
                    # Recruit a knight when resources remain after construction.
                    if room_manager.can_afford(room, name, 'knight'):
                        room_manager.buy_knight(code, token)
                    ok, _ = room_manager.end_turn(code, token)
            if not ok:
                break
            await room_manager.broadcast_room(code)
    finally:
        if _ai_tasks.get(code) is asyncio.current_task():
            _ai_tasks.pop(code, None)

def schedule_ai(room_code):
    code = room_code.upper()
    room = room_manager.get_room(code)
    if not room or not room['started'] or room['players'][room['turn_index']] not in room['ai_players']:
        return
    task = _ai_tasks.get(code)
    if task and not task.done():
        return
    _ai_tasks[code] = asyncio.create_task(drive_ai(code))

@app.post('/api/rooms/{room_code}/robber/move')
async def move_robber(room_code: str, data: RobberRequest):
    async with room_manager.lock:
        ok, error = room_manager.move_robber(room_code, data.token, data.tile_id, data.victim)
    if ok:
        await room_manager.broadcast_room(room_code)
        schedule_ai(room_code)
    return {'success': ok, 'error': error}

@app.post('/api/rooms/{room_code}/trade/propose')
async def trade_propose(room_code: str, data: TradeRequest):
    async with room_manager.lock:
        ok, error = room_manager.propose_trade(room_code, data.token, data.recipient, data.offer, data.request)
    if ok:
        await room_manager.broadcast_room(room_code)
        async def expire_later():
            await asyncio.sleep(120.05)
            if room_manager.expire_trades(room_code):
                await room_manager.broadcast_room(room_code)
        asyncio.create_task(expire_later())
    outcome = None
    if ok:
        room = room_manager.get_room(room_code)
        trade = room['trades'].get(str(room['trade_serial']))
        if trade and data.recipient in room['ai_players']:
            outcome = 'counteroffer' if trade['status'] == 'pending' else trade['status']
    return {'success': ok, 'error': error, 'ai_outcome': outcome}

@app.post('/api/rooms/{room_code}/trade/counter')
async def trade_counter(room_code: str, data: TradeCounter):
    async with room_manager.lock:
        ok, error = room_manager.counter_trade(room_code, data.token, data.trade_id, data.offer, data.request)
    if ok: await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.post('/api/rooms/{room_code}/trade/respond')
async def trade_respond(room_code: str, data: TradeResponse):
    async with room_manager.lock:
        ok, error = room_manager.resolve_trade(room_code, data.token, data.trade_id, data.accept)
    await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.post('/api/rooms/{room_code}/start')
async def start_room(room_code: str, data: TokenRequest):
    ok, error = room_manager.start_room(room_code, data.token)
    if ok:
        await room_manager.broadcast_room(room_code)
        schedule_ai(room_code)
    return {'success': ok, 'error': error}
@app.post('/api/rooms/{room_code}/roll')
async def roll(room_code: str, data: TokenRequest):
    ok, error = room_manager.roll_dice(room_code, data.token)
    if ok:
        await room_manager.broadcast_room(room_code)
        schedule_ai(room_code)
    return {'success': ok, 'error': error}
@app.post('/api/rooms/{room_code}/end-turn')
async def end_turn(room_code: str, data: TokenRequest):
    ok, error = room_manager.end_turn(room_code, data.token)
    if ok:
        await room_manager.broadcast_room(room_code)
        schedule_ai(room_code)
    return {'success': ok, 'error': error}
@app.post('/api/rooms/{room_code}/knight/buy')
async def buy_knight(room_code: str, data: TokenRequest):
    async with room_manager.lock:
        ok, error = room_manager.buy_knight(room_code, data.token)
        if ok: await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.post('/api/rooms/{room_code}/knight/play')
async def play_knight(room_code: str, data: TokenRequest):
    async with room_manager.lock:
        ok, error = room_manager.play_knight(room_code, data.token)
        if ok: await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.post('/api/rooms/{room_code}/build')
async def build(room_code: str, data: BuildRequest):
    ok, error = room_manager.build(room_code, data.token, data.kind, data.location)
    if ok:
        await room_manager.broadcast_room(room_code)
        schedule_ai(room_code)
    return {'success': ok, 'error': error}

async def notify_token(room_code, token, kind):
    room = room_manager.get_room(room_code)
    if not room: return
    name = room['tokens'].get(token) or room['spectators'].get(token)
    # Caller may have already removed token; use the websocket token registry instead.
    for ws in list(room_manager.connections.get(room_code.upper(), [])):
        if getattr(ws.state, 'application_state', None) is None: continue
        if room_manager.socket_tokens.get(ws) == token:
            try: await ws.send_json({'type': kind})
            except Exception: pass

@app.post('/api/rooms/{room_code}/leave')
async def leave(room_code: str, data: TokenRequest):
    ok, error, _ = room_manager.leave_room(room_code, data.token)
    if ok:
        if not room_manager.get_room(room_code):
            for ws in list(room_manager.connections.get(room_code.upper(), [])):
                try: await ws.send_json({'type': 'session_ended'})
                except Exception: pass
        else:
            await room_manager.broadcast_room(room_code)
            room = room_manager.get_room(room_code)
            if room and room['started'] and room['players'][room['turn_index']] in room['ai_players']:
                schedule_ai(room_code)
    return {'success': ok, 'error': error}
@app.post('/api/rooms/{room_code}/end-session')
async def end_session(room_code: str, data: TokenRequest):
    ok, error = room_manager.end_session(room_code, data.token)
    if ok:
        for ws in list(room_manager.connections.get(room_code.upper(), [])):
            try: await ws.send_json({'type':'session_ended'})
            except Exception: pass
        room_manager.rooms.pop(room_code.upper(), None)
    return {'success': ok, 'error': error}
@app.post('/api/rooms/{room_code}/reset')
async def reset(room_code: str, data: TokenRequest):
    ok, error = room_manager.reset_board(room_code, data.token)
    if ok: await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}
@app.post('/api/rooms/{room_code}/kick')
async def kick(room_code: str, data: KickRequest):
    ok, error, victim_token = room_manager.kick_member(room_code, data.token, data.player_name)
    if ok:
        for ws in list(room_manager.connections.get(room_code.upper(), [])):
            if room_manager.socket_tokens.get(ws) == victim_token:
                try: await ws.send_json({'type':'kicked'})
                except Exception: pass
        await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.websocket('/ws/{room_code}')
async def websocket_room(websocket: WebSocket, room_code: str):
    token = websocket.query_params.get('token', '')
    player = await room_manager.connect(room_code, websocket, token)
    if not player: return
    room_manager.socket_tokens[websocket] = token
    await room_manager.broadcast_room(room_code)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get('type') == 'ping':
                await websocket.send_json({'type': 'pong', 'id': data.get('id')})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        room_manager.socket_tokens.pop(websocket, None)
        room_manager.disconnect(room_code, websocket)
        await room_manager.broadcast_room(room_code)
