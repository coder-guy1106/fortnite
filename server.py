import asyncio
import websockets
import os
import json

# --- SERVER VERSION ---
SERVER_VERSION = "1.2.0"

connected_clients = set()
build_history = {} 

async def handle_client(websocket):
    try:
        # Require a handshake packet first!
        init_msg = await asyncio.wait_for(websocket.recv(), timeout=5.0)
        init_data = json.loads(init_msg)
        
        if init_data.get('type') != 'join' or init_data.get('version') != SERVER_VERSION:
            await websocket.send(json.dumps({'type': 'error', 'message': f'Version mismatch! Server is on {SERVER_VERSION}'}))
            return # Drop the connection
            
    except:
        return # Drop if they fail the handshake

    connected_clients.add(websocket)
    
    # Send all existing blocks to the new player
    for block_id, block_data in build_history.items():
        try: await websocket.send(block_data)
        except: pass

    try:
        async for message in websocket:
            try:
                info = json.loads(message)
                if info.get('type') == 'build':
                    build_history[info['block_id']] = message
                elif info.get('type') == 'destroy_block':
                    if info['block_id'] in build_history:
                        del build_history[info['block_id']]
            except: pass
            
            for client in connected_clients:
                if client != websocket:
                    try: await client.send(message)
                    except: pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)

async def main():
    port = int(os.environ.get("PORT", 5555))
    async with websockets.serve(handle_client, "0.0.0.0", port):
        print(f"[SERVER] Running on port {port} | Version {SERVER_VERSION}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
