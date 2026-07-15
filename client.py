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

# Fix VS Code pathing
os.chdir(os.path.dirname(os.path.abspath(__file__)))

app = Ursina()
window.title = 'Project: Build & Battle'
window.borderless = False
window.exit_button.visible = False

SERVER_URL = 'wss://fortnite-5xm3.onrender.com'
ws = None

# --- PLAYER IDENTITY ---
my_id = str(uuid.uuid4())
my_name = f"Player_{random.randint(1000, 9999)}"
my_color = (random.randint(50, 255), random.randint(50, 255), random.randint(50, 255))

other_players = {}
other_player_labels = {}
network_queue = [] 

game_started = False
connecting = False
connected_successfully = False
connection_error = ""

current_mode = 'combat' 
is_aiming = False       
is_reloading = False
is_dead = False # Death State

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
damage_overlay = None
hit_text_ui = None

# Death UI
death_screen = None
respawn_text = None

gun_entities = {}
active_gun = None

weapons = {
    0: {'name': 'Pickaxe', 'dmg': 20, 'bdmg': 50, 'color': color.gray, 'cooldown': 0.5, 'ammo': 999, 'max_ammo': 999, 'reload': 0, 'spread': 0},
    1: {'name': 'Assault Rifle', 'dmg': 15, 'bdmg': 15, 'color': color.dark_gray, 'cooldown': 0.15, 'ammo': 30, 'max_ammo': 30, 'reload': 1.5, 'spread': 0.02},
    2: {'name': 'Shotgun', 'dmg': 12, 'bdmg': 10, 'color': color.orange, 'cooldown': 1.0, 'ammo': 5, 'max_ammo': 5, 'reload': 2.5, 'spread': 0.1},
    3: {'name': 'Heavy Sniper', 'dmg': 90, 'bdmg': 150, 'color': color.green, 'cooldown': 2.0, 'ammo': 1, 'max_ammo': 1, 'reload': 3.0, 'spread': 0}
}
last_fired = 0

# --- NETWORKING ---
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

# --- UI LOBBY ---
menu_parent = Entity(parent=camera.ui)
Entity(parent=menu_parent, model='quad', scale=(2, 1), color=color.rgba(15, 15, 20, 255))
Text(text="BUILD & BATTLE", parent=menu_parent, y=0.3, scale=3, origin=(0,0), color=color.cyan)
Button(text='PLAY ONLINE', parent=menu_parent, y=-0.05, scale=(0.4, 0.12), color=color.rgba(0, 150, 100, 255)).on_click = start_game
ui_elements['status'] = Text(text="", parent=menu_parent, y=-0.25, origin=(0,0), color=color.white)

# --- WEAPONS ---
def build_weapons():
    # Pickaxe (Using a cube for the handle to prevent missing cylinder error)
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
    global active_gun, current_weapon, current_mode, is_reloading
    if is_reloading or is_dead: return
    if active_gun: active_gun.visible = False
    
    current_mode = 'combat'
    current_weapon = w_id
    active_gun = gun_entities[w_id]['entity']
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
    global is_reloading
    wep = weapons[current_weapon]
    if wep['ammo'] == wep['max_ammo'] or current_weapon == 0 or is_dead: return
    
    is_reloading = True
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

# --- BUILDING LOGIC ---
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

def destroy_block_local(cx, cy, cz):
    if (cx, cy, cz) in built_cells:
        destroy(built_cells[(cx, cy, cz)])
        del built_cells[(cx, cy, cz)]

# --- DEATH & RESPAWN ---
def handle_death():
    global is_dead, my_health
    is_dead = True
    my_health = 0
    ui_elements['health'].text = f"HP: {my_health}"
    
    player.disable() # Freezes player movement
    if active_gun: active_gun.visible = False
    if preview_block: preview_block.visible = False
    
    death_screen.visible = True
    camera.fov = 90
    
    def countdown(t):
        if t > 0:
            respawn_text.text = f"Respawning in {t}..."
            invoke(countdown, t-1, delay=1)
        else:
            respawn()
            
    countdown(3)

def respawn():
    global is_dead, my_health, is_reloading
    is_dead = False
    is_reloading = False
    my_health = 100
    ui_elements['health'].text = f"HP: {my_health}"
    
    player.position = (0, 20, 0) # Drop from sky
    player.enable()
    death_screen.visible = False
    
    # Reload all weapons on respawn
    for w in weapons.values():
        w['ammo'] = w['max_ammo']
    
    equip_weapon(1)

