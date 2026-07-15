from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import websocket
import threading
import json
import uuid
import math
import os

# Fix VS Code pathing
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# ==========================================
# 1. GLOBAL SETUP
# ==========================================
app = Ursina()
window.title = 'Project: Build & Battle'
window.borderless = False
window.exit_button.visible = False

SERVER_URL = 'wss://fortnite-5xm3.onrender.com'
ws = None
my_id = str(uuid.uuid4())
other_players = {}
network_queue = [] 

game_started = False
connecting = False
connected_successfully = False
connection_error = ""

# --- NEW: State Machine Variables ---
current_mode = 'combat' # Can be 'combat' or 'build'
is_aiming = False       # Tracks if the player is holding Right-Click

my_health = 100
current_weapon = 1 
build_mode = 'wall'
GRID_SIZE = 4 
BUILD_RANGE = GRID_SIZE * 1.5 
built_cells = set() 

player = None
ground = None
preview_block = None
ui_elements = {}

gun_entities = {}
active_gun = None

# ==========================================
# 2. NETWORKING
# ==========================================
def receive_data():
    global ws
    while True:
        try:
            data = ws.recv()
            if not data: break
            network_queue.append(json.loads(data))
        except: break

def try_connect_background():
    global ws, connected_successfully, connection_error, connecting
    try:
        ws = websocket.WebSocket()
        ws.connect(SERVER_URL, timeout=60) 
        threading.Thread(target=receive_data, daemon=True).start()
        connected_successfully = True
    except:
        connection_error = "Server offline."
        connecting = False

def start_game():
    global connecting
    if connecting: return 
    connecting = True
    ui_elements['status'].text = "Waking up cloud server..."
    ui_elements['status'].color = color.yellow
    threading.Thread(target=try_connect_background, daemon=True).start()

# ==========================================
# 3. UI LOBBY
# ==========================================
menu_parent = Entity(parent=camera.ui)
Entity(parent=menu_parent, model='quad', scale=(2, 1), color=color.rgba(15, 15, 20, 255))
Text(text="BUILD & BATTLE", parent=menu_parent, y=0.3, scale=3, origin=(0,0), color=color.cyan)
Button(text='PLAY ONLINE', parent=menu_parent, y=-0.05, scale=(0.4, 0.12), color=color.rgba(0, 150, 100, 255)).on_click = start_game
ui_elements['status'] = Text(text="", parent=menu_parent, y=-0.25, origin=(0,0), color=color.white)
Button(text='X', parent=menu_parent, position=(0.85, 0.45), scale=(0.05, 0.05), color=color.red).on_click = application.quit

# ==========================================
# 4. WEAPON SETUP
# ==========================================
def build_weapons():
    ar = Entity(parent=camera, position=(0.3, -0.3, 0.5), visible=False)
    Entity(parent=ar, model='cube', color=color.dark_gray, scale=(0.08, 0.1, 0.5)) 
    Entity(parent=ar, model='cube', color=color.black, scale=(0.03, 0.03, 0.4), position=(0, 0, 0.35)) 
    Entity(parent=ar, model='cube', color=color.black, scale=(0.04, 0.2, 0.1), position=(0, -0.1, 0.05)) 
    gun_entities[1] = {'entity': ar, 'name': 'Assault Rifle', 'dmg': 15}

    shotgun = Entity(parent=camera, position=(0.3, -0.3, 0.5), visible=False)
    Entity(parent=shotgun, model='cube', color=color.orange, scale=(0.12, 0.12, 0.3)) 
    Entity(parent=shotgun, model='cube', color=color.gray, scale=(0.1, 0.05, 0.3), position=(0, 0, 0.25)) 
    gun_entities[2] = {'entity': shotgun, 'name': 'Tactical Shotgun', 'dmg': 40}

    sniper = Entity(parent=camera, position=(0.3, -0.3, 0.5), visible=False)
    Entity(parent=sniper, model='cube', color=color.olive, scale=(0.08, 0.12, 0.6)) 
    Entity(parent=sniper, model='cube', color=color.black, scale=(0.03, 0.03, 0.7), position=(0, 0, 0.5)) 
    Entity(parent=sniper, model='cube', color=color.black, scale=(0.05, 0.05, 0.2), position=(0, 0.08, 0.1)) 
    gun_entities[3] = {'entity': sniper, 'name': 'Heavy Sniper', 'dmg': 90}

