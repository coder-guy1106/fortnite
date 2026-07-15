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

my_health = 100
current_weapon = 1 
build_mode = 'wall'
GRID_SIZE = 4 

built_cells = set() # Structural Memory

player = None
ground = None
gun_model = None
preview_block = None
ui_elements = {}

weapons = {
    1: {'name': 'AR', 'dmg': 15, 'color': color.dark_gray},
    2: {'name': 'Shotgun', 'dmg': 40, 'color': color.orange},
    3: {'name': 'Sniper', 'dmg': 90, 'color': color.green}
}

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
# 4. SMART BUILDING LOGIC
# ==========================================
def get_target_cell():
    """Finds the best grid cell based on where you are looking."""
    # Ignore the player and the preview block so they don't mess up the raycast
    hit_info = raycast(camera.world_position, camera.forward, distance=12, ignore=[player, preview_block])
    
    if hit_info.hit:
        # Snap to the face of the block we are looking at
        target_pos = hit_info.world_point + (hit_info.normal * 0.1)
    else:
        # Look 1 grid space ahead if aiming at the sky
        target_pos = camera.world_position + (camera.forward * GRID_SIZE)
        
    cx = round(target_pos.x / GRID_SIZE)
    # math.floor ensures we don't accidentally snap to the ceiling when standing on a ramp
    cy = max(0, math.floor(target_pos.y / GRID_SIZE))
    cz = round(target_pos.z / GRID_SIZE)
    
    return cx, cy, cz

def is_supported(cx, cy, cz):
    """Checks if a block is touching the ground OR any adjacent block (including diagonals)."""
    if cy == 0: return True 
    
    # Check a 3x3x3 grid around the target cell
    for dx in [-1, 0, 1]:
        for dy in [-1, 0, 1]:
            for dz in [-1, 0, 1]:
                if dx == 0 and dy == 0 and dz == 0: continue
                if (cx+dx, cy+dy, cz+dz) in built_cells:
                    return True
    return False

def get_world_pos_and_rot(cx, cy, cz, b_type, player_rot_y):
    """Converts grid coordinates into world coordinates with Edge-Snapping & Height Fixing."""
    x = cx * GRID_SIZE
    y = cy * GRID_SIZE
    z = cz * GRID_SIZE
    
    rot_y = round(player_rot_y / 90) * 90 % 360
    
    # Push walls and ramps UP by half their height so they sit ON the floor
    base_y = y + (GRID_SIZE / 2)
    
    if b_type == 'floor':
        # Floors sit flat at the bottom of the cell
        return Vec3(x, y + 0.1, z), 0, (GRID_SIZE, 0.2, GRID_SIZE)
    
    elif b_type == 'ramp':
        return Vec3(x, base_y, z), rot_y, (GRID_SIZE, 0.2, GRID_SIZE * 1.414) 
    
    elif b_type == 'wall':
        # EDGE SNAPPING
        if rot_y == 0:   z += GRID_SIZE/2
        elif rot_y == 90:  x += GRID_SIZE/2
        elif rot_y == 180: z -= GRID_SIZE/2
        elif rot_y == 270: x -= GRID_SIZE/2
        return Vec3(x, base_y, z), rot_y, (GRID_SIZE, GRID_SIZE, 0.2)

def place_structure_local(cx, cy, cz, b_type, rot_y):
    """Spawns the final built structure and adds it to memory."""
    pos, final_rot, scale = get_world_pos_and_rot(cx, cy, cz, b_type, rot_y)
    
    Entity(model='cube', texture='white_cube', color=color.cyan, position=pos, rotation=(0 if b_type!='ramp' else -45, final_rot, 0), scale=scale, collider='box')
    built_cells.add((cx, cy, cz))

# ==========================================
# 5. GAME LOOP
# ==========================================
def update():
    global game_started, connected_successfully, ground, player, gun_model, preview_block, my_health
    
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
        ui_elements['wep'] = Text(text="[1] AR | Build: Q,E,R", position=(0.4, -0.4), scale=1.5, color=color.white)
        
        gun_model = Entity(parent=camera, model='cube', color=weapons[1]['color'], scale=(0.1, 0.1, 0.6), position=(0.3, -0.3, 0.5))
        
        preview_block = Entity(model='cube', color=color.rgba(0, 0, 255, 100), unlit=True, collider=None)
        
        game_started = True
        connected_successfully = False 
        
    if game_started and ws and player:
        # --- HOLOGRAM LOGIC ---
        cx, cy, cz = get_target_cell()
        
        if is_supported(cx, cy, cz):
            preview_block.color = color.rgba(0, 200, 255, 120)
        else:
            preview_block.color = color.rgba(255, 0, 0, 120)
            
        pos, rot, scale = get_world_pos_and_rot(cx, cy, cz, build_mode, player.rotation_y)
        preview_block.position = pos
        preview_block.rotation = (0 if build_mode!='ramp' else -45, rot, 0)
        preview_block.scale = scale
        # ----------------------

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
    global current_weapon, build_mode
    if not game_started: return

    if key in ['1', '2', '3']:
        current_weapon = int(key)
        gun_model.color = weapons[current_weapon]['color']
        ui_elements['wep'].text = f"[{key}] {weapons[current_weapon]['name']} | Build: Q,E,R"

    if key == 'q': build_mode = 'wall'
    if key == 'e': build_mode = 'floor'
    if key == 'r': build_mode = 'ramp'

    if key == 'right mouse down':
        cx, cy, cz = get_target_cell()
        
        if is_supported(cx, cy, cz):
            snap_rot = round(player.rotation_y / 90) * 90
            place_structure_local(cx, cy, cz, build_mode, snap_rot)
            try:
                ws.send(json.dumps({'type': 'build', 'b_type': build_mode, 'cx': cx, 'cy': cy, 'cz': cz, 'rot_y': snap_rot}))
            except: pass

    if key == 'left mouse down':
        gun_model.position = (0.3, -0.25, 0.4)
        invoke(setattr, gun_model, 'position', (0.3, -0.3, 0.5), delay=0.1)

        hit_info = raycast(camera.world_position, camera.forward, distance=150, ignore=[player, preview_block])
        
        tracer_length = hit_info.distance if hit_info.hit else 150
        tracer = Entity(model='cube', color=color.yellow, unlit=True, scale=(0.05, 0.05, tracer_length))
        tracer.position = gun_model.world_position
        tracer.look_at(hit_info.world_point if hit_info.hit else camera.world_position + (camera.forward * 150))
        tracer.position += tracer.forward * (tracer.scale_z / 2)
        destroy(tracer, delay=0.05) 

        if hit_info.hit and hasattr(hit_info.entity, 'pid'):
            try:
                ws.send(json.dumps({'type': 'damage', 'target_id': hit_info.entity.pid, 'amount': weapons[current_weapon]['dmg']}))
            except: pass

    if key == 'escape':
        application.quit()

app.run()
