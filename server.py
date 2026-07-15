from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import websocket
import threading
import json
import uuid
import math
import os
import random
import time

os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = Ursina()
window.title = 'Project: Build & Battle'
window.borderless = False
window.exit_button.visible = False

# ==========================================
# CLIENT SETTINGS & VERSION
# ==========================================
SERVER_URL = 'wss://fortnite-5xm3.onrender.com'
GAME_VERSION = "1.1.0"
ws = None

# --- PLAYER IDENTITY & STATS ---
my_id = str(uuid.uuid4())
my_name = f"Player_{random.randint(1000, 9999)}"
my_color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))
my_kills = 0
my_assists = 0
my_score = 0
recent_attackers = {} # Tracks {attacker_id: timestamp} for Assists
last_attacker_id = ""

other_players = {}
other_player_labels = {}
network_queue = [] 
leaderboard_data = {}

game_started = False
connecting = False
connected_successfully = False
connection_error = ""

current_mode = 'combat' 
is_aiming = False       
is_reloading = False
is_dead = False 

my_health = 100
current_weapon = 1 
build_mode = 'wall'
GRID_SIZE = 4 
BUILD_RANGE = GRID_SIZE * 1.5 
built_cells = {} 

player = None
ground = None
preview_block = None
ui_elements = {}

damage_borders = []
hit_text_ui = None
death_screen = None
respawn_text = None
scope_ui = None
crosshair = None
hitmarker = None
damage_dealt_ui = None

gun_entities = {}
active_gun = None

weapons = {
    0: {'name': 'Pickaxe', 'dmg': 20, 'bdmg': 50, 'color': color.gray, 'cooldown': 0.4, 'ammo': 999, 'max_ammo': 999, 'reload': 0, 'spread': 0},
    1: {'name': 'Assault Rifle', 'dmg': 15, 'bdmg': 15, 'color': color.dark_gray, 'cooldown': 0.15, 'ammo': 30, 'max_ammo': 30, 'reload': 1.5, 'spread': 0.02},
    2: {'name': 'Shotgun', 'dmg': 12, 'bdmg': 10, 'color': color.orange, 'cooldown': 1.0, 'ammo': 5, 'max_ammo': 5, 'reload': 2.5, 'spread': 0.1},
    3: {'name': 'Heavy Sniper', 'dmg': 90, 'bdmg': 150, 'color': color.green, 'cooldown': 2.0, 'ammo': 1, 'max_ammo': 1, 'reload': 3.0, 'spread': 0}
}
last_fired = 0

def rgb_to_hex(r, g, b):
    return f"#{int(r):02x}{int(g):02x}{int(b):02x}"

# ==========================================
# NETWORKING & HANDSHAKE
# ==========================================
def receive_data():
    global ws
    while True:
        try:
            data = ws.recv()
            if not data: break
            network_queue.append(json.loads(data))
        except: 
            # If the socket dies, crash the game
            invoke(application.quit)
            break

def try_connect_background():
    global ws, connected_successfully, connection_error, connecting
    try:
        ws = websocket.WebSocket()
        ws.connect(SERVER_URL, timeout=60) 
        
        handshake = json.dumps({'type': 'join', 'id': my_id, 'version': GAME_VERSION})
        ws.send(handshake)
        
        threading.Thread(target=receive_data, daemon=True).start()
        connected_successfully = True
    except:
        connection_error = "Server offline."
        connecting = False

def start_game():
    global connecting
    if connecting: return 
    connecting = True
    ui_elements['status'].text = f"Connecting (v{GAME_VERSION})..."
    ui_elements['status'].color = color.yellow
    threading.Thread(target=try_connect_background, daemon=True).start()

