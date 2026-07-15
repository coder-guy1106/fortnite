import asyncio
import websockets
import os
import json

connected_clients = set()
build_history = {} # Changed from a list to a dictionary to track block IDs!

async def handle_client(websocket):
    connected_clients.add(websocket)
    
    # Send all existing blocks to the new player
    for block_id, block_data in build_history.items():
        try:
            await websocket.send(block_data)
        except: pass

    try:
        async for message in websocket:
            try:
                info = json.loads(message)
                # Store new builds
                if info.get('type') == 'build':
                    build_history[info['block_id']] = message
                # Delete destroyed builds from memory
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
        connected_clients.remove(websocket)

async def main():
    port = int(os.environ.get("PORT", 5555))
    async with websockets.serve(handle_client, "0.0.0.0", port):
        print(f"[SERVER] Running on port {port}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
