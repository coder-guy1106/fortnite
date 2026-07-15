import asyncio
import websockets
import os
import json

# ==========================================
# SERVER VERSION AUTHORITY
# Increment this when making major updates!
# ==========================================
SERVER_VERSION = "1.1.1"

connected_clients = set()
build_history = {} 

async def handle_client(websocket):
    try:
        first_message = await websocket.recv()
        info = json.loads(first_message)
        
        # STRICT VERSION CHECK
        if info.get('type') != 'join' or info.get('version') != SERVER_VERSION:
            error_packet = json.dumps({
                'type': 'error', 
                'message': f'Version Mismatch! Server is running v{SERVER_VERSION}. Please update your game.'
            })
            await websocket.send(error_packet)
            await websocket.close()
            return
            
        connected_clients.add(websocket)
        
        # Send map history to the new player
        for block_id, block_data in build_history.items():
            try:
                await websocket.send(block_data)
            except: 
                pass

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
        print(f"[SERVER] Running on port {port} | Version: {SERVER_VERSION}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
