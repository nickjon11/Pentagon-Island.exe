import asyncio
import random
import secrets
import string
import time
from fastapi import WebSocket
from app.board import generate_board, ROWS

# Prototype board graph; server validates every build location.
from app.geometry import VERTICES, EDGES, EDGE_PAIRS as EDGES_LIST, HEX_VERTICES

COLORS = ['red', 'blue', 'green', 'yellow']
RESOURCE_TYPES = ('wood', 'brick', 'wheat', 'wool', 'ore')
TERRAIN_RESOURCE = {'forest': 'wood', 'hills': 'brick', 'wheat': 'wheat',
                    'pasture': 'wool', 'mountain': 'ore'}
COSTS = {'road': {'wood': 1, 'brick': 1},
         'settlement': {'wood': 1, 'brick': 1, 'wheat': 1, 'wool': 1},
         'city': {'wheat': 2, 'ore': 3}}

def empty_inventory():
    return {resource: 0 for resource in RESOURCE_TYPES}


class RoomManager:
    def __init__(self):
        self.rooms = {}
        self.connections = {}
        self.lock = asyncio.Lock()
        self.socket_tokens = {}
        self.socket_tokens = {}

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
            'host': player_name, 'players': [player_name], 'ai_players': [], 'started': False,
            'tokens': {token: player_name}, 'spectators': {}, 'departed': [], 'turn_index': 0, 'turn_number': 1,
            'rolled': False, 'last_roll': None, 'victory_points': {player_name: 0},
            'turns_taken': {player_name: 0}, 'log': [], 'road_owner': None,
            'army_owner': None, 'resources': {player_name: empty_inventory()},
            'connections': {}, 'buildings': {}, 'roads': {}, 'cities': [],
            'board': generate_board(), 'phase': 'lobby', 'setup_order': [],
            'setup_index': 0, 'setup_step': 'settlement', 'setup_vertex': None,
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
        room['victory_points'][player_name] = 0
        room['turns_taken'][player_name] = 0
        room['resources'][player_name] = empty_inventory()
        self.log(code, f'{player_name} joined the room.')
        return token

    def add_ai(self, code, token):
        room = self.get_room(code)
        if not self.authorized_host(code, token):
            return False, 'Only the host can manage AI players.'
        if room['started']:
            return False, 'AI players can only be added in the lobby.'
        if len(room['players']) >= 4:
            return False, 'The room is full (maximum four players).'
        name = next((f'Computer {i} (AI)' for i in range(1, 5)
                     if f'Computer {i} (AI)' not in room['players']), None)
        if not name:
            return False, 'No AI slots available.'
        room['players'].append(name)
        room['ai_players'].append(name)
        room['victory_points'][name] = 0
        room['turns_taken'][name] = 0
        room['resources'][name] = empty_inventory()
        self.log(code, f'{name} joined the room.')
        return True, None

    def remove_ai(self, code, token, name):
        room = self.get_room(code)
        if not self.authorized_host(code, token):
            return False, 'Only the host can manage AI players.'
        if room['started']:
            return False, 'Reset the board before removing an AI player.'
        if name not in room['ai_players']:
            return False, 'AI player not found.'
        room['ai_players'].remove(name)
        room['players'].remove(name)
        for key in ('victory_points', 'turns_taken', 'resources'):
            room[key].pop(name, None)
        self.log(code, f'{name} was removed.')
        return True, None

    def ai_token(self, room, name):
        # Tokens are internal; never exposed to clients.
        for token, player in room['tokens'].items():
            if player == name:
                return token
        token = secrets.token_urlsafe(24)
        room['tokens'][token] = name
        return token

    def ai_build_choice(self, room, player, kind, locations):
        if not locations:
            return None
        if kind == 'city':
            return max(locations, key=lambda v: self.ai_vertex_score(room, int(v[1:])))
        if kind == 'settlement':
            return max(locations, key=lambda v: self.ai_vertex_score(room, int(v[1:])) + random.random() * 0.1)
        # Prefer extending towards an unoccupied, productive intersection.
        occupied = room['buildings']
        def score(edge):
            a, b = EDGES_LIST[int(edge[1:])]
            return max((self.ai_vertex_score(room, v) if f'v{v}' not in occupied else 0)
                       for v in (a, b)) + random.random() * 0.5
        return max(locations, key=score)

    def ai_vertex_score(self, room, vertex):
        weights = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
        return sum(weights.get(tile['number'], 0)
                   for tile, vertices in zip(room['board']['tiles'], HEX_VERTICES)
                   if vertex in vertices and tile['terrain'] in TERRAIN_RESOURCE)

    def join_spectator(self, code, name):
        room = self.get_room(code)
        if not room or not room['started'] or not name or name in room['players'] or name in room['spectators'].values():
            return None
        token = secrets.token_urlsafe(24)
        room['spectators'][token] = name
        self.log(code, f'{name} is spectating.')
        return token

    def spectator_for_token(self, code, token):
        room = self.get_room(code)
        return room['spectators'].get(token) if room else None

    def authorized_host(self, code, token):
        room = self.get_room(code)
        return bool(room and room['tokens'].get(token) == room['host'])

    def leave_room(self, code, token):
        room = self.get_room(code)
        if not room:
            return False, 'Room not found.', None
        if token in room['spectators']:
            name = room['spectators'].pop(token)
            self.log(code, f'{name} stopped spectating.')
            return True, None, name
        name = room['tokens'].pop(token, None)
        if not name:
            return False, 'Not a room member.', None
        if room['started'] and room['phase'] == 'setup':
            room['tokens'][token] = name
            return False, 'Leaving during initial placement is unavailable. Ask the host to reset or end the session.', None
        if room['started']:
            # Keep placed structures and historical scores, but skip resigned players.
            room['departed'].append(name)
            if room['host'] == name:
                candidates = [p for p in room['players'] if p not in room['departed']]
                if candidates: room['host'] = candidates[0]
            if room['players'][room['turn_index']] == name and room['phase'] == 'play':
                for offset in range(1, len(room['players']) + 1):
                    index = (room['turn_index'] + offset) % len(room['players'])
                    if room['players'][index] not in room['departed']:
                        room['turn_index'] = index
                        break
                room['rolled'] = False
                room['last_roll'] = None
            self.log(code, f'{name} left the match.')
            return True, None, name
        room['players'].remove(name)
        for key in ('victory_points', 'turns_taken', 'resources'):
            room[key].pop(name, None)
        room['connections'].pop(name, None)
        if not room['players']:
            self.rooms.pop(code.upper(), None)
            return True, None, name
        if room['host'] == name:
            room['host'] = room['players'][0]
        self.log(code, f'{name} left the room.')
        return True, None, name

    def end_session(self, code, token):
        if not self.authorized_host(code, token):
            return False, 'Only the host can end the session.'
        return True, None

    def reset_board(self, code, token):
        if not self.authorized_host(code, token):
            return False, 'Only the host can reset the board.'
        room = self.get_room(code)
        for name in room['departed']:
            if name in room['players']: room['players'].remove(name)
            for key in ('victory_points', 'turns_taken', 'resources'):
                room[key].pop(name, None)
        room.update(board=generate_board(), started=False, phase='lobby', departed=[],
                    turn_index=0, turn_number=1, rolled=False, last_roll=None,
                    buildings={}, roads={}, cities=[], setup_order=[],
                    setup_index=0, setup_step='settlement', setup_vertex=None,
                    road_owner=None, army_owner=None)
        for name in room['players']:
            room['resources'][name] = empty_inventory()
            room['victory_points'][name] = 0
            room['turns_taken'][name] = 0
        self.log(code, 'Host reset the board. Waiting for a new game.')
        return True, None

    def kick_member(self, code, token, name):
        if not self.authorized_host(code, token):
            return False, 'Only the host can kick members.', None
        room = self.get_room(code)
        if name == room['host']:
            return False, 'Host cannot kick themselves.', None
        spectator_token = next((t for t, n in room['spectators'].items() if n == name), None)
        if spectator_token:
            room['spectators'].pop(spectator_token)
            self.log(code, f'{name} was removed by the host.')
            return True, None, spectator_token
        if name in room['ai_players']:
            ok, error = self.remove_ai(code, token, name)
            return ok, error, None
        if name not in room['players']:
            return False, 'Member not found.', None
        if room['started']:
            return False, 'Active players cannot be kicked mid-match. Reset the board first.', None
        victim_token = next((t for t, n in room['tokens'].items() if n == name), None)
        if victim_token:
            room['tokens'].pop(victim_token)
        room['players'].remove(name)
        for key in ('victory_points', 'turns_taken', 'resources'):
            room[key].pop(name, None)
        self.log(code, f'{name} was removed by the host.')
        return True, None, victim_token

    def join_spectator(self, code, name):
        room = self.get_room(code)
        if not room or not room['started'] or not name or name in room['players'] or name in room['spectators'].values():
            return None
        token = secrets.token_urlsafe(24)
        room['spectators'][token] = name
        self.log(code, f'{name} is spectating.')
        return token

    def spectator_for_token(self, code, token):
        room = self.get_room(code)
        return room['spectators'].get(token) if room else None

    def authorized_host(self, code, token):
        room = self.get_room(code)
        return bool(room and room['tokens'].get(token) == room['host'])

    def leave_room(self, code, token):
        room = self.get_room(code)
        if not room:
            return False, 'Room not found.', None
        if token in room['spectators']:
            name = room['spectators'].pop(token)
            self.log(code, f'{name} stopped spectating.')
            return True, None, name
        name = room['tokens'].pop(token, None)
        if not name:
            return False, 'Not a room member.', None
        if room['started']:
            # Active game membership is retained to preserve ownership, turn order,
            # and scoring. The disconnected player may rejoin only after reset.
            room['tokens'][token] = name
            return False, 'Players cannot leave an active match individually. Ask the host to reset or end the session.', None
        room['players'].remove(name)
        for key in ('victory_points', 'turns_taken', 'resources'):
            room[key].pop(name, None)
        room['connections'].pop(name, None)
        if not room['players']:
            self.rooms.pop(code.upper(), None)
            return True, None, name
        if room['host'] == name:
            room['host'] = room['players'][0]
        self.log(code, f'{name} left the room.')
        return True, None, name

    def end_session(self, code, token):
        if not self.authorized_host(code, token):
            return False, 'Only the host can end the session.'
        return True, None

    def reset_board(self, code, token):
        if not self.authorized_host(code, token):
            return False, 'Only the host can reset the board.'
        room = self.get_room(code)
        for name in room['departed']:
            if name in room['players']: room['players'].remove(name)
            for key in ('victory_points', 'turns_taken', 'resources'):
                room[key].pop(name, None)
        room.update(board=generate_board(), started=False, phase='lobby', departed=[],
                    turn_index=0, turn_number=1, rolled=False, last_roll=None,
                    buildings={}, roads={}, cities=[], setup_order=[],
                    setup_index=0, setup_step='settlement', setup_vertex=None,
                    road_owner=None, army_owner=None)
        for name in room['players']:
            room['resources'][name] = empty_inventory()
            room['victory_points'][name] = 0
            room['turns_taken'][name] = 0
        self.log(code, 'Host reset the board. Waiting for a new game.')
        return True, None

    def kick_member(self, code, token, name):
        if not self.authorized_host(code, token):
            return False, 'Only the host can kick members.', None
        room = self.get_room(code)
        if name == room['host']:
            return False, 'Host cannot kick themselves.', None
        spectator_token = next((t for t, n in room['spectators'].items() if n == name), None)
        if spectator_token:
            room['spectators'].pop(spectator_token)
            self.log(code, f'{name} was removed by the host.')
            return True, None, spectator_token
        if name not in room['players']:
            return False, 'Member not found.', None
        if room['started']:
            return False, 'Active players cannot be kicked mid-match. Reset the board first.', None
        victim_token = next((t for t, n in room['tokens'].items() if n == name), None)
        if victim_token:
            room['tokens'].pop(victim_token)
        room['players'].remove(name)
        for key in ('victory_points', 'turns_taken', 'resources'):
            room[key].pop(name, None)
        self.log(code, f'{name} was removed by the host.')
        return True, None, victim_token

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

    def resource_count(self, inventory):
        return sum(inventory.values())

    def can_afford(self, room, player, kind):
        return all(room['resources'][player][resource] >= amount
                   for resource, amount in COSTS[kind].items())

    def charge(self, room, player, kind):
        for resource, amount in COSTS[kind].items():
            room['resources'][player][resource] -= amount

    def give_resources_for_vertex(self, room, player, vertex, amount=1):
        for tile, vertices in zip(room['board']['tiles'], HEX_VERTICES):
            resource = TERRAIN_RESOURCE.get(tile['terrain'])
            if vertex in vertices and resource:
                room['resources'][player][resource] += amount

    def produce_resources(self, code, number):
        room = self.get_room(code)
        awards = {}
        for tile, vertices in zip(room['board']['tiles'], HEX_VERTICES):
            if tile['number'] != number:
                continue
            resource = TERRAIN_RESOURCE.get(tile['terrain'])
            if not resource:
                continue
            for vertex in vertices:
                location = f'v{vertex}'
                owner = room['buildings'].get(location)
                if owner:
                    amount = 2 if location in room['cities'] else 1
                    room['resources'][owner][resource] += amount
                    awards.setdefault(owner, empty_inventory())[resource] += amount
        if awards:
            details = ', '.join(f'{owner} received ' + ', '.join(
                f'{amount} {resource}' for resource, amount in items.items() if amount)
                for owner, items in awards.items())
            self.log(code, details + '.')
        else:
            self.log(code, 'No resources produced this roll.')

    def public_room(self, code):
        room = self.get_room(code)
        if not room:
            return None
        return {
            'host': room['host'], 'players': room['players'], 'ai_players': room['ai_players'], 'started': room['started'],
            'spectators': list(room['spectators'].values()), 'departed': room['departed'],
            'spectators': list(room['spectators'].values()), 'departed': room['departed'],
            'turn_index': room['turn_index'], 'turn_number': room['turn_number'],
            'current_player': room['players'][room['turn_index']],
            'rolled': room['rolled'], 'last_roll': room['last_roll'],
            'victory_points': room['victory_points'], 'turns_taken': room['turns_taken'],
            'resource_counts': {p: self.resource_count(room['resources'][p]) for p in room['players']}, 'log': room['log'],
            'road_owner': room['road_owner'], 'army_owner': room['army_owner'],
            'connected': {p: p in room['ai_players'] or bool(room['connections'].get(p)) for p in room['players']},
            'colors': {p: COLORS[i] for i, p in enumerate(room['players'])},
            'buildings': room['buildings'], 'roads': room['roads'], 'cities': room['cities'],
            'board': room['board'], 'phase': room['phase'],
            'setup_step': room['setup_step'], 'setup_index': room['setup_index'],
            'valid_builds': {kind: self.valid_build_locations(room, room['players'][room['turn_index']], kind)
                             for kind in ('settlement', 'road', 'city')},
        }

    def player_room(self, code, player):
        result = self.public_room(code)
        if result and player in self.get_room(code)['resources']:
            result['my_inventory'] = self.get_room(code)['resources'][player].copy()
        elif result and player in self.get_room(code)['spectators'].values():
            result['spectator'] = True
            result['all_inventories'] = {name: inv.copy() for name, inv in self.get_room(code)['resources'].items()}
            result['valid_builds'] = {'road': [], 'settlement': [], 'city': []}
        elif result and player in self.get_room(code)['spectators'].values():
            result['spectator'] = True
            result['all_inventories'] = {name: inv.copy() for name, inv in self.get_room(code)['resources'].items()}
            result['valid_builds'] = {'road': [], 'settlement': [], 'city': []}
        return result

    async def connect(self, code: str, websocket: WebSocket, token: str):
        code = code.upper()
        player = self.player_for_token(code, token) or self.spectator_for_token(code, token) or self.spectator_for_token(code, token)
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
        if not self.get_room(code):
            return
        for websocket in list(self.connections.get(code, [])):
            try:
                player = None
                for name, connections in self.get_room(code)['connections'].items():
                    if websocket in connections:
                        player = name
                        break
                token = self.socket_tokens.get(websocket)
                if not player or not (token in self.get_room(code)['tokens'] or token in self.get_room(code)['spectators']):
                    continue
                await websocket.send_json({'type': 'room_update', 'room_code': code,
                                           'room': self.player_room(code, player)})
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
        room['phase'] = 'setup'
        room['setup_order'] = room['players'] + list(reversed(room['players']))
        room['turn_index'] = 0
        self.log(code, 'Game started! Place your first settlement, then a connecting road.')
        return True, None

    def roll_dice(self, code, token):
        room = self.get_room(code)
        if not room or not room['started']:
            return False, 'Game is not running.'
        player = room['tokens'].get(token)
        if player in room['departed'] or player != room['players'][room['turn_index']]:
            return False, 'Not your turn.'
        if room['phase'] == 'setup':
            return False, 'Finish initial settlement and road placement first.'
        if room['rolled']:
            return False, 'You already rolled this turn.'
        import random
        dice = [random.randint(1, 6), random.randint(1, 6)]
        room['rolled'] = True
        room['last_roll'] = dice
        self.log(code, f'{player} rolled {sum(dice)} ({dice[0]} + {dice[1]}).')
        if sum(dice) == 7:
            # Temporary server-side automatic discard; robber selection is a future feature.
            import random
            for name, inventory in room['resources'].items():
                total = self.resource_count(inventory)
                if total > 7:
                    discard = total // 2
                    cards = [resource for resource, amount in inventory.items() for _ in range(amount)]
                    for resource in random.sample(cards, discard):
                        inventory[resource] -= 1
                    self.log(code, f'{name} discarded {discard} cards after rolling 7.')
            self.log(code, 'Robber movement is not implemented yet.')
        else:
            self.produce_resources(code, sum(dice))
        return True, None

    def valid_build_locations(self, room, player, kind):
        if not room['started'] or player in room['departed'] or room['players'][room['turn_index']] != player:
            return []
        setup = room['phase'] == 'setup'
        if setup and kind != room['setup_step']:
            return []
        if not setup and not room['rolled']:
            return []
        if not setup and kind in COSTS and not self.can_afford(room, player, kind):
            return []
        if kind == 'city':
            return [] if setup else [v for v, owner in room['buildings'].items()
                                     if owner == player and v not in room['cities']]
        occupied = room['buildings']
        roads = room['roads']
        neighbors = {v: set() for v in range(len(VERTICES))}
        for a, b in EDGES_LIST:
            neighbors[a].add(b)
            neighbors[b].add(a)
        if kind == 'settlement':
            candidates = []
            for v in range(len(VERTICES)):
                key = f'v{v}'
                if key in occupied or any(f'v{n}' in occupied for n in neighbors[v]):
                    continue
                if not setup and not any(owner == player and v in EDGES_LIST[int(edge[1:])]
                                     for edge, owner in roads.items()):
                    continue
                candidates.append(key)
            return candidates
        if kind == 'road':
            candidates = []
            for i, (a, b) in enumerate(EDGES_LIST):
                key = f'e{i}'
                if key in roads:
                    continue
                if setup:
                    if room['setup_vertex'] in (a, b):
                        candidates.append(key)
                    continue
                # A rival settlement stops road continuation through that vertex.
                def reachable(vertex):
                    holder = occupied.get(f'v{vertex}')
                    if holder is not None:
                        return holder == player
                    return any(owner == player and vertex in EDGES_LIST[int(edge[1:])]
                               for edge, owner in roads.items())
                if reachable(a) or reachable(b):
                    candidates.append(key)
            return candidates
        return []

    def build(self, code, token, kind, location):
        room = self.get_room(code)
        if not room or not room['started']:
            return False, 'Game is not running.'
        player = room['tokens'].get(token)
        if player in room['departed'] or player != room['players'][room['turn_index']]:
            return False, 'Wait for your turn.'
        valid = VERTICES if kind in ('settlement', 'city') else EDGES if kind == 'road' else None
        if valid is None or location not in valid:
            return False, 'Invalid construction location.'
        target = room['buildings'] if kind in ('settlement', 'city') else room['roads']
        if kind != 'city' and location in target:
            return False, 'This location is already occupied.'

        if location not in self.valid_build_locations(room, player, kind):
            return False, 'That location is blocked, too close to a settlement, or not connected to your network.'
        if kind == 'settlement':
            vertex_id = int(location[1:])

        if room['phase'] == 'setup':
            if kind != room['setup_step']:
                return False, f"Place a {room['setup_step']} first."
            if kind == 'road':
                a, b = EDGES_LIST[int(location[1:])]
                anchor = room['setup_vertex']
                if anchor not in (a, b):
                    return False, 'Your starting road must connect to your new settlement.'
            target[location] = player
            if kind == 'settlement':
                room['victory_points'][player] += 1
                # Second starting settlement grants adjacent tile resources.
                if room['setup_index'] >= len(room['players']):
                    self.give_resources_for_vertex(room, player, vertex_id)
                    self.log(code, f'{player} received starting resources.')
                room['setup_vertex'] = vertex_id
                room['setup_step'] = 'road'
            else:
                room['setup_index'] += 1
                room['setup_vertex'] = None
                if room['setup_index'] >= len(room['setup_order']):
                    room['phase'] = 'play'
                    room['turn_index'] = 0
                    room['setup_step'] = 'settlement'
                    self.log(code, 'Setup complete! Roll the dice to begin.')
                else:
                    next_player = room['setup_order'][room['setup_index']]
                    room['turn_index'] = room['players'].index(next_player)
                    room['setup_step'] = 'settlement'
            self.log(code, f'{player} placed a starting {kind} at {location}.')
            return True, None

        if not room['rolled']:
            return False, 'Roll the dice before building.'
        if not self.can_afford(room, player, kind):
            return False, 'Not enough resources.'
        self.charge(room, player, kind)
        if kind == 'city':
            room['cities'].append(location)
            room['victory_points'][player] += 1  # Upgrade 1 VP settlement to 2 VP city.
        else:
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
        if player in room['departed'] or player != room['players'][room['turn_index']]:
            return False, 'Not your turn.'
        if room['phase'] == 'setup':
            return False, 'Finish initial placement before ending turns.'
        if not room['rolled']:
            return False, 'Roll the dice before ending your turn.'
        room['turns_taken'][player] += 1
        for offset in range(1, len(room['players']) + 1):
            index = (room['turn_index'] + offset) % len(room['players'])
            if room['players'][index] not in room['departed']:
                room['turn_index'] = index
                break
        room['turn_number'] += 1
        room['rolled'] = False
        room['last_roll'] = None
        self.log(code, f"Turn passed to {room['players'][room['turn_index']] }.")
        return True, None

room_manager = RoomManager()
