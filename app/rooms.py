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
AI_DIFFICULTIES = ('Easy', 'Normal', 'Hard', 'Aggressive')
TERRAIN_RESOURCE = {'forest': 'wood', 'hills': 'brick', 'wheat': 'wheat',
                    'pasture': 'wool', 'mountain': 'ore'}
COSTS = {'road': {'wood': 1, 'brick': 1},
         'settlement': {'wood': 1, 'brick': 1, 'wheat': 1, 'wool': 1},
         'city': {'wheat': 2, 'ore': 3},
         'knight': {'wool': 1, 'wheat': 1, 'ore': 1}}

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
            'host': player_name, 'players': [player_name], 'ai_players': [], 'ai_difficulties': {}, 'started': False,
            'tokens': {token: player_name}, 'spectators': {}, 'departed': [], 'forfeited': {}, 'private_logs': {}, 'turn_index': 0, 'turn_number': 1,
            'rolled': False, 'last_roll': None, 'victory_points': {player_name: 0},
            'turns_taken': {player_name: 0}, 'log': [], 'road_owner': None,
            'army_owner': None, 'knights_played': {}, 'knights_ready': {}, 'knights_new': {}, 'knight_used': False, 'road_lengths': {}, 'resources': {player_name: empty_inventory()},
            'trades': {}, 'trade_serial': 0, 'connections': {}, 'buildings': {}, 'roads': {}, 'cities': [],
            'board': generate_board(), 'robber_tile': None, 'robber_pending': False, 'phase': 'lobby', 'setup_order': [],
            'setup_index': 0, 'setup_step': 'settlement', 'setup_vertex': None,
        }
        self.initialize_awards(self.rooms[code])
        self.initialize_robber(self.rooms[code])
        self.log(code, f'{player_name} created the room.')
        return code, token

    def join_room(self, room_code, player_name):
        code = room_code.upper()
        room = self.rooms.get(code)
        if not room or room['started'] or len(room['players']) >= 4 or player_name in room['players'] or player_name in room['spectators'].values():
            return None
        token = secrets.token_urlsafe(24)
        room['tokens'][token] = player_name
        room['players'].append(player_name)
        room['victory_points'][player_name] = 0
        room['turns_taken'][player_name] = 0
        room['resources'][player_name] = empty_inventory()
        self.initialize_awards(room)
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
        room['ai_difficulties'][name] = 'Normal'
        room['victory_points'][name] = 0
        room['turns_taken'][name] = 0
        room['resources'][name] = empty_inventory()
        self.initialize_awards(room)
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
        room['ai_difficulties'].pop(name, None)
        room['players'].remove(name)
        for key in ('victory_points', 'turns_taken', 'resources'):
            room[key].pop(name, None)
        self.initialize_awards(room)
        self.log(code, f'{name} was removed.')
        return True, None

    def set_ai_difficulty(self, code, token, name, difficulty):
        room = self.get_room(code)
        if not room or not self.authorized_host(code, token):
            return False, 'Only the host can configure AI opponents.'
        if room['started']:
            return False, 'AI difficulty is locked after the match starts.'
        if name not in room['ai_players']:
            return False, 'AI opponent not found.'
        if difficulty not in AI_DIFFICULTIES:
            return False, 'Choose Easy, Normal, Hard, or Aggressive.'
        room['ai_difficulties'][name] = difficulty
        self.log(code, f'{name} difficulty set to {difficulty}.')
        return True, None

    def ai_difficulty(self, room, player):
        return room.get('ai_difficulties', {}).get(player, 'Normal')

    def ai_trade_accepts(self, room, recipient, give, want, sender):
        difficulty = self.ai_difficulty(room, recipient)
        if difficulty in ('Easy', 'Normal'):
            return True
        inventory = room['resources'][recipient]
        # Value resources by scarcity and the immediate costs of useful builds.
        def value(resource):
            count = inventory.get(resource, 0)
            base = 1.0 + (1.2 if count == 0 else 0.5 if count == 1 else 0)
            if resource in ('ore', 'wheat') and self.valid_build_locations(room, recipient, 'city'):
                base += 0.8
            if resource in ('wood', 'brick') and room.get('road_owner') != recipient:
                base += 0.3
            return base
        incoming = sum(value(k) * n for k, n in give.items())
        outgoing = sum(value(k) * n for k, n in want.items())
        # Keep a reserve for construction and avoid enabling the leader.
        reserve_penalty = sum(0.7 * n for k, n in want.items() if inventory[k] - n == 0)
        if difficulty == 'Aggressive':
            leader = room['victory_points'].get(sender, 0)
            reserve_penalty += max(0, leader - room['victory_points'].get(recipient, 0)) * 0.35
            return incoming >= (outgoing + reserve_penalty) * 1.15
        return incoming >= outgoing + reserve_penalty

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
        difficulty = self.ai_difficulty(room, player)
        if difficulty == 'Easy':
            return random.choice(locations)
        if kind in ('city', 'settlement'):
            def score(location):
                vertex = int(location[1:])
                value = self.ai_vertex_score(room, vertex)
                if difficulty in ('Hard', 'Aggressive'):
                    adjacent = [tile for tile, vertices in zip(room['board']['tiles'], HEX_VERTICES)
                                if vertex in vertices and tile['terrain'] in TERRAIN_RESOURCE]
                    value += len({TERRAIN_RESOURCE[t['terrain']] for t in adjacent}) * 1.4
                    if kind == 'city':
                        value *= 1.6
                return value + random.random() * (2 if difficulty == 'Normal' else 0.15)
            return max(locations, key=score)
        occupied = room['buildings']
        def score(edge):
            a, b = EDGES_LIST[int(edge[1:])]
            potential = max((self.ai_vertex_score(room, v) if f'v{v}' not in occupied else 0)
                            for v in (a, b))
            if difficulty == 'Aggressive':
                # Prefer competing for routes near the longest-road contender.
                leader = max((p for p in room['players'] if p != player),
                             key=lambda p: room.get('road_lengths', {}).get(p, 0), default=None)
                if leader and room.get('road_lengths', {}).get(leader, 0) >= 3:
                    rival_vertices = {v for e, owner in room['roads'].items() if owner == leader
                                      for v in EDGES_LIST[int(e[1:])]}
                    potential += sum(v in rival_vertices for v in (a, b)) * 7
                potential += room.get('road_lengths', {}).get(player, 0) * 0.3
            return potential + random.random() * (2 if difficulty == 'Normal' else 0.1)
        return max(locations, key=score)

    def ai_vertex_score(self, room, vertex):
        weights = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
        return sum(weights.get(tile['number'], 0)
                   for tile, vertices in zip(room['board']['tiles'], HEX_VERTICES)
                   if vertex in vertices and tile['terrain'] in TERRAIN_RESOURCE)

    def join_spectator(self, code, name):
        room = self.get_room(code)
        if not room or not room['started'] or not name or (name in room['players'] and name not in room['departed']) or name in room['spectators'].values():
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
        name = room['tokens'].get(token)
        if not name:
            return False, 'Not a room member.', None
        if room['started']:
            candidates = [p for p in room['players'] if p != name
                          and p not in room['ai_players'] and p not in room['departed']
                          and any(n == p for t, n in room['tokens'].items()
                                  if t != token and room['connections'].get(p))]
            if name == room['host'] and not candidates:
                self.rooms.pop(code.upper(), None)
                return True, None, name
            room['tokens'].pop(token, None)
            room['departed'].append(name)
            room['forfeited'][name] = True
            if name == room['host']:
                room['host'] = candidates[0]
                self.log(code, f'{room["host"]} is the new host.')
            if room['phase'] == 'setup':
                # Rebuild setup order without the forfeited player.
                room['setup_order'] = [p for p in room['setup_order'] if p != name]
                room['setup_index'] = min(room['setup_index'], max(0, len(room['setup_order']) - 1))
            if room['players'][room['turn_index']] == name:
                for offset in range(1, len(room['players']) + 1):
                    index = (room['turn_index'] + offset) % len(room['players'])
                    if room['players'][index] not in room['departed']:
                        room['turn_index'] = index
                        break
                room['rolled'] = False
                room['last_roll'] = None
            for trade in room['trades'].values():
                if trade['status'] == 'pending' and name in (trade['sender'], trade['recipient']):
                    trade['status'] = 'expired'
            self.log(code, f'{name} forfeited the match.')
            return True, None, name
        room['tokens'].pop(token, None)
        room['players'].remove(name)
        for key in ('victory_points', 'turns_taken', 'resources'):
            room[key].pop(name, None)
        room['connections'].pop(name, None)
        if not room['players']:
            self.rooms.pop(code.upper(), None)
            return True, None, name
        if room['host'] == name:
            candidates = [p for p in room['players'] if p not in room['ai_players']]
            if not candidates:
                self.rooms.pop(code.upper(), None)
                return True, None, name
            room['host'] = candidates[0]
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
        # Spectators become active players for the next round when slots exist.
        for spectator_token, spectator_name in list(room['spectators'].items()):
            if len(room['players']) >= 4:
                break
            if spectator_name in room['players']:
                continue
            room['spectators'].pop(spectator_token)
            room['tokens'][spectator_token] = spectator_name
            room['players'].append(spectator_name)
            room['victory_points'][spectator_name] = 0
            room['turns_taken'][spectator_name] = 0
            room['resources'][spectator_name] = empty_inventory()
        room['forfeited'] = {}
        room['private_logs'] = {}
        room.update(board=generate_board(), started=False, phase='lobby', departed=[], trades={}, trade_serial=0,
                    turn_index=0, turn_number=1, rolled=False, last_roll=None,
                    buildings={}, roads={}, cities=[], setup_order=[],
                    setup_index=0, setup_step='settlement', setup_vertex=None,
                    road_owner=None, army_owner=None, robber_pending=False)
        self.initialize_robber(room)
        self.initialize_awards(room, reset=True)
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
            room['log'].append({'time': time.strftime('%H:%M:%S'), 'message': message, 'sequence': time.monotonic_ns()})
            room['log'] = room['log'][-100:]

    def private_log(self, code, player, message):
        room = self.get_room(code)
        if room:
            entries = room['private_logs'].setdefault(player, [])
            entries.append({'time': time.strftime('%H:%M:%S'), 'message': message, 'sequence': time.monotonic_ns()})
            room['private_logs'][player] = entries[-100:]

    def expire_trades(self, code):
        room = self.get_room(code)
        if not room:
            return False
        changed = False
        for trade in room['trades'].values():
            if trade['status'] == 'pending' and time.monotonic() >= trade['deadline_monotonic']:
                trade['status'] = 'expired'
                changed = True
        return changed

    def pending_trade(self, code):
        self.expire_trades(code)
        room = self.get_room(code)
        return next((t for t in room['trades'].values() if t['status'] == 'pending'), None) if room else None

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

    def initialize_awards(self, room, reset=False):
        for key in ('knights_played', 'knights_ready', 'knights_new'):
            if reset:
                room[key] = {}
            room.setdefault(key, {})
            for name in room['players']:
                room[key].setdefault(name, 0)
        if reset:
            room['road_lengths'] = {}
            room['knight_used'] = False
        room.setdefault('road_lengths', {})

    def longest_road_length(self, room, player):
        # Enumerate trails (edges cannot repeat). Enemy buildings interrupt the route.
        adjacency = {}
        for edge_id, owner in room['roads'].items():
            if owner != player:
                continue
            a, b = EDGES_LIST[int(edge_id[1:])]
            adjacency.setdefault(a, []).append((b, edge_id))
            adjacency.setdefault(b, []).append((a, edge_id))
        def search(vertex, used):
            if used and room['buildings'].get(f'v{vertex}') not in (None, player):
                return 0
            best = 0
            for other, edge in adjacency.get(vertex, []):
                if edge not in used:
                    best = max(best, 1 + search(other, used | {edge}))
            return best
        return max((search(vertex, set()) for vertex in adjacency), default=0)

    def update_awards(self, code):
        room = self.get_room(code)
        self.initialize_awards(room)
        room['road_lengths'] = {p: self.longest_road_length(room, p) for p in room['players']}
        for owner_key, scores, minimum, title in (
            ('road_owner', room['road_lengths'], 5, 'Longest Road'),
            ('army_owner', room['knights_played'], 3, 'Largest Army')):
            old = room[owner_key]
            high = max(scores.values(), default=0)
            leaders = [p for p, score in scores.items() if score == high]
            new = (old if old in leaders else (leaders[0] if len(leaders) == 1 else None)) if high >= minimum else None
            if new != old:
                if old in room['victory_points']:
                    room['victory_points'][old] -= 2
                if new in room['victory_points']:
                    room['victory_points'][new] += 2
                room[owner_key] = new
                self.log(code, f'{new} earned {title} (+2 VP).' if new else f'{title} is unclaimed.')

    def buy_knight(self, code, token):
        room = self.get_room(code)
        if not room or room['phase'] != 'play':
            return False, 'Finish setup first.'
        player = room['tokens'].get(token)
        if player != room['players'][room['turn_index']] or not room['rolled'] or room['robber_pending']:
            return False, 'Buy a knight during your turn after resolving the dice.'
        if not self.can_afford(room, player, 'knight'):
            return False, 'A knight costs 1 wool, 1 wheat, and 1 ore.'
        self.charge(room, player, 'knight')
        self.initialize_awards(room)
        room['knights_new'][player] += 1
        self.log(code, f'{player} recruited a knight (usable on a later turn).')
        return True, None

    def play_knight(self, code, token):
        room = self.get_room(code)
        if not room or room['phase'] != 'play':
            return False, 'Finish setup first.'
        player = room['tokens'].get(token)
        if player != room['players'][room['turn_index']] or not room['rolled'] or room['robber_pending']:
            return False, 'Play a knight during your turn after resolving the dice.'
        if room.get('knight_used') or room['knights_ready'].get(player, 0) < 1:
            return False, 'No playable knight, or you already played one this turn.'
        room['knights_ready'][player] -= 1
        room['knights_played'][player] += 1
        room['knight_used'] = True
        room['robber_pending'] = True
        self.update_awards(code)
        self.log(code, f'{player} played a knight and must move the robber.')
        return True, None

    def initialize_robber(self, room):
        room['robber_tile'] = next(tile['id'] for tile in room['board']['tiles'] if tile['terrain'] == 'desert')
        room['robber_pending'] = False

    def robber_victims(self, room, tile_id, mover):
        for tile, vertices in zip(room['board']['tiles'], HEX_VERTICES):
            if tile['id'] == tile_id:
                return sorted({room['buildings'][f'v{v}'] for v in vertices
                               if f'v{v}' in room['buildings']
                               and room['buildings'][f'v{v}'] != mover
                               and self.resource_count(room['resources'][room['buildings'][f'v{v}']]) > 0})
        return []

    def move_robber(self, code, token, tile_id, victim=None):
        room = self.get_room(code)
        if not room or room['phase'] != 'play' or not room['robber_pending']:
            return False, 'There is no robber move pending.'
        mover = room['tokens'].get(token)
        if mover != room['players'][room['turn_index']] or mover in room['departed']:
            return False, 'Only the current player can move the robber.'
        if not isinstance(tile_id, str) or tile_id == room['robber_tile'] or not any(t['id'] == tile_id for t in room['board']['tiles']):
            return False, 'Choose a different tile on the island.'
        eligible = self.robber_victims(room, tile_id, mover)
        if victim is not None and victim not in eligible:
            return False, 'That opponent cannot be robbed on this tile.'
        if eligible and victim is None:
            if len(eligible) == 1:
                victim = eligible[0]
            else:
                return False, 'Choose which adjacent opponent to rob.'
        room['robber_tile'] = tile_id
        room['robber_pending'] = False
        self.log(code, f'{mover} moved the robber to {tile_id}.')
        if victim:
            cards = [k for k, count in room['resources'][victim].items() for _ in range(count)]
            if cards:
                stolen = random.choice(cards)
                room['resources'][victim][stolen] -= 1
                room['resources'][mover][stolen] += 1
                # Public log omits the stolen resource type.
                self.log(code, f'{mover} stole one resource card from {victim}.')
        return True, None

    def produce_resources(self, code, number):
        room = self.get_room(code)
        awards = {}
        for tile, vertices in zip(room['board']['tiles'], HEX_VERTICES):
            if tile['number'] != number or tile['id'] == room['robber_tile']:
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
            for owner, items in awards.items():
                details = ', '.join(f'{amount} {resource}' for resource, amount in items.items() if amount)
                self.private_log(code, owner, f'You received {details}.')
                self.log(code, f'{owner} received resources.')
        else:
            self.log(code, 'No resources produced this roll.')

    def propose_trade(self, code, token, recipient, offer, request):
        room = self.get_room(code)
        if not room or not room['started'] or room['phase'] != 'play':
            return False, 'Trading is available during normal gameplay only.'
        sender = room['tokens'].get(token)
        if sender != room['players'][room['turn_index']] or not room['rolled'] or room['robber_pending']:
            return False, 'You can trade only after rolling on your turn.'
        if recipient not in room['players'] or recipient == sender or recipient in room['departed']:
            return False, 'Choose an available opponent.'
        if not isinstance(offer, dict) or not isinstance(request, dict):
            return False, 'Invalid resource quantities.'
        for hand in (offer, request):
            if set(hand) - set(RESOURCE_TYPES) or any(type(v) is not int or v < 0 or v > 99 for v in hand.values()):
                return False, 'Invalid resource quantities.'
        give = {k: offer.get(k, 0) for k in RESOURCE_TYPES}
        want = {k: request.get(k, 0) for k in RESOURCE_TYPES}
        if not any(give.values()) or not any(want.values()):
            return False, 'Both sides must exchange at least one card.'
        if any(room['resources'][sender][k] < v for k, v in give.items()):
            return False, 'You do not have enough resources.'
        if self.pending_trade(code):
            return False, 'Resolve the pending trade first.'
        room['trade_serial'] += 1
        ident = str(room['trade_serial'])
        trade = {'id': ident, 'sender': sender, 'recipient': recipient,
                 'offer': give, 'request': want, 'status': 'pending',
                 'deadline_monotonic': time.monotonic() + 120,
                 'expires_at': time.time() + 120, 'countered': False}
        room['trades'][ident] = trade
        if recipient in room['ai_players']:
            if any(room['resources'][recipient][k] < n for k, n in want.items()):
                trade['status'] = 'rejected'
            elif self.ai_trade_accepts(room, recipient, give, want, sender):
                self.resolve_trade(code, self.ai_token(room, recipient), ident, True)
            else:
                difficulty = self.ai_difficulty(room, recipient)
                if difficulty in ('Normal', 'Hard', 'Aggressive') and sum(give.values()) < sum(want.values()):
                    extra = next((k for k in RESOURCE_TYPES if room['resources'][sender][k] > give[k]), None)
                    if extra:
                        counter_request = give.copy()
                        counter_request[extra] += 1
                        trade.update(offer=want.copy(), request=counter_request,
                                     countered=True, recipient=sender, sender=recipient)
                    else:
                        trade['status'] = 'rejected'
                else:
                    trade['status'] = 'rejected'
        return True, None

    def counter_trade(self, code, token, trade_id, offer, request):
        room = self.get_room(code)
        trade = self.pending_trade(code)
        if not room or not trade or trade['id'] != str(trade_id):
            return False, 'Trade is no longer pending.'
        recipient = room['tokens'].get(token)
        if recipient != trade['recipient'] or recipient in room['ai_players']:
            return False, 'Only the recipient may counteroffer.'
        if trade['countered']:
            return False, 'Only one counteroffer is allowed.'
        if not isinstance(offer, dict) or not isinstance(request, dict):
            return False, 'Invalid counteroffer.'
        for hand in (offer, request):
            if set(hand) - set(RESOURCE_TYPES) or any(type(v) is not int or v < 0 or v > 99 for v in hand.values()):
                return False, 'Invalid counteroffer.'
        give = {k: offer.get(k, 0) for k in RESOURCE_TYPES}
        want = {k: request.get(k, 0) for k in RESOURCE_TYPES}
        if not any(give.values()) or not any(want.values()):
            return False, 'Both sides must exchange at least one card.'
        if any(room['resources'][recipient][k] < v for k, v in give.items()):
            return False, 'You do not have enough resources.'
        original_sender = trade['sender']
        trade.update(sender=recipient, recipient=original_sender, offer=give, request=want, countered=True)
        return True, None

    def resolve_trade(self, code, token, trade_id, accept):
        room = self.get_room(code)
        trade = self.pending_trade(code)
        recipient = room['tokens'].get(token) if room else None
        if not trade or trade['id'] != str(trade_id) or recipient != trade['recipient']:
            return False, 'You are not authorized to respond to this trade.'
        if not isinstance(accept, bool):
            return False, 'Invalid response.'
        if not accept:
            trade['status'] = 'rejected'
            return True, None
        sender = trade['sender']
        if (room['phase'] != 'play' or
            any(room['resources'][sender][k] < n for k, n in trade['offer'].items()) or
            any(room['resources'][recipient][k] < n for k, n in trade['request'].items())):
            trade['status'] = 'expired'
            return False, 'Trade could not be completed.'
        for k in RESOURCE_TYPES:
            room['resources'][sender][k] += trade['request'][k] - trade['offer'][k]
            room['resources'][recipient][k] += trade['offer'][k] - trade['request'][k]
        trade['status'] = 'accepted'
        self.log(code, 'A private trade was completed.')
        return True, None

    def public_room(self, code):
        room = self.get_room(code)
        if not room:
            return None
        return {
            'host': room['host'], 'players': room['players'], 'ai_players': room['ai_players'], 'ai_difficulties': room.get('ai_difficulties', {}), 'started': room['started'],
            'spectators': list(room['spectators'].values()), 'departed': room['departed'],
            'turn_index': room['turn_index'], 'turn_number': room['turn_number'],
            'current_player': room['players'][room['turn_index']],
            'rolled': room['rolled'], 'last_roll': room['last_roll'],
            'robber_tile': room['robber_tile'], 'robber_pending': room['robber_pending'],
            'robber_tile_vertices': {tile['id']: list(vertices) for tile, vertices in zip(room['board']['tiles'], HEX_VERTICES)},
            'victory_points': room['victory_points'], 'turns_taken': room['turns_taken'],
            'resource_counts': {p: self.resource_count(room['resources'][p]) for p in room['players']}, 'log': room['log'],
            'road_owner': room['road_owner'], 'army_owner': room['army_owner'],
            'road_lengths': room.get('road_lengths', {}), 'knights_played': room.get('knights_played', {}), 'knight_used': room.get('knight_used', False),
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
        if result:
            room = self.get_room(code)
            result['log'] = sorted(
                room['log'] + room['private_logs'].get(player, []),
                key=lambda entry: entry['sequence']
            )[-100:]
        if result and player in self.get_room(code)['resources'] and player not in self.get_room(code)['departed']:
            result['my_knights'] = {'ready': self.get_room(code).get('knights_ready', {}).get(player, 0), 'new': self.get_room(code).get('knights_new', {}).get(player, 0)}
            result['my_inventory'] = self.get_room(code)['resources'][player].copy()
            result['private_trades'] = [{k:v for k,v in t.items() if k != 'deadline_monotonic'} for t in self.get_room(code)['trades'].values() if player in (t['sender'], t['recipient'])][-15:]
        elif result and player in self.get_room(code)['spectators'].values():
            result['spectator'] = True
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
            room['robber_pending'] = True
            self.log(code, f'{player} must move the robber to a different tile.')
        else:
            self.produce_resources(code, sum(dice))
        return True, None

    def valid_build_locations(self, room, player, kind):
        if not room['started'] or player in room['departed'] or room['players'][room['turn_index']] != player:
            return []
        setup = room['phase'] == 'setup'
        if setup and kind != room['setup_step']:
            return []
        if not setup and (not room['rolled'] or room['robber_pending']):
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
            self.update_awards(code)
            self.log(code, f'{player} placed a starting {kind} at {location}.')
            return True, None

        if not room['rolled']:
            return False, 'Roll the dice before building.'
        if room['robber_pending']:
            return False, 'Move the robber before building.'
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
        self.update_awards(code)
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
        if room['robber_pending']:
            return False, 'Move the robber before ending your turn.'
        if self.pending_trade(code):
            return False, 'You cannot end your turn while a trade is pending.'
        room['turns_taken'][player] += 1
        room['knights_ready'][player] += room['knights_new'][player]
        room['knights_new'][player] = 0
        room['knight_used'] = False
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
