from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
import websocket
import threading
import json
import uuid

# ==========================================
# 1. GLOBAL SETUP & CONFIGURATION
# ==========================================
app = Ursina()
window.title = 'Project: Build & Battle (Online)'
window.borderless = False
window.fullscreen = False
window.exit_button.visible = False

SERVER_URL = 'wss://fortnite-5xm3.onrender.com'
ws = None
my_id = str(uuid.uuid4())
other_players = {}

# --- NEW: The bucket for incoming network messages ---
network_queue = [] 

game_started = False
connecting = False
connected_successfully = False
connection_error = ""

my_health = 100
current_weapon = 1 

player = None
ground = None
gun_model = None
health_bar = None
weapon_text = None

weapons = {
    1: {'name': 'Assault Rifle', 'dmg': 15, 'color': color.dark_gray, 'scale': (0.1, 0.1, 0.6)},
    2: {'name': 'Shotgun', 'dmg': 40, 'color': color.orange, 'scale': (0.15, 0.15, 0.4)},
    3: {'name': 'Sniper', 'dmg': 90, 'color': color.green, 'scale': (0.08, 0.12, 1.0)}
}

# ==========================================
# 2. NETWORKING LOGIC
# ==========================================
def receive_data():
    global ws
    while True:
        try:
            data = ws.recv()
            if not data: break
            
            # Toss the incoming message into the bucket! Do NOT draw graphics here.
            network_queue.append(json.loads(data))
                    
        except Exception as e:
            print("Disconnected:", e)
            break

def try_connect_background():
    global ws, connected_successfully, connection_error, connecting
    try:
        ws = websocket.WebSocket()
        ws.connect(SERVER_URL, timeout=60) 
        threading.Thread(target=receive_data, daemon=True).start()
        connected_successfully = True
    except Exception as e:
        connection_error = "Server offline."
        connecting = False

def start_game():
    global connecting, connection_error
    if connecting: return 
    
    connecting = True
    connection_error = ""
    ui_status.text = "Waking up cloud server..."
    ui_status.color = color.yellow
    
    threading.Thread(target=try_connect_background, daemon=True).start()

# ==========================================
# 3. UI LOBBY
# ==========================================
menu_parent = Entity(parent=camera.ui)
bg_panel = Entity(parent=menu_parent, model='quad', scale=(2, 1), color=color.rgba(15, 15, 20, 255))
menu_box = Entity(parent=menu_parent, model='quad', scale=(0.6, 0.8), color=color.rgba(30, 30, 40, 200), y=0)
Text(text="PROJECT:\nBUILD & BATTLE", parent=menu_parent, y=0.32, scale=2, origin=(0,0), color=color.cyan)

play_btn = Button(text='PLAY ONLINE', parent=menu_parent, y=-0.05, scale=(0.4, 0.12), color=color.rgba(0, 150, 100, 255))
play_btn.on_click = start_game

ui_status = Text(text="", parent=menu_parent, y=-0.25, origin=(0,0), color=color.white)
quit_btn = Button(text='X', parent=menu_parent, position=(0.85, 0.45), scale=(0.05, 0.05), color=color.red)
quit_btn.on_click = application.quit

# ==========================================
# 4. GAME LOOP & MECHANICS
# ==========================================
def update():
    global game_started, connected_successfully, ground, player, gun_model, health_bar, weapon_text, my_health
    
    if connection_error != "":
        ui_status.text = connection_error
        ui_status.color = color.red
        
    if not game_started and connected_successfully:
        menu_parent.enabled = False
        mouse.locked = True
        
        Sky(texture='sky_sunset')
        ground = Entity(model='plane', scale=(100, 1, 100), color=color.rgba(50, 150, 50, 255), texture='white_cube', texture_scale=(100, 100), collider='box')
        
        player = FirstPersonController()
        player.y = 5
        
        health_bar = Text(text=f"HEALTH: {my_health}", position=(-0.85, -0.4), scale=2, color=color.green)
        weapon_text = Text(text="[1] Assault Rifle", position=(0.5, -0.4), scale=2, color=color.white)
        
        gun_model = Entity(parent=camera, model='cube', color=weapons[1]['color'], scale=weapons[1]['scale'], position=(0.3, -0.3, 0.5))
        
        game_started = True
        connected_successfully = False 
        
    if game_started and ws and player:
        # 1. Safely process all network messages on the main thread
        while len(network_queue) > 0:
            info = network_queue.pop(0)
            
            if info['type'] == 'player':
                pid = info['id']
                if pid not in other_players:
                    other_players[pid] = Entity(model='cube', color=color.magenta, scale=(1.5, 3, 1.5), collider='box')
                    other_players[pid].pid = pid 
                
                other_players[pid].position = (info['x'], info['y'], info['z'])
                other_players[pid].rotation_y = info['rot_y']
            
            elif info['type'] == 'build':
                Entity(model='cube', texture='white_cube', color=color.cyan, position=(info['x'], info['y'], info['z']), collider='box')
            
            elif info['type'] == 'damage':
                if info['target_id'] == my_id:
                    my_health -= info['amount']
                    if my_health <= 0:
                        my_health = 100 
                        player.position = (0, 10, 0) # Respawn
                    health_bar.text = f"HEALTH: {my_health}"

        # 2. Send our position to the server
        try:
            ws.send(json.dumps({'type': 'player', 'id': my_id, 'x': player.x, 'y': player.y, 'z': player.z, 'rot_y': player.rotation_y}))
        except:
            pass

def input(key):
    global current_weapon
    if not game_started: return

    if key in ['1', '2', '3']:
        current_weapon = int(key)
        wep = weapons[current_weapon]
        gun_model.color = wep['color']
        gun_model.scale = wep['scale']
        weapon_text.text = f"[{key}] {wep['name']}"

    if key == 'right mouse down':
        hit_info = raycast(camera.world_position, camera.forward, distance=15)
        if hit_info.hit:
            build_pos = hit_info.entity.position + hit_info.normal
            Entity(model='cube', texture='white_cube', color=color.cyan, position=build_pos, collider='box')
            try:
                ws.send(json.dumps({'type': 'build', 'x': build_pos.x, 'y': build_pos.y, 'z': build_pos.z}))
            except: pass

    if key == 'left mouse down':
        gun_model.position = (0.3, -0.25, 0.4)
        invoke(setattr, gun_model, 'position', (0.3, -0.3, 0.5), delay=0.1)

        hit_info = raycast(camera.world_position, camera.forward, distance=100)
        if hit_info.hit:
            hit_entity = hit_info.entity
            if hasattr(hit_entity, 'pid'):
                dmg = weapons[current_weapon]['dmg']
                try:
                    ws.send(json.dumps({'type': 'damage', 'target_id': hit_entity.pid, 'amount': dmg}))
                except: pass

    if key == 'escape':
        application.quit()

app.run()