# ==========================================
# UI LOBBY
# ==========================================
menu_parent = Entity(parent=camera.ui)
Entity(parent=menu_parent, model='quad', scale=(2, 1), color=color.rgba(15, 15, 20, 255))
Text(text="BUILD & BATTLE", parent=menu_parent, y=0.3, scale=3, origin=(0,0), color=color.cyan)
Text(text=f"v{GAME_VERSION}", parent=menu_parent, y=0.2, scale=1.5, origin=(0,0), color=color.gray)
Button(text='PLAY ONLINE', parent=menu_parent, y=-0.05, scale=(0.4, 0.12), color=color.rgba(0, 150, 100, 255)).on_click = start_game
ui_elements['status'] = Text(text="", parent=menu_parent, y=-0.25, origin=(0,0), color=color.white)

# ==========================================
# WEAPONS
# ==========================================
def build_weapons():
    pickaxe = Entity(parent=camera, position=(0.3, -0.3, 0.5), visible=False)
    Entity(parent=pickaxe, model='cube', color=color.brown, scale=(0.02, 0.6, 0.02), rotation_x=90) 
    Entity(parent=pickaxe, model='cube', color=color.gray, scale=(0.3, 0.1, 0.05), position=(0, 0, 0.25))
    gun_entities[0] = {'entity': pickaxe}

    ar = Entity(parent=camera, position=(0.3, -0.3, 0.5), visible=False)
    Entity(parent=ar, model='cube', color=color.dark_gray, scale=(0.08, 0.1, 0.5)) 
    Entity(parent=ar, model='cube', color=color.black, scale=(0.03, 0.03, 0.4), position=(0, 0, 0.35)) 
    gun_entities[1] = {'entity': ar}

    shotgun = Entity(parent=camera, position=(0.3, -0.3, 0.5), visible=False)
    Entity(parent=shotgun, model='cube', color=color.orange, scale=(0.12, 0.12, 0.3)) 
    gun_entities[2] = {'entity': shotgun}

    sniper = Entity(parent=camera, position=(0.3, -0.3, 0.5), visible=False)
    Entity(parent=sniper, model='cube', color=color.olive, scale=(0.08, 0.12, 0.6)) 
    Entity(parent=sniper, model='cube', color=color.black, scale=(0.05, 0.05, 0.2), position=(0, 0.08, 0.1)) 
    gun_entities[3] = {'entity': sniper}

def equip_weapon(w_id):
    global active_gun, current_weapon, current_mode, is_reloading, is_aiming
    if is_reloading or is_dead: return
    if active_gun: active_gun.visible = False
    
    current_mode = 'combat'
    current_weapon = w_id
    active_gun = gun_entities[w_id]['entity']
    
    is_aiming = False
    camera.fov = 90
    if scope_ui: scope_ui.visible = False
    if crosshair: crosshair.visible = True
    active_gun.visible = True
    
    if preview_block: preview_block.visible = False
    update_hud()

def update_hud():
    wep = weapons[current_weapon]
    if current_mode == 'combat':
        ammo_txt = "∞" if current_weapon == 0 else f"{wep['ammo']}/{wep['max_ammo']}"
        ui_elements['wep'].text = f"[{current_weapon}] {wep['name']} | Ammo: {ammo_txt} | Build: Z,X,C"
    else:
        ui_elements['wep'].text = f"BUILD: {build_mode.upper()} | Combat: 0,1,2,3"

def reload_weapon():
    global is_reloading, is_aiming
    wep = weapons[current_weapon]
    if wep['ammo'] == wep['max_ammo'] or current_weapon == 0 or is_dead: return
    
    is_reloading = True
    is_aiming = False
    camera.fov = 90
    if scope_ui: scope_ui.visible = False
    if crosshair: crosshair.visible = True
    if active_gun:
        active_gun.visible = True
        active_gun.position = Vec3(0.3, -0.3, 0.5)

    ui_elements['wep'].text = f"RELOADING..."
    
    def finish_reload():
        global is_reloading
        if not is_dead:
            wep['ammo'] = wep['max_ammo']
            is_reloading = False
            update_hud()
    
    invoke(finish_reload, delay=wep['reload'])