def equip_weapon(w_id):
    global active_gun, current_weapon, current_mode
    if active_gun:
        active_gun.visible = False
    
    current_mode = 'combat' # Force combat mode
    current_weapon = w_id
    active_gun = gun_entities[w_id]['entity']
    active_gun.visible = True
    
    if preview_block: preview_block.visible = False
    ui_elements['wep'].text = f"COMBAT: [{w_id}] {gun_entities[w_id]['name']} | Build: Z,X,C"

def spawn_hit_particle(pos):
    spark = Entity(model='sphere', color=color.yellow, position=pos, scale=0.1, unlit=True)
    spark.animate_scale(0.5, duration=0.1)
    spark.animate_color(color.clear, duration=0.1)
    destroy(spark, delay=0.15)

# ==========================================
# 5. SMART BUILDING LOGIC
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

def get_world_pos_and_rot(cx, cy, cz, b_type, player_rot_y):
    x = cx * GRID_SIZE
    y = cy * GRID_SIZE
    z = cz * GRID_SIZE
    rot_y = round(player_rot_y / 90) * 90 % 360
    base_y = y + (GRID_SIZE / 2)
    
    if b_type == 'floor':
        return Vec3(x, y + 0.1, z), 0, (GRID_SIZE, 0.2, GRID_SIZE)
    elif b_type == 'ramp':
        return Vec3(x, base_y, z), rot_y, (GRID_SIZE, 0.2, GRID_SIZE * 1.414) 
    elif b_type == 'wall':
        if rot_y == 0:   z += GRID_SIZE/2
        elif rot_y == 90:  x += GRID_SIZE/2
        elif rot_y == 180: z -= GRID_SIZE/2
        elif rot_y == 270: x -= GRID_SIZE/2
        return Vec3(x, base_y, z), rot_y, (GRID_SIZE, GRID_SIZE, 0.2)

def place_structure_local(cx, cy, cz, b_type, rot_y):
    pos, final_rot, scale = get_world_pos_and_rot(cx, cy, cz, b_type, rot_y)
    Entity(model='cube', texture='white_cube', color=color.cyan, position=pos, rotation=(0 if b_type!='ramp' else -45, final_rot, 0), scale=scale, collider='box')
    built_cells.add((cx, cy, cz))

# ==========================================
# 6. GAME LOOP
# ==========================================
def update():
    global game_started, connected_successfully, ground, player, preview_block, my_health
    
    if connection_error != "":
        ui_elements['status'].text = connection_error
        ui_elements['status'].color = color.red
        
    if not game_started and connected_successfully:
        menu_parent.enabled = False
        mouse.locked = True
        
        Sky(texture='sky_sunset')
        ground = Entity(model='plane', scale=(150, 1, 150), texture='grass', texture_scale=(30, 30), collider='box')
        
        player = FirstPersonController()
        player.y = 5
        player.step_height = 1.2 
        
        ui_elements['health'] = Text(text=f"HP: {my_health}", position=(-0.85, -0.4), scale=2, color=color.green)
        ui_elements['wep'] = Text(text="", position=(0.3, -0.4), scale=1.5, color=color.white)
        
        preview_block = Entity(model='cube', color=color.rgba(0, 0, 255, 100), unlit=True, collider=None, visible=False)
        
        build_weapons()
        equip_weapon(1)
        
        game_started = True
        connected_successfully = False 
        
    if game_started and ws and player:
        # --- UPDATE HOLOGRAM ONLY IF IN BUILD MODE ---
        if current_mode == 'build':
            cx, cy, cz = get_target_cell()
            if is_supported(cx, cy, cz):
                preview_block.color = color.rgba(0, 200, 255, 120)
            else:
                preview_block.color = color.rgba(255, 0, 0, 120)
                
            pos, rot, scale = get_world_pos_and_rot(cx, cy, cz, build_mode, player.rotation_y)
            preview_block.position = pos
            preview_block.rotation = (0 if build_mode!='ramp' else -45, rot, 0)
            preview_block.scale = scale

        # Process Network Queue
        while len(network_queue) > 0:
            info = network_queue.pop(0)
            if info['type'] == 'player':
                pid = info['id']
                if pid not in other_players:
                    other_players[pid] = Entity(model='cube', color=color.magenta, scale=(1.2, 2.5, 1.2), collider='box')
                    other_players[pid].pid = pid 
                other_players[pid].position = (info['x'], info['y'], info['z'])
                other_players[pid].rotation_y = info['rot_y']
            elif info['type'] == 'build':
                place_structure_local(info['cx'], info['cy'], info['cz'], info['b_type'], info['rot_y'])
            elif info['type'] == 'damage' and info['target_id'] == my_id:
                my_health -= info['amount']
                if my_health <= 0:
                    my_health = 100 
                    player.position = (0, 10, 0) 
                ui_elements['health'].text = f"HP: {my_health}"

        try:
            ws.send(json.dumps({'type': 'player', 'id': my_id, 'x': player.x, 'y': player.y, 'z': player.z, 'rot_y': player.rotation_y}))
        except: pass