# --- GAME LOOP ---
def update():
    global game_started, connected_successfully, ground, player, preview_block, my_health, damage_overlay, hit_text_ui
    global death_screen, respawn_text
    
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
        ui_elements['wep'] = Text(text="", position=(0.3, -0.4), scale=1.5, color=color.white)
        
        # Hit effects UI
        damage_overlay = Entity(parent=camera.ui, model='quad', color=color.rgba(255, 0, 0, 0), scale=(2, 1), z=-1)
        hit_text_ui = Text(parent=camera.ui, text="", color=color.red, scale=3, origin=(0,0), y=0.1)
        
        # Death Screen UI
        death_screen = Entity(parent=camera.ui, model='quad', color=color.rgba(0, 0, 0, 220), scale=(2, 1), z=-2, visible=False)
        Text(parent=death_screen, text="YOU WERE ELIMINATED", scale=3, origin=(0,0), y=0.1, color=color.red)
        respawn_text = Text(parent=death_screen, text="Respawning in 3...", scale=2, origin=(0,0), y=-0.1, color=color.white)
        
        build_weapons()
        equip_weapon(1)
        
        preview_block = Entity(model='cube', color=color.rgba(0, 0, 255, 100), unlit=True, collider=None, visible=False)
        
        game_started = True
        connected_successfully = False 
        
    if game_started and ws and player:
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
            
            if info['type'] == 'player':
                pid = info['id']
                if pid not in other_players:
                    c = info.get('color', (255, 0, 255))
                    c_obj = color.rgb(c[0], c[1], c[2])
                    
                    other_players[pid] = Entity(model='cube', color=c_obj, scale=(1.2, 2.5, 1.2), collider='box')
                    other_players[pid].pid = pid 
                    
                    # Billboard Nameplate
                    p_name = info.get('name', 'Unknown')
                    other_player_labels[pid] = Text(parent=other_players[pid], text=p_name, y=0.6, scale=5, billboard=True, origin=(0,0), color=c_obj)
                    
                other_players[pid].position = (info['x'], info['y'], info['z'])
                other_players[pid].rotation_y = info['rot_y']
            
            elif info['type'] == 'build':
                b_id = info.get('block_id', str(uuid.uuid4())) # Fallback for old packets
                place_structure_local(info['cx'], info['cy'], info['cz'], info['b_type'], info['rot_y'], b_id)
                
            elif info['type'] == 'destroy_block':
                destroy_block_local(info['cx'], info['cy'], info['cz'])
                
            elif info['type'] == 'damage' and info['target_id'] == my_id and not is_dead:
                my_health -= info['amount']
                ui_elements['health'].text = f"HP: {my_health}"
                
                # Intense Hit Feedback
                damage_overlay.color = color.rgba(255, 0, 0, 180)
                damage_overlay.animate_color(color.rgba(255, 0, 0, 0), duration=0.4)
                
                hit_text_ui.text = f"-{info['amount']} HP"
                hit_text_ui.color = color.rgba(255, 50, 50, 255)
                hit_text_ui.animate_color(color.clear, duration=0.6)
                
                if my_health <= 0:
                    handle_death()

        try:
            if not is_dead:
                ws.send(json.dumps({
                    'type': 'player', 'id': my_id, 'x': player.x, 'y': player.y, 'z': player.z, 'rot_y': player.rotation_y,
                    'color': my_color, 'name': my_name
                }))
        except: pass

def input(key):
    global build_mode, current_mode, is_aiming, last_fired
    if not game_started or is_reloading or is_dead: return

    if key in ['0', '1', '2', '3']:
        equip_weapon(int(key)) 

    if key in ['z', 'x', 'c']:
        current_mode = 'build'
        active_gun.visible = False
        preview_block.visible = True
        
        if key == 'z': build_mode = 'wall'
        if key == 'x': build_mode = 'floor'
        if key == 'c': build_mode = 'ramp'
        
        camera.fov = 90
        is_aiming = False
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
            active_gun.position = base_pos + Vec3(0, 0.05, -0.1)
            invoke(setattr, active_gun, 'position', base_pos, delay=0.1)

            pellets = 5 if current_weapon == 2 else 1
            
            for _ in range(pellets):
                shoot_dir = camera.forward + Vec3(random.uniform(-wep['spread'], wep['spread']), random.uniform(-wep['spread'], wep['spread']), 0)
                hit_info = raycast(camera.world_position, shoot_dir, distance=200, ignore=[player, preview_block, active_gun])
                
                if current_weapon != 0: 
                    tracer_len = hit_info.distance if hit_info.hit else 200
                    tracer = Entity(model='cube', color=color.rgba(255, 255, 100, 200), unlit=True, scale=(0.04, 0.04, tracer_len))
                    tracer.position = active_gun.world_position
                    tracer.look_at(hit_info.world_point if hit_info.hit else camera.world_position + (shoot_dir * 200))
                    tracer.position += tracer.forward * (tracer.scale_z / 2)
                    tracer.animate_color(color.clear, duration=0.1) 
                    destroy(tracer, delay=0.15) 

                if hit_info.hit:
                    spawn_hit_particle(hit_info.world_point)
                    
                    if hasattr(hit_info.entity, 'pid'):
                        try: ws.send(json.dumps({'type': 'damage', 'target_id': hit_info.entity.pid, 'amount': wep['dmg']}))
                        except: pass
                    
                    elif hasattr(hit_info.entity, 'block_id'):
                        hit_info.entity.hp -= wep['bdmg']
                        hit_info.entity.color = color.red 
                        invoke(setattr, hit_info.entity, 'color', color.cyan, delay=0.1)
                        
                        if hit_info.entity.hp <= 0:
                            cx, cy, cz = hit_info.entity.cx, hit_info.entity.cy, hit_info.entity.cz
                            b_id = hit_info.entity.block_id
                            destroy_block_local(cx, cy, cz)
                            try: ws.send(json.dumps({'type': 'destroy_block', 'block_id': b_id, 'cx': cx, 'cy': cy, 'cz': cz}))
                            except: pass

    if key == 'right mouse down' and current_mode == 'combat':
        is_aiming = True
        camera.fov = 20 if current_weapon == 3 else 60 
        active_gun.position = Vec3(0, -0.2, 0.4) 

    if key == 'right mouse up' and current_mode == 'combat':
        is_aiming = False
        camera.fov = 90 
        active_gun.position = Vec3(0.3, -0.3, 0.5) 

    if key == 'escape':
        application.quit()

app.run()