def spawn_hit_particle(pos):
    spark = Entity(model='sphere', color=color.yellow, position=pos, scale=0.1, unlit=True)
    spark.animate_scale(0.5, duration=0.1)
    spark.animate_color(color.clear, duration=0.1)
    destroy(spark, delay=0.15)

# ==========================================
# SMART BUILDING 
# ==========================================
def get_target_cell():
    hit_info = raycast(camera.world_position, camera.forward, distance=BUILD_RANGE, ignore=[player, preview_block, active_gun])
    if hit_info.hit:
        target_pos = hit_info.world_point + (hit_info.normal * 0.1)
    else:
        target_pos = camera.world_position + (camera.forward * (GRID_SIZE * 0.8))
        
    cx = round(target_pos.x / GRID_SIZE)
    cy = max(0, math.floor(target_pos.y / GRID_SIZE))
    cz = round(target_pos.z / GRID_SIZE)
    return cx, cy, cz

def is_supported(cx, cy, cz):
    if cy == 0: return True 
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            for dz in [-1, 0, 1]:
                if dx == 0 and dy == 0 and dz == 0: continue
                if (cx+dx, cy+dy, cz+dz) in built_cells: return True
    return False

def check_structural_integrity():
    if not built_cells: return
    visited = set()
    queue = []
    
    for coord in list(built_cells.keys()):
        if coord[1] == 0:
            queue.append(coord)
            visited.add(coord)
            
    head = 0
    while head < len(queue):
        cx, cy, cz = queue[head]
        head += 1
        for dx, dy, dz in [(-1,0,0), (1,0,0), (0,-1,0), (0,1,0), (0,0,-1), (0,0,1)]:
            neighbor = (cx+dx, cy+dy, cz+dz)
            if neighbor in built_cells and neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
                
    unsupported = [coord for coord in built_cells if coord not in visited]
    for coord in unsupported:
        block = built_cells[coord]
        block_id = block.block_id
        destroy_block_local(coord[0], coord[1], coord[2], check_stability=False)
        try: ws.send(json.dumps({'type': 'destroy_block', 'block_id': block_id, 'cx': coord[0], 'cy': coord[1], 'cz': coord[2]}))
        except: pass

def get_world_pos_and_rot(cx, cy, cz, b_type, player_rot_y):
    x = cx * GRID_SIZE
    y = cy * GRID_SIZE
    z = cz * GRID_SIZE
    rot_y = round(player_rot_y / 90) * 90 % 360
    base_y = y + (GRID_SIZE / 2)
    
    if b_type == 'floor':
        return Vec3(x, y + 0.1, z), 0, (GRID_SIZE, 0.2, GRID_SIZE)
    elif b_type == 'ramp':
        return Vec3(x, base_y - 0.1, z), rot_y, (GRID_SIZE, 0.2, GRID_SIZE * 1.414) 
    elif b_type == 'wall':
        if rot_y == 0:   z += GRID_SIZE/2
        elif rot_y == 90:  x += GRID_SIZE/2
        elif rot_y == 180: z -= GRID_SIZE/2
        elif rot_y == 270: x -= GRID_SIZE/2
        return Vec3(x, base_y, z), rot_y, (GRID_SIZE, GRID_SIZE, 0.2)

def place_structure_local(cx, cy, cz, b_type, rot_y, block_id):
    pos, final_rot, scale = get_world_pos_and_rot(cx, cy, cz, b_type, rot_y)
    col_type = 'mesh' if b_type == 'ramp' else 'box'
    
    block = Entity(model='cube', texture='white_cube', color=color.cyan, position=pos, rotation=(0 if b_type!='ramp' else -45, final_rot, 0), scale=scale, collider=col_type)
    block.block_id = block_id
    block.hp = 150 
    block.cx, block.cy, block.cz = cx, cy, cz
    
    built_cells[(cx, cy, cz)] = block
    
    def destroy_self():
        if (cx, cy, cz) in built_cells and built_cells[(cx, cy, cz)] == block:
            destroy_block_local(cx, cy, cz)
            try: ws.send(json.dumps({'type': 'destroy_block', 'block_id': block_id, 'cx': cx, 'cy': cy, 'cz': cz}))
            except: pass
    invoke(destroy_self, delay=60)