def input(key):
    global build_mode, current_mode, is_aiming
    if not game_started: return

    # --- MODE SWAPPING ---
    if key in ['1', '2', '3']:
        equip_weapon(int(key)) # This automatically forces combat mode

    if key in ['z', 'x', 'c']:
        current_mode = 'build'
        active_gun.visible = False
        preview_block.visible = True
        
        if key == 'z': build_mode = 'wall'
        if key == 'x': build_mode = 'floor'
        if key == 'c': build_mode = 'ramp'
        
        # Reset ADS if they swap to build mode while aiming
        camera.fov = 90
        is_aiming = False
        
        ui_elements['wep'].text = f"BUILD: {build_mode.upper()} | Combat: 1,2,3"

    # --- MOUSE INPUTS ---
    if key == 'left mouse down':
        if current_mode == 'build':
            # Place Structure
            cx, cy, cz = get_target_cell()
            if is_supported(cx, cy, cz):
                snap_rot = round(player.rotation_y / 90) * 90
                place_structure_local(cx, cy, cz, build_mode, snap_rot)
                try:
                    ws.send(json.dumps({'type': 'build', 'b_type': build_mode, 'cx': cx, 'cy': cy, 'cz': cz, 'rot_y': snap_rot}))
                except: pass
                
        elif current_mode == 'combat':
            # Shoot Weapon
            base_pos = Vec3(0, -0.2, 0.4) if is_aiming else Vec3(0.3, -0.3, 0.5)
            
            # Recoil
            active_gun.position = base_pos + Vec3(0, 0.05, -0.1)
            invoke(setattr, active_gun, 'position', base_pos, delay=0.1)

            hit_info = raycast(camera.world_position, camera.forward, distance=200, ignore=[player, preview_block, active_gun])
            
            # Tracer
            tracer_length = hit_info.distance if hit_info.hit else 200
            tracer = Entity(model='cube', color=color.rgba(255, 255, 100, 200), unlit=True, scale=(0.04, 0.04, tracer_length))
            tracer.position = active_gun.world_position
            tracer.look_at(hit_info.world_point if hit_info.hit else camera.world_position + (camera.forward * 200))
            tracer.position += tracer.forward * (tracer.scale_z / 2)
            tracer.animate_color(color.clear, duration=0.1) 
            destroy(tracer, delay=0.15) 

            if hit_info.hit:
                spawn_hit_particle(hit_info.world_point)
                if hasattr(hit_info.entity, 'pid'):
                    try:
                        ws.send(json.dumps({'type': 'damage', 'target_id': hit_info.entity.pid, 'amount': gun_entities[current_weapon]['dmg']}))
                    except: pass

    # --- ADS (Aim Down Sights) LOGIC ---
    if key == 'right mouse down':
        if current_mode == 'combat':
            is_aiming = True
            camera.fov = 70 # Zoom in
            active_gun.position = (0, -0.2, 0.4) # Center the gun

    if key == 'right mouse up':
        if current_mode == 'combat':
            is_aiming = False
            camera.fov = 90 # Revert zoom
            active_gun.position = (0.3, -0.3, 0.5) # Put gun back to hip

    if key == 'escape':
        application.quit()

app.run()
