import asyncio
import websockets
import os
import json

# --- SERVER VERSION CONTROL ---
REQUIRED_VERSION = "1.0.0"

connected_clients = set()
build_history = {} 

async def handle_client(websocket):
    try:
        # 1. The Handshake: Wait for the client to declare their version
        first_message = await websocket.recv()
        info = json.loads(first_message)
        
        # Check if they sent a valid join packet with the correct version
        if info.get('type') != 'join' or info.get('version') != REQUIRED_VERSION:
            # Kick them by sending an error and closing the door
            error_packet = json.dumps({'type': 'error', 'message': f'Version Mismatch! Server requires v{REQUIRED_VERSION}'})
            await websocket.send(error_packet)
            await websocket.close()
            return
            
        # 2. If they pass the check, register them and send the map history
        connected_clients.add(websocket)
        for block_id, block_data in build_history.items():
            try:
                await websocket.send(block_data)
            except: 
                pass

        # 3. Continuous Loop: Listen for standard game messages
        async for message in websocket:
            try:
                info = json.loads(message)
                if info.get('type') == 'build':
                    build_history[info['block_id']] = message
                elif info.get('type') == 'destroy_block':
                    if info['block_id'] in build_history:
                        del build_history[info['block_id']]
            except: pass
            
            # Broadcast to everyone else
            for client in connected_clients:
                if client != websocket:
                    try:
                        await client.send(message)
                    except: pass
                    
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)

async def main():
    port = int(os.environ.get("PORT", 5555))
    async with websockets.serve(handle_client, "0.0.0.0", port):
        print(f"[SERVER] Running on port {port} | Version: {REQUIRED_VERSION}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