def destroy_block_local(cx, cy, cz, check_stability=True):
    if (cx, cy, cz) in built_cells:
        destroy(built_cells[(cx, cy, cz)])
        del built_cells[(cx, cy, cz)]
        if check_stability:
            check_structural_integrity()

# ==========================================
# DEATH & RESPAWN
# ==========================================
def handle_death():
    global is_dead, my_health, recent_attackers
    is_dead = True
    my_health = 0
    ui_elements['health'].text = f"HP: {my_health}"
    
    player.disable() 
    if active_gun: active_gun.visible = False
    if preview_block: preview_block.visible = False
    if scope_ui: scope_ui.visible = False
    if crosshair: crosshair.visible = False
    
    death_screen.visible = True
    camera.fov = 90
    
    # Calculate Assists (anyone who did damage in last 10s, excluding the final killer)
    curr_time = time.time()
    assist_ids = [a_id for a_id, t in recent_attackers.items() if curr_time - t < 10 and a_id != last_attacker_id]
    
    try:
        ws.send(json.dumps({
            'type': 'eliminated',
            'killer_id': last_attacker_id,
            'assist_ids': assist_ids,
            'victim_id': my_id,
            'victim_name': my_name
        }))
    except: pass
    
    def countdown(t):
        if t > 0:
            respawn_text.text = f"Respawning in {t}..."
            invoke(countdown, t-1, delay=1)
        else:
            respawn()
    countdown(3)

def respawn():
    global is_dead, my_health, is_reloading, last_attacker_id, is_aiming, recent_attackers
    is_dead = False
    is_reloading = False
    is_aiming = False
    last_attacker_id = ""
    recent_attackers.clear() # Clear damage history on respawn
    
    my_health = 100
    ui_elements['health'].text = f"HP: {my_health}"
    
    player.position = (random.randint(-20, 20), 20, random.randint(-20, 20)) 
    player.enable()
    death_screen.visible = False
    camera.fov = 90
    
    for w in weapons.values():
        w['ammo'] = w['max_ammo']
        
    equip_weapon(1)

