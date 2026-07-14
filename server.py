import asyncio
import websockets
import os

# Store all connected players
connected_clients = set()

async def handle_client(websocket):
    # Register new player
    connected_clients.add(websocket)
    try:
        # Listen for messages and broadcast them to everyone else
        async for message in websocket:
            for client in connected_clients:
                if client != websocket:
                    await client.send(message)
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Unregister player when they disconnect
        connected_clients.remove(websocket)

async def main():
    # Render assigns a port dynamically via environment variables
    port = int(os.environ.get("PORT", 5555))
    
    # Start the server (0.0.0.0 allows external connections)
    async with websockets.serve(handle_client, "0.0.0.0", port):
        print(f"[SERVER] Running on port {port}")
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
