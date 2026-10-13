import asyncio
import secrets
import string
import time
from fastapi import WebSocket
from app.board import generate_board, ROWS

# Prototype board graph; server validates every build location.
from app.geometry import VERTICES, EDGES

COLORS = ['red', 'blue', 'green', 'yellow']

class RoomManager:
    def __init__(self):
        self.rooms = {}
        self.connections = {}
        self.lock = asyncio.Lock()

    def generate_room_code(self):
        alphabet = string.ascii_uppercase + string.digits
        while True:
            code = ''.join(secrets.choice(alphabet) for _ in range(6))
            if code not in self.rooms:
                return code

    def create_room(self, player_name):
        code = self.generate_room_code()
        token = secrets.token_urlsafe(24)
        self.rooms[code] = {
            'host': player_name, 'players': [player_name], 'started': False,
            'tokens': {token: player_name}, 'turn_index': 0, 'turn_number': 1,
            'rolled': False, 'last_roll': None, 'victory_points': {player_name: 2},
            'turns_taken': {player_name: 0}, 'log': [], 'road_owner': None,
            'army_owner': None, 'resources': {player_name: 5},
            'connections': {}, 'buildings': {}, 'roads': {},
            'board': generate_board(),
        }
        self.log(code, f'{player_name} created the room.')
        return code, token

    def join_room(self, room_code, player_name):
        code = room_code.upper()
        room = self.rooms.get(code)
        if not room or room['started'] or len(room['players']) >= 4 or player_name in room['players']:
            return None
        token = secrets.token_urlsafe(24)
        room['tokens'][token] = player_name
        room['players'].append(player_name)
        room['victory_points'][player_name] = 2
        room['turns_taken'][player_name] = 0
        room['resources'][player_name] = 5
        self.log(code, f'{player_name} joined the room.')
        return token

    def room_exists(self, room_code):
        return room_code.upper() in self.rooms

    def get_room(self, room_code):
        return self.rooms.get(room_code.upper())

    def player_for_token(self, code, token):
        room = self.get_room(code)
        return room['tokens'].get(token) if room else None

    def log(self, code, message):
        room = self.get_room(code)
        if room:
            room['log'].append({'time': time.strftime('%H:%M:%S'), 'message': message})
            room['log'] = room['log'][-100:]

    def public_room(self, code):
        room = self.get_room(code)
        if not room:
            return None
        return {
            'host': room['host'], 'players': room['players'], 'started': room['started'],
            'turn_index': room['turn_index'], 'turn_number': room['turn_number'],
            'current_player': room['players'][room['turn_index']],
            'rolled': room['rolled'], 'last_roll': room['last_roll'],
            'victory_points': room['victory_points'], 'turns_taken': room['turns_taken'],
            'resource_counts': room['resources'], 'log': room['log'],
            'road_owner': room['road_owner'], 'army_owner': room['army_owner'],
            'connected': {p: bool(room['connections'].get(p)) for p in room['players']},
            'colors': {p: COLORS[i] for i, p in enumerate(room['players'])},
            'buildings': room['buildings'], 'roads': room['roads'],
            'board': room['board'],
        }

    async def connect(self, code: str, websocket: WebSocket, token: str):
        code = code.upper()
        player = self.player_for_token(code, token)
        if not player:
            await websocket.close(code=1008)
            return None
        await websocket.accept()
        self.connections.setdefault(code, []).append(websocket)
        self.rooms[code]['connections'].setdefault(player, set()).add(websocket)
        return player

    def disconnect(self, code: str, websocket: WebSocket):
        code = code.upper()
        if websocket in self.connections.get(code, []):
            self.connections[code].remove(websocket)
        room = self.get_room(code)
        if room:
            for conns in room['connections'].values():
                conns.discard(websocket)

    async def broadcast_room(self, code: str):
        code = code.upper()
        room = self.public_room(code)
        if not room:
            return
        for websocket in list(self.connections.get(code, [])):
            try:
                await websocket.send_json({'type': 'room_update', 'room_code': code, 'room': room})
            except Exception:
                self.disconnect(code, websocket)

    def start_room(self, code, token):
        room = self.get_room(code)
        if not room or room['tokens'].get(token) != room['host']:
            return False, 'Only the host can start the game.'
        if room['started']:
            return False, 'Game already started.'
        if len(room['players']) < 2:
            return False, 'At least two players are required.'
        room['started'] = True
        self.log(code, 'Game started!')
        return True, None

    def roll_dice(self, code, token):
        room = self.get_room(code)
        if not room or not room['started']:
            return False, 'Game is not running.'
        player = room['tokens'].get(token)
        if player != room['players'][room['turn_index']]:
            return False, 'Not your turn.'
        if room['rolled']:
            return False, 'You already rolled this turn.'
        import random
        dice = [random.randint(1, 6), random.randint(1, 6)]
        room['rolled'] = True
        room['last_roll'] = dice
        self.log(code, f'{player} rolled {sum(dice)} ({dice[0]} + {dice[1]}).')
        if sum(dice) == 7:
            self.log(code, 'Seven rolled! Robber/discard rules coming in the next phase.')
        return True, None

    def build(self, code, token, kind, location):
        room = self.get_room(code)
        if not room or not room['started']:
            return False, 'Game is not running.'
        player = room['tokens'].get(token)
        if player != room['players'][room['turn_index']]:
            return False, 'Wait for your turn.'
        if not room['rolled']:
            return False, 'Roll the dice before building.'
        valid = VERTICES if kind == 'settlement' else EDGES if kind == 'road' else None
        if valid is None or location not in valid:
            return False, 'Invalid construction location.'
        target = room['buildings'] if kind == 'settlement' else room['roads']
        if location in target:
            return False, 'This location is already occupied.'
        target[location] = player
        if kind == 'settlement':
            room['victory_points'][player] += 1
        self.log(code, f'{player} built a {kind} at {location}.')
        return True, None

    def end_turn(self, code, token):
        room = self.get_room(code)
        if not room or not room['started']:
            return False, 'Game is not running.'
        player = room['tokens'].get(token)
        if player != room['players'][room['turn_index']]:
            return False, 'Not your turn.'
        if not room['rolled']:
            return False, 'Roll the dice before ending your turn.'
        room['turns_taken'][player] += 1
        room['turn_index'] = (room['turn_index'] + 1) % len(room['players'])
        room['turn_number'] += 1
        room['rolled'] = False
        room['last_roll'] = None
        self.log(code, f"Turn passed to {room['players'][room['turn_index']] }.")
        return True, None

room_manager = RoomManager()