# ==========================================
# MAIN LOOP
# ==========================================
def update():
    global game_started, connected_successfully, connecting, connection_error
    global ground, player, preview_block, my_health, damage_borders
    global hit_text_ui, hitmarker, damage_dealt_ui, crosshair, death_screen, respawn_text, scope_ui
    global my_kills, my_score, my_assists, ws, recent_attackers
    
    if connection_error != "":
        ui_elements['status'].text = connection_error
        ui_elements['status'].color = color.red
        
    if not game_started and connected_successfully:
        menu_parent.enabled = False
        mouse.locked = True
        
        Sky(texture='sky_sunset')
        ground = Entity(model='plane', scale=(150, 1, 150), texture='grass', texture_scale=(30, 30), collider='box')
        
        player = FirstPersonController()
        player.y = 10
        player.step_height = 1.2 
        
        ui_elements['health'] = Text(text=f"HP: {my_health}", position=(-0.85, -0.4), scale=2, color=color.green)
        ui_elements['stats'] = Text(text=f"SCORE: {my_score} | K/A: {my_kills}/{my_assists}", position=(-0.85, 0.45), scale=1.5, color=color.yellow)
        ui_elements['wep'] = Text(text="", position=(0.3, -0.4), scale=1.5, color=color.white)
        ui_elements['leaderboard'] = Text(text="LEADERBOARD", position=(0.6, 0.45), scale=1.5, color=color.white)
        
        for _ in range(4):
            damage_borders.append(Entity(parent=camera.ui, model='quad', color=color.rgba(255, 0, 0, 0), z=-1))
        damage_borders[0].scale, damage_borders[0].y = (2, 0.05), 0.475  
        damage_borders[1].scale, damage_borders[1].y = (2, 0.05), -0.475 
        damage_borders[2].scale, damage_borders[2].x = (0.05, 1), -0.875 
        damage_borders[3].scale, damage_borders[3].x = (0.05, 1), 0.875  
        
        hit_text_ui = Text(parent=camera.ui, text="", color=color.red, scale=3, origin=(0,0), y=0.1)
        hitmarker = Text(parent=camera.ui, text="X", color=color.red, scale=3, origin=(0,0), visible=False)
        damage_dealt_ui = Text(parent=camera.ui, text="", color=color.yellow, scale=2, origin=(0,0), x=0.03, y=0.03)
        
        death_screen = Entity(parent=camera.ui, model='quad', color=color.rgba(0, 0, 0, 220), scale=(2, 1), z=-2, visible=False)
        Text(parent=death_screen, text="YOU WERE ELIMINATED", scale=3, origin=(0,0), y=0.1, color=color.red)
        respawn_text = Text(parent=death_screen, text="Respawning in 3...", scale=2, origin=(0,0), y=-0.1, color=color.white)
        
        crosshair = Entity(parent=camera.ui, model='quad', color=color.white, scale=(0.008, 0.008), z=-1)
        
        scope_ui = Entity(parent=camera.ui, visible=False)
        Entity(parent=scope_ui, model='quad', color=color.black, scale=(2, 0.002)) 
        Entity(parent=scope_ui, model='quad', color=color.black, scale=(0.002, 2)) 
        Entity(parent=scope_ui, model='quad', color=color.red, scale=(0.01, 0.01)) 
        
        build_weapons()
        equip_weapon(1)
        
        preview_block = Entity(model='cube', color=color.rgba(0, 0, 255, 100), unlit=True, collider=None, visible=False)
        
        game_started = True
        connected_successfully = False 
        
    if game_started and ws and player:
        # Drop players who haven't sent a packet in 3 seconds
        current_time = time.time()
        to_drop = [pid for pid, ent in other_players.items() if hasattr(ent, 'last_seen') and current_time - ent.last_seen > 3.0]
        for pid in to_drop:
            destroy(other_players[pid])
            del other_players[pid]
            if pid in leaderboard_data: del leaderboard_data[pid]

        leaderboard_data[my_id] = {'name': my_name, 'color': my_color, 'score': my_score}
        sorted_players = sorted(leaderboard_data.values(), key=lambda x: x['score'], reverse=True)
        lb_text = "<white>LEADERBOARD\n"
        for p in sorted_players[:5]: 
            hex_c = rgb_to_hex(*p['color'])
            lb_text += f"<{hex_c}>{p['name']} <white>- {p['score']}\n"
        ui_elements['leaderboard'].text = lb_text

        if current_mode == 'build' and not is_dead:
            cx, cy, cz = get_target_cell()
            if is_supported(cx, cy, cz):
                preview_block.color = color.rgba(0, 200, 255, 120)
            else:
                preview_block.color = color.rgba(255, 0, 0, 120)
                
            pos, rot, scale = get_world_pos_and_rot(cx, cy, cz, build_mode, player.rotation_y)
            preview_block.position = pos
            preview_block.rotation = (0 if build_mode!='ramp' else -45, rot, 0)
            preview_block.scale = scale

        while len(network_queue) > 0:
            info = network_queue.pop(0)
            
            # --- ERROR HANDLING (Crash on Kick) ---
            if info.get('type') == 'error':
                application.quit() 
                return
            
            elif info['type'] == 'player':
                pid = info['id']
                p_score = info.get('score', 0)
                p_color = info.get('color', (255, 0, 255))
                p_name = info.get('name', 'Unknown')
                p_dead = info.get('dead', False)
                
                leaderboard_data[pid] = {'name': p_name, 'color': p_color, 'score': p_score}
                c_obj = color.rgb(p_color[0], p_color[1], p_color[2])
                
                if pid not in other_players:
                    other_players[pid] = Entity()
                    other_players[pid].pid = pid
                    hitbox = Entity(parent=other_players[pid], model='cube', color=color.clear, collider='box', scale=(1, 2, 1), y=1)
                    hitbox.pid = pid 
                    
                    p_head = Entity(parent=other_players[pid], model='cube', color=color.rgb(220,185,155), scale=(0.5, 0.5, 0.5), y=1.85)
                    # Add Eyes!
                    Entity(parent=p_head, model='cube', color=color.black, scale=(0.1, 0.1, 0.1), position=(0.25, 0.1, 0.5))
                    Entity(parent=p_head, model='cube', color=color.black, scale=(0.1, 0.1, 0.1), position=(-0.25, 0.1, 0.5))
                    
                    p_torso = Entity(parent=other_players[pid], model='cube', color=c_obj, scale=(0.8, 0.8, 0.4), y=1.1)
                    
                    # Add Visible Gun Pivot to Torso
                    gun_pivot = Entity(parent=other_players[pid], y=1.5)
                    other_players[pid].gun_pivot = gun_pivot
                    Entity(parent=gun_pivot, model='cube', color=color.dark_gray, scale=(0.15, 0.15, 0.8), position=(0.3, -0.2, 0.4))
                    
                    p_armL = Entity(parent=other_players[pid], model='cube', color=c_obj.tint(-0.2), scale=(0.2, 0.8, 0.2), x=0.55, y=1.1)
                    p_armR = Entity(parent=other_players[pid], model='cube', color=c_obj.tint(-0.2), scale=(0.2, 0.8, 0.2), x=-0.55, y=1.1)
                    p_legL = Entity(parent=other_players[pid], model='cube', color=color.dark_gray, scale=(0.3, 0.8, 0.3), x=0.22, y=0.4)
                    p_legR = Entity(parent=other_players[pid], model='cube', color=color.dark_gray, scale=(0.3, 0.8, 0.3), x=-0.22, y=0.4)
                    
                    for part in [p_head, p_torso, p_armL, p_armR, p_legL, p_legR]:
                        part.original_color = part.color
                    
                    other_player_labels[pid] = Text(parent=other_players[pid], text=p_name, y=2.3, scale=5, billboard=True, origin=(0,0), color=c_obj)
                    
                other_players[pid].position = (info['x'], info['y'], info['z'])
                other_players[pid].rotation_y = info['rot_y']
                
                # Apply Pitch (Look Up/Down) to their gun
                if hasattr(other_players[pid], 'gun_pivot'):
                    other_players[pid].gun_pivot.rotation_x = info.get('rot_x', 0)
                
                # Hide if they are dead (but keep updating position/heartbeat so they aren't deleted)
                other_players[pid].enabled = not p_dead
                other_players[pid].last_seen = time.time()
            
            elif info['type'] == 'build':
                b_id = info.get('block_id', str(uuid.uuid4()))
                place_structure_local(info['cx'], info['cy'], info['cz'], info['b_type'], info['rot_y'], b_id)
                
            elif info['type'] == 'destroy_block':
                destroy_block_local(info['cx'], info['cy'], info['cz'], check_stability=False)
                
            elif info['type'] == 'damage':
                if info['target_id'] == my_id and not is_dead:
                    my_health -= info['amount']
                    last_attacker_id = info.get('attacker_id', '') 
                    recent_attackers[last_attacker_id] = time.time() # Log for assists
                    
                    ui_elements['health'].text = f"HP: {my_health}"
                    
                    for border in damage_borders:
                        border.color = color.rgba(255, 0, 0, 180)
                        border.animate_color(color.rgba(255, 0, 0, 0), duration=0.4)
                    
                    hit_text_ui.text = f"-{info['amount']} HP"
                    hit_text_ui.color = color.rgba(255, 50, 50, 255)
                    hit_text_ui.animate_color(color.clear, duration=0.6)
                    
                    if my_health <= 0:
                        handle_death()
                
                elif info['target_id'] in other_players:
                    enemy = other_players[info['target_id']]
                    for part in enemy.children:
                        if hasattr(part, 'original_color'):
                            part.color = color.red
                    
                    def reset_color(e_id=info['target_id']):
                        if e_id in other_players:
                            for p in other_players[e_id].children:
                                if hasattr(p, 'original_color'):
                                    p.color = p.original_color
                    invoke(reset_color, delay=0.2)
                    
            elif info['type'] == 'eliminated':
                # Apply Kill Points
                if info['killer_id'] == my_id:
                    my_kills += 1
                    my_score += 100
                    hit_text_ui.text = f"ELIMINATED {info['victim_name'].upper()}!"
                    hit_text_ui.color = color.cyan
                    hit_text_ui.animate_color(color.clear, duration=1.5)
                
                # Apply Assist Points
                elif my_id in info.get('assist_ids', []):
                    my_assists += 1
                    my_score += 50
                    hit_text_ui.text = f"ASSISTED ON {info['victim_name'].upper()}!"
                    hit_text_ui.color = color.orange
                    hit_text_ui.animate_color(color.clear, duration=1.5)
                    
                ui_elements['stats'].text = f"SCORE: {my_score} | K/A: {my_kills}/{my_assists}"

        try:
            # We now ALWAYS send this packet, even if dead, to prevent disconnecting!
            ws.send(json.dumps({
                'type': 'player', 'id': my_id, 
                'x': player.x, 'y': player.y, 'z': player.z, 
                'rot_y': player.rotation_y, 'rot_x': camera.rotation_x, # Added Camera Pitch
                'color': my_color, 'name': my_name, 'score': my_score, 'dead': is_dead # Added Dead status
            }))
        except: pass

