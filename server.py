import asyncio
import websockets
import os
import json

# Store all connected players
connected_clients = set()

# --- NEW: The server's memory bank! ---
build_history = []

async def handle_client(websocket):
    # Register new player
    connected_clients.add(websocket)
    
    # --- NEW: Catch-up logic ---
    # The absolute split-second a new player joins, send them the entire world history
    for build_message in build_history:
        try:
            await websocket.send(build_message)
        except:
            pass

    try:
        # Listen for messages and broadcast them
        async for message in websocket:
            
            # --- NEW: Memory storage ---
            # If the message is a "build" command, permanently save it to history
            try:
                info = json.loads(message)
                if info.get('type') == 'build':
                    build_history.append(message)
            except:
                pass
            
            # Broadcast the message to everyone else in the lobby
            for client in connected_clients:
                if client != websocket:
                    try:
                        await client.send(message)
                    except:
                        pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Unregister player when they leave
        connected_clients.remove(websocket)

async def main():
    # Render assigns a port dynamically via environment variables
    port = int(os.environ.get("PORT", 5555))
    
    # Start the server
    async with websockets.serve(handle_client, "0.0.0.0", port):
        print(f"[SERVER] Running on port {port}")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
