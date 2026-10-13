'use strict';
const $ = id => document.getElementById(id);
let socket = null, currentRoom = null, currentPlayer = null, playerToken = null;
let latestRoom = null, pingMs = null, pingSent = new Map(), pingCounter = 0;
const getHost = () => latestRoom && latestRoom.host === currentPlayer;
function showScreen(name) {
  ['home-screen','lobby-screen','game-screen'].forEach(id => $(id).classList.toggle('hidden', id !== name));
}
function showLobby(code, player, token) {
  currentRoom = code; currentPlayer = player; playerToken = token;
  $('lobby-room-code').textContent = code;
  $('game-room-code').textContent = code;
  $('footer-room').textContent = '| ' + code;
  showScreen('lobby-screen'); connectWebSocket();
}
function connectWebSocket() {
  if (socket) socket.close();
  const scheme = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const ws = new WebSocket(`${scheme}//${location.host}/ws/${encodeURIComponent(currentRoom)}?token=${encodeURIComponent(playerToken)}`);
  socket = ws;
  ws.onopen = () => { console.log('Connected to', currentRoom); sendPing(); };
  ws.onmessage = event => {
    const data = JSON.parse(event.data);
    if (data.type === 'room_update') updateRoom(data.room);
    if (data.type === 'pong' && pingSent.has(data.id)) {
      pingMs = Math.round(performance.now() - pingSent.get(data.id));
      pingSent.delete(data.id); if (latestRoom) renderPlayers(latestRoom);
    }
  };
  ws.onclose = () => console.log('Disconnected');
  ws.onerror = error => console.error('WebSocket error', error);
}
function sendPing() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  const id = ++pingCounter;
  pingSent.set(id, performance.now());
  socket.send(JSON.stringify({type:'ping', id}));
  if (pingSent.size > 10) pingSent.clear();
}
setInterval(sendPing, 3000);
function updateRoom(room) {
  latestRoom = room;
  $('player-list').replaceChildren();
  room.players.forEach(player => {
    const entry = document.createElement('div'); entry.className = 'player-entry';
    const name = document.createElement('span'); name.textContent = '● ' + player; entry.append(name);
    if (player === room.host) { const label = document.createElement('span'); label.className='host-label'; label.textContent='[HOST]'; entry.append(label); }
    $('player-list').append(entry);
  });
  $('start-game').classList.toggle('hidden', currentPlayer !== room.host || room.started);
  $('start-game').disabled = room.players.length < 2;
  document.querySelector('.waiting-message').textContent = room.started ? '> GAME STARTED - LOADING BOARD...' : `> ${room.players.length} PLAYER(S) CONNECTED - WAITING...`;
  if (room.started) { showScreen('game-screen'); renderGame(room); }
}
function renderPlayers(room) {
  const body = $('game-players'); body.replaceChildren();
  const seven = room.last_roll && room.last_roll.reduce((a,b)=>a+b,0) === 7;
  $('last-column-head').textContent = seven ? 'Cards' : 'Connection';
  room.players.forEach(player => {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    if (player === room.current_player) { const star = document.createElement('span'); star.className='star'; star.textContent='★ '; cell.append(star); }
    const color = document.createElement('span'); color.className='color-square '+room.colors[player]; cell.append(color);
    const name = document.createElement('span'); name.textContent=player+(player===room.host?' (HOST)':''); cell.append(name); row.append(cell);
    for (const val of [room.turns_taken[player], room.victory_points[player]]) { const td=document.createElement('td'); td.textContent=val; row.append(td); }
    const status=document.createElement('td');
    if (seven) status.textContent=room.resource_counts[player] + (room.resource_counts[player]>7?' ⚠':'');
    else { const dot=document.createElement('span'); dot.className=room.connected[player]?'online':'offline'; dot.textContent='● '; status.append(dot); status.append(document.createTextNode(room.connected[player]?(player===currentPlayer&&pingMs!==null?`${pingMs} ms`:'Online'):'Offline')); }
    row.append(status); body.append(row);
  });
}
function renderGame(room) {
  renderPlayers(room);
  renderTerrainBoard(room.board);
  renderBuildOverlay(room);
  $('current-player').textContent = room.current_player + (room.current_player===room.host?' (HOST)':'');
  $('turn-info').textContent = `Turn ${room.turn_number}`;
  $('dice-result').textContent = room.last_roll ? room.last_roll.join(' + ') : '⚄ ⚄';
  const myTurn = room.current_player === currentPlayer;
  $('roll-dice').disabled = !myTurn || room.rolled;
  $('end-turn').disabled = !myTurn || !room.rolled;
  $('longest-road').textContent = room.road_owner || 'Not awarded';
  $('largest-army').textContent = room.army_owner || 'Not awarded';
  const log = $('game-log');
  const wasAtBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 25;
  log.replaceChildren();
  room.log.forEach(item => { const line=document.createElement('div'); const time=document.createElement('time'); time.textContent='['+item.time+']'; line.append(time,document.createTextNode(item.message)); log.append(line); });
  if (wasAtBottom) log.scrollTop=log.scrollHeight;
}
async function request(path, body) {
  const response = await fetch(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if (!response.ok) throw new Error(`Server returned ${response.status}`);
  const data=await response.json(); if (!data.success) throw new Error(data.error||'Request failed'); return data;
}
async function perform(button, fn) {
  button.disabled=true;
  try { await fn(); } catch (error) { alert(error.message); console.error(error); }
  finally { button.disabled=false; }
}
$('create-room').onclick=()=>perform($('create-room'),async()=>{
  const name=$('create-name').value.trim(); if (!name) throw new Error('Enter your name.');
  const data=await request('/api/rooms',{player_name:name}); showLobby(data.room_code,data.player_name,data.token);
});
$('join-room').onclick=()=>perform($('join-room'),async()=>{
  const name=$('join-name').value.trim(),code=$('room-code').value.trim().toUpperCase();
  if (!name||!code) throw new Error('Enter a name and room code.');
  const data=await request(`/api/rooms/${encodeURIComponent(code)}/join`,{player_name:name}); showLobby(data.room_code,data.player_name,data.token);
});
$('start-game').onclick=()=>perform($('start-game'),()=>request(`/api/rooms/${currentRoom}/start`,{token:playerToken}));
$('roll-dice').onclick=()=>perform($('roll-dice'),()=>request(`/api/rooms/${currentRoom}/roll`,{token:playerToken}));
$('end-turn').onclick=()=>perform($('end-turn'),()=>request(`/api/rooms/${currentRoom}/end-turn`,{token:playerToken}));
document.querySelectorAll('[data-placeholder]').forEach(button=>button.onclick=()=>alert(button.dataset.placeholder+' is coming in the next stage.'));


// v0.3: per-browser display settings (no multiplayer state changes)
function applyTheme(theme) {
  const dark = theme === 'dark';
  document.body.classList.toggle('dark-theme', dark);
  localStorage.setItem('pentagon-theme', dark ? 'dark' : 'light');
}
applyTheme(localStorage.getItem('pentagon-theme') || 'light');
const viewToggle = $('view-menu-toggle');
const viewDropdown = $('view-dropdown');
viewToggle.addEventListener('click', () => {
  const open = viewDropdown.classList.toggle('hidden') === false;
  viewToggle.setAttribute('aria-expanded', String(open));
});
$('theme-light').addEventListener('click', () => { applyTheme('light'); viewDropdown.classList.add('hidden'); viewToggle.setAttribute('aria-expanded', 'false'); });
$('theme-dark').addEventListener('click', () => { applyTheme('dark'); viewDropdown.classList.add('hidden'); viewToggle.setAttribute('aria-expanded', 'false'); });
document.addEventListener('click', event => {
  if (!event.target.closest('.view-menu')) { viewDropdown.classList.add('hidden'); viewToggle.setAttribute('aria-expanded', 'false'); }
});

// v0.5 construction overlay: coordinates refer to the existing 917 x 760 map.
// These are prototype clickable build sites, not yet the final resource/adjacency rules.
let V = [];
let E = [];
fetch('/api/board-geometry').then(r=>r.json()).then(g=>{V=g.vertices;E=g.edges;if(latestRoom&&latestRoom.started)renderBuildOverlay(latestRoom);}).catch(console.error);
let buildMode = null;
let showMarkers = true;
const overlay = $('build-overlay');
const SVG_NS = 'http://www.w3.org/2000/svg';
function svgEl(tag, attrs) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key,value] of Object.entries(attrs)) el.setAttribute(key, value);
  return el;
}
function renderBuildOverlay(room) {
  overlay.replaceChildren();
  if (!V.length || !E.length) return;
  const canBuild = room.current_player === currentPlayer && room.rolled;
  for (let i=0;i<E.length;i++) {
    const [a,b] = E[i], [x1,y1]=V[a], [x2,y2]=V[b], owner=room.roads['e'+i];
    const line=svgEl('line',{x1,y1,x2,y2,'class':owner?'built-road':'build-edge'+(buildMode==='road'&&canBuild&&showMarkers?' available':'')});
    if(owner) line.setAttribute('stroke', room.colors[owner] || 'white');
    if (!owner && buildMode==='road' && canBuild && showMarkers) {
      line.addEventListener('click',()=>placeBuild('road','e'+i));
    }
    overlay.append(line);
  }
  for(let i=0;i<V.length;i++) {
    const [cx,cy]=V[i], owner=room.buildings['v'+i];
    const circle=svgEl('circle',{cx,cy,r:owner?12:10,'class':owner?'built-settlement':'build-vertex'+(buildMode==='settlement'&&canBuild&&showMarkers?' available':'')});
    if(owner) circle.setAttribute('fill',room.colors[owner]||'white');
    if(!owner && buildMode==='settlement' && canBuild && showMarkers) circle.addEventListener('click',()=>placeBuild('settlement','v'+i));
    overlay.append(circle);
  }
  const enabled=canBuild&&showMarkers;
  $('build-road').disabled=!enabled;
  $('build-settlement').disabled=!enabled;
  $('build-road').classList.toggle('selected',buildMode==='road');
  $('build-settlement').classList.toggle('selected',buildMode==='settlement');
  $('build-hint').textContent=!canBuild?'Roll the dice on your turn to build.':buildMode?`Click a highlighted ${buildMode==='road'?'edge':'circle'} on the island to place a ${buildMode}.`:'Select Build Road or Settlement to show available spots.';
}
async function placeBuild(kind, location) {
  try { await request(`/api/rooms/${currentRoom}/build`,{token:playerToken,kind,location}); }
  catch(error) { alert(error.message); }
}
for (const [id,kind] of [['build-road','road'],['build-settlement','settlement']]) {
  $(id).onclick=()=>{ buildMode=buildMode===kind?null:kind; if(latestRoom)renderBuildOverlay(latestRoom); };
}
function setMarkers(enabled) {
  showMarkers=enabled;
  $('build-markers-toggle').textContent=(enabled?'✓ ':'  ')+'Build Markers';
  localStorage.setItem('pentagon-markers',enabled?'on':'off');
  if(latestRoom)renderBuildOverlay(latestRoom);
}
setMarkers(localStorage.getItem('pentagon-markers')!=='off');
$('build-markers-toggle').onclick=()=>setMarkers(!showMarkers);