# ==========================================
# MOUSE & KEYBOARD
# ==========================================
def input(key):
    global build_mode, current_mode, is_aiming, last_fired
    if not game_started or is_reloading or is_dead: return

    if key in ['0', '1', '2', '3']:
        equip_weapon(int(key)) 

    if key in ['z', 'x', 'c']:
        current_mode = 'build'
        active_gun.visible = False
        preview_block.visible = True
        
        if scope_ui: scope_ui.visible = False
        if crosshair: crosshair.visible = True
        camera.fov = 90
        is_aiming = False
        
        if key == 'z': build_mode = 'wall'
        if key == 'x': build_mode = 'floor'
        if key == 'c': build_mode = 'ramp'
        
        update_hud()

    if key == 'r' and current_mode == 'combat':
        reload_weapon()

    if key == 'left mouse down':
        if current_mode == 'build':
            cx, cy, cz = get_target_cell()
            if is_supported(cx, cy, cz) and (cx, cy, cz) not in built_cells:
                snap_rot = round(player.rotation_y / 90) * 90
                block_id = str(uuid.uuid4())
                place_structure_local(cx, cy, cz, build_mode, snap_rot, block_id)
                try:
                    ws.send(json.dumps({'type': 'build', 'block_id': block_id, 'b_type': build_mode, 'cx': cx, 'cy': cy, 'cz': cz, 'rot_y': snap_rot}))
                except: pass
                
        elif current_mode == 'combat':
            wep = weapons[current_weapon]
            if time.time() - last_fired < wep['cooldown']: return
            if wep['ammo'] <= 0:
                reload_weapon()
                return
                
            last_fired = time.time()
            if current_weapon != 0: wep['ammo'] -= 1
            update_hud()
            
            base_pos = Vec3(0, -0.2, 0.4) if is_aiming else Vec3(0.3, -0.3, 0.5)
            
            if current_weapon == 0:
                active_gun.animate_rotation((45, -45, 0), duration=0.1)
                invoke(setattr, active_gun, 'rotation', Vec3(0,0,0), delay=0.15)
                hit_info = raycast(camera.world_position, camera.forward, distance=3, ignore=[player, preview_block, active_gun])
            else:
                active_gun.position = base_pos + Vec3(0, 0.05, -0.1)
                invoke(setattr, active_gun, 'position', base_pos, delay=0.1)
                
                pellets = 5 if current_weapon == 2 else 1
                for _ in range(pellets):
                    shoot_dir = camera.forward + Vec3(random.uniform(-wep['spread'], wep['spread']), random.uniform(-wep['spread'], wep['spread']), 0)
                    hit_info = raycast(camera.world_position, shoot_dir, distance=200, ignore=[player, preview_block, active_gun])
                    
                    dist = hit_info.distance if hit_info.hit else 200
                    target_pt = hit_info.world_point if hit_info.hit else camera.world_position + (shoot_dir * dist)
                    
                    trail = Entity(model='cube', color=color.rgba(255, 255, 100, 200), unlit=True)
                    trail.position = active_gun.world_position
                    trail.look_at(target_pt)
                    trail.scale = (0.02, 0.02, dist)
                    trail.position += trail.forward * (dist / 2) 
                    
                    trail.animate_color(color.clear, duration=0.2)
                    destroy(trail, delay=0.25)

            if hit_info.hit:
                spawn_hit_particle(hit_info.world_point)
                
                if hasattr(hit_info.entity, 'pid'):
                    hitmarker.visible = True
                    invoke(setattr, hitmarker, 'visible', False, delay=0.2)
                    
                    damage_dealt_ui.text = str(wep['dmg'])
                    damage_dealt_ui.color = color.rgba(255, 255, 0, 255)
                    damage_dealt_ui.animate_y(0.08, duration=0.5)
                    damage_dealt_ui.animate_color(color.clear, duration=0.5)
                    invoke(setattr, damage_dealt_ui, 'y', 0.03, delay=0.5) 
                    
                    try: ws.send(json.dumps({'type': 'damage', 'target_id': hit_info.entity.pid, 'amount': wep['dmg'], 'attacker_id': my_id}))
                    except: pass
                
                elif hasattr(hit_info.entity, 'block_id'):
                    hit_info.entity.hp -= wep['bdmg']
                    hit_info.entity.color = color.red 
                    invoke(setattr, hit_info.entity, 'color', color.cyan, delay=0.1)
                    
                    if hit_info.entity.hp <= 0:
                        cx, cy, cz = hit_info.entity.cx, hit_info.entity.cy, hit_info.entity.cz
                        b_id = hit_info.entity.block_id
                        destroy_block_local(cx, cy, cz, check_stability=True)
                        try: ws.send(json.dumps({'type': 'destroy_block', 'block_id': b_id, 'cx': cx, 'cy': cy, 'cz': cz}))
                        except: pass

    if key == 'right mouse down' and current_mode == 'combat':
        is_aiming = True
        if current_weapon == 3:
            camera.fov = 10 
            scope_ui.visible = True
            crosshair.visible = False
            active_gun.visible = False
        else:
            camera.fov = 60 
            active_gun.position = Vec3(0, -0.2, 0.4) 

    if key == 'right mouse up' and current_mode == 'combat':
        is_aiming = False
        camera.fov = 90 
        if current_weapon == 3:
            scope_ui.visible = False
            crosshair.visible = True
            active_gun.visible = True
        else:
            active_gun.position = Vec3(0.3, -0.3, 0.5) 

    if key == 'escape':
        application.quit()

app.run()
