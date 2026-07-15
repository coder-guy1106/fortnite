import asyncio
import websockets
import os
import json

connected_clients = set()

# The memory bank tracking unique block IDs so late-joiners can see the map
build_history = {} 

async def handle_client(websocket):
    connected_clients.add(websocket)
    
    # 1. Catch-Up: Send all existing, unbroken blocks to the new player instantly
    for block_id, block_data in build_history.items():
        try:
            await websocket.send(block_data)
        except: 
            pass

    try:
        # 2. Continuous Loop: Listen for incoming messages
        async for message in websocket:
            try:
                info = json.loads(message)
                
                # If it's a build command, permanently save it to memory
                if info.get('type') == 'build':
                    build_history[info['block_id']] = message
                    
                # If a block is destroyed, delete it from the server's memory
                elif info.get('type') == 'destroy_block':
                    if info['block_id'] in build_history:
                        del build_history[info['block_id']]
            except: 
                pass
            
            # 3. Broadcast: Send the packet (movement, shooting, building) to everyone else
            for client in connected_clients:
                if client != websocket:
                    try:
                        await client.send(message)
                    except: 
                        pass
                        
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.remove(websocket)

async def main():
    # Render assigns the port dynamically
    port = int(os.environ.get("PORT", 5555))
    
    async with websockets.serve(handle_client, "0.0.0.0", port):
        print(f"[SERVER] Running on port {port}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())
