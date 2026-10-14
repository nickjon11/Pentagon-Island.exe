import asyncio
from pathlib import Path
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from app.rooms import room_manager
from app.geometry import VERTEX_POINTS, EDGE_PAIRS

BASE = Path(__file__).resolve().parent.parent
app = FastAPI()
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
                if not room['rolled']:
                    ok, _ = room_manager.roll_dice(code, token)
                else:
                    ok = True
                    # Keep turns bounded; build a city/settlement first, then at most two roads.
                    for kind, maximum in [('city', 1), ('settlement', 1), ('road', 2)]:
                        for _ in range(maximum):
                            options = room_manager.valid_build_locations(room, name, kind)
                            choice = room_manager.ai_build_choice(room, name, kind, options)
                            if not choice:
                                break
                            built, _ = room_manager.build(code, token, kind, choice)
                            if not built:
                                break
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
    if ok: await room_manager.broadcast_room(room_code)
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
