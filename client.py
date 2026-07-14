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

# Networking Variables
SERVER_URL = 'wss://fortnite-5xm3.onrender.com'
ws = None
my_id = str(uuid.uuid4())
other_players = {}

# Game State Variables
game_started = False
connecting = False
connected_successfully = False
connection_error = ""

# Game Objects
player = None
ground = None
gun = None

# ==========================================
# 2. NETWORKING LOGIC
# ==========================================
def receive_data():
    """Listens for updates from the server (other players moving/building)."""
    global ws
    while True:
        try:
            data = ws.recv()
            if not data:
                break
            
            info = json.loads(data)
            
            # Sync other players
            if info['type'] == 'player':
                pid = info['id']
                if pid not in other_players:
                    other_players[pid] = Entity(model='cube', color=color.magenta, scale=(0.8, 1.8, 0.8), collider='box')
                
                other_players[pid].position = (info['x'], info['y'], info['z'])
                other_players[pid].rotation_y = info['rot_y']
            
            # Sync building
            elif info['type'] == 'build':
                Entity(model='cube', texture='white_cube', color=color.cyan, position=(info['x'], info['y'], info['z']), collider='box')
                
        except Exception as e:
            print("Disconnected from server:", e)
            break

def try_connect_background():
    """Connects to Render in the background so the game doesn't freeze."""
    global ws, connected_successfully, connection_error, connecting
    try:
        ws = websocket.WebSocket()
        # 60 second timeout gives Render plenty of time to wake up from sleep
        ws.connect(SERVER_URL, timeout=60) 
        
        # Start listening for other players
        threading.Thread(target=receive_data, daemon=True).start()
        connected_successfully = True
    except Exception as e:
        connection_error = "Server offline. Check Render dashboard."
        connecting = False

def start_game():
    """Triggered by the PLAY button. Starts the background connection."""
    global connecting, connection_error
    if connecting: 
        return # Prevent clicking the button multiple times
    
    connecting = True
    connection_error = ""
    ui_status.text = "Waking up cloud server... (Can take 50 seconds!)"
    ui_status.color = color.yellow
    
    threading.Thread(target=try_connect_background, daemon=True).start()

# ==========================================
# 3. UI: DETAILED & THEMED LOBBY
# ==========================================
menu_parent = Entity(parent=camera.ui)

# Background Panels
bg_panel = Entity(parent=menu_parent, model='quad', scale=(2, 1), color=color.rgba(15, 15, 20, 255))
menu_box = Entity(parent=menu_parent, model='quad', scale=(0.6, 0.8), color=color.rgba(30, 30, 40, 200), y=0)

# Title Elements
Text(text="PROJECT:", parent=menu_parent, y=0.32, scale=1.5, origin=(0,0), color=color.light_gray)
Text(text="BUILD & BATTLE", parent=menu_parent, y=0.25, scale=3, origin=(0,0), color=color.cyan)

# Streamlined Play Button
play_btn = Button(text='PLAY ONLINE', parent=menu_parent, y=-0.05, scale=(0.4, 0.12), 
                  color=color.rgba(0, 150, 100, 255), highlight_color=color.rgba(0, 200, 150, 255))
play_btn.on_click = start_game

# Status Text (Errors/Connecting)
ui_status = Text(text="", parent=menu_parent, y=-0.25, origin=(0,0), color=color.white)

# Quit Button
quit_btn = Button(text='X', parent=menu_parent, position=(0.85, 0.45), scale=(0.05, 0.05), color=color.red, highlight_color=color.pink)
quit_btn.on_click = application.quit

# ==========================================
# 4. CORE GAME LOOP (Movement & Building)
# ==========================================
def update():
    global game_started, connecting, connected_successfully, ground, player, gun
    
    # 1. Handle UI updates from the background thread
    if connection_error != "":
        ui_status.text = connection_error
        ui_status.color = color.red
        
    # 2. Once connected, build the 3D world on the main thread
    if not game_started and connected_successfully:
        menu_parent.enabled = False
        mouse.locked = True
        
        Sky(texture='sky_sunset')
        ground = Entity(model='plane', scale=(100, 1, 100), color=color.rgba(50, 150, 50, 255), texture='white_cube', texture_scale=(100, 100), collider='box')
        
        player = FirstPersonController()
        player.y = 5
        
        gun = Entity(parent=camera, model='cube', color=color.dark_gray, scale=(0.1, 0.1, 0.4), position=(0.3, -0.3, 0.5), rotation=(0, -5, 0))
        
        game_started = True
        connected_successfully = False # Reset flag so we don't rebuild the world
        
    # 3. If in-game, broadcast position to server
    if game_started and ws and player:
        pos_data = {
            'type': 'player',
            'id': my_id,
            'x': player.x,
            'y': player.y,
            'z': player.z,
            'rot_y': player.rotation_y
        }
        try:
            ws.send(json.dumps(pos_data))
        except:
            pass

def input(key):
    if not game_started:
        return
        
    # BUILDING MECHANIC
    if key == 'left mouse down':
        # Simple gun recoil animation
        gun.position = (0.3, -0.28, 0.4)
        invoke(setattr, gun, 'position', (0.3, -0.3, 0.5), delay=0.1)

        # Raycast to place block
        hit_info = raycast(camera.world_position, camera.forward, distance=15)
        if hit_info.hit:
            build_pos = hit_info.entity.position + hit_info.normal
            
            # Place block locally
            Entity(model='cube', texture='white_cube', color=color.cyan, position=build_pos, collider='box')
            
            # Send build event to server
            build_data = {
                'type': 'build',
                'x': build_pos.x,
                'y': build_pos.y,
                'z': build_pos.z
            }
            try:
                ws.send(json.dumps(build_data))
            except:
                pass

    # Quit to desktop
    if key == 'escape':
        application.quit()

app.run()