// v0.6.1: original island base + 19 independently randomized hex textures.
// Board state is owned by the Python server, shared through WebSockets.
const BOARD_R=70;
const TEXTURES=['forest','wheat','pasture','hills','mountain','desert'];
const TERRAIN_TINT={forest:'#27623b',wheat:'#c49b26',pasture:'#5b963e',hills:'#b55d31',mountain:'#6d7682',desert:'#d3b67d'};
function hexCenter(tile) {
  const counts=[3,4,5,4,3];
  return [450+(tile.col-(counts[tile.row]-1)/2)*Math.sqrt(3)*BOARD_R,170+tile.row*1.5*BOARD_R];
}
function hexPoints(cx,cy) {
  return Array.from({length:6},(_,k)=>{const a=(-90+60*k)*Math.PI/180;return [cx+BOARD_R*Math.cos(a),cy+BOARD_R*Math.sin(a)];});
}
function renderTerrainBoard(board) {
  if(!board) return;
  const svg=$('terrain-board');
  if(svg.dataset.seed===String(board.seed))return;
  svg.dataset.seed=String(board.seed);
  svg.replaceChildren();
  const defs=svgEl('defs',{});
  for(const type of TEXTURES) {
    const pattern=svgEl('pattern',{id:'tile-'+type,patternUnits:'userSpaceOnUse',width:180,height:180});
    pattern.append(svgEl('image',{href:'/static/img/terrain-'+type+'.jpg',x:0,y:0,width:180,height:180,preserveAspectRatio:'xMidYMid slice'}));
    defs.append(pattern);
  }
  svg.append(defs);
  svg.append(svgEl('image',{href:'/static/img/island-base.png',x:0,y:0,width:900,height:781,preserveAspectRatio:'none'}));
  for(const tile of board.tiles) {
    const [cx,cy]=hexCenter(tile);
    const points=hexPoints(cx,cy).map(p=>p.join(',')).join(' ');
    // Individual hex shapes: background artwork remains independent.
    const tileGroup=svgEl('g',{'class':'hex-cell'});
    tileGroup.append(svgEl('polygon',{points,fill:TERRAIN_TINT[tile.terrain],opacity:.95}));
    // Image texture clipped exactly to each hexagon (no baked terrain layout).
    const clipId='hex-clip-'+tile.id;
    const clip=svgEl('clipPath',{id:clipId});clip.append(svgEl('polygon',{points}));defs.append(clip);
    tileGroup.append(svgEl('image',{href:'/static/img/terrain-'+tile.terrain+'.jpg',x:cx-BOARD_R*1.05,y:cy-BOARD_R,width:BOARD_R*2.1,height:BOARD_R*2,preserveAspectRatio:'xMidYMid slice','clip-path':'url(#'+clipId+')'}));
    tileGroup.append(svgEl('polygon',{points,'class':'hex-rim'}));
    if(tile.number!==null) {
      tileGroup.append(svgEl('circle',{cx,cy,r:21,'class':'tile-number'}));
      const label=svgEl('text',{x:cx,y:cy+1,'class':'tile-number-text'+([6,8].includes(tile.number)?' hot':'')});label.textContent=tile.number;tileGroup.append(label);
    } else {
      tileGroup.append(svgEl('circle',{cx,cy,r:20,'class':'tile-number'}));
      const label=svgEl('text',{x:cx,y:cy+1,'class':'tile-number-text'});label.textContent='♟';tileGroup.append(label);
    }
    svg.append(tileGroup);
  }
  const seed=svgEl('text',{x:14,y:763,'class':'board-seed'});seed.textContent='MAP SEED: '+board.seed;svg.append(seed);
}
