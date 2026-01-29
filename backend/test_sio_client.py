import socketio
import asyncio
import sys

async def test_connect():
    sio = socketio.AsyncClient()
    url = 'http://localhost:5051'
    print(f"Attempting to connect to {url}")
    try:
        await sio.connect(url, transports=['polling'])
        print("Successfully connected via polling!")
        await sio.disconnect()
    except Exception as e:
        print(f"Connection failed: {e}")
        # Print more details if possible
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    # Start the server in background if not running
    # (Assuming it's already being started in a real environment,
    # but here I'll just run the test against the one I might have started)
    asyncio.run(test_connect())
