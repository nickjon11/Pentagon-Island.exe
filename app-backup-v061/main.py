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

@app.get('/')
async def home(request: Request):
    return templates.TemplateResponse(request=request, name='index.html')

@app.get('/api/board-geometry')
async def board_geometry():
    return {'vertices': VERTEX_POINTS, 'edges': EDGE_PAIRS}

@app.post('/api/rooms')
async def create_room(data: PlayerRequest):
    name = data.player_name.strip()[:16]
    if not name:
        return {'success': False, 'error': 'Player name is required.'}
    code, token = room_manager.create_room(name)
    return {'success': True, 'room_code': code, 'player_name': name, 'token': token}

@app.get('/api/rooms/{room_code}')
async def get_room(room_code: str):
    room = room_manager.public_room(room_code)
    return {'success': True, 'room': room} if room else {'success': False, 'error': 'Room not found.'}

@app.post('/api/rooms/{room_code}/join')
async def join_room(room_code: str, data: PlayerRequest):
    name = data.player_name.strip()[:16]
    if not name:
        return {'success': False, 'error': 'Player name is required.'}
    token = room_manager.join_room(room_code, name)
    if not token:
        return {'success': False, 'error': 'Room unavailable, full, started, or name already taken.'}
    await room_manager.broadcast_room(room_code)
    return {'success': True, 'room_code': room_code.upper(), 'player_name': name, 'token': token}

@app.post('/api/rooms/{room_code}/start')
async def start_room(room_code: str, data: TokenRequest):
    ok, error = room_manager.start_room(room_code, data.token)
    if ok:
        await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.post('/api/rooms/{room_code}/roll')
async def roll(room_code: str, data: TokenRequest):
    ok, error = room_manager.roll_dice(room_code, data.token)
    if ok:
        await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.post('/api/rooms/{room_code}/end-turn')
async def end_turn(room_code: str, data: TokenRequest):
    ok, error = room_manager.end_turn(room_code, data.token)
    if ok:
        await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.post('/api/rooms/{room_code}/build')
async def build(room_code: str, data: BuildRequest):
    ok, error = room_manager.build(room_code, data.token, data.kind, data.location)
    if ok:
        await room_manager.broadcast_room(room_code)
    return {'success': ok, 'error': error}

@app.websocket('/ws/{room_code}')
async def websocket_room(websocket: WebSocket, room_code: str):
    token = websocket.query_params.get('token', '')
    player = await room_manager.connect(room_code, websocket, token)
    if not player:
        return
    await room_manager.broadcast_room(room_code)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get('type') == 'ping':
                await websocket.send_json({'type': 'pong', 'id': data.get('id')})
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        room_manager.disconnect(room_code, websocket)
        await room_manager.broadcast_room(room_code)
