
import asyncio
import socketio
import time

async def verify_btc_feed():
    sio = socketio.AsyncClient()

    received_ticks = []

    @sio.on('raw_tick')
    def on_raw_tick(data):
        print(f"Received tick: {data}")
        received_ticks.append(data)

    @sio.on('connect')
    async def on_connect():
        print("Connected to server")
        # Subscribing to Coinbase:BTCUSD
        await sio.emit('subscribe', {'instrumentKeys': ['Coinbase:BTCUSD']})
        print("Subscribed to Coinbase:BTCUSD")

    try:
        await sio.connect('http://localhost:3000')
        # Wait for some ticks
        for _ in range(30):
            if received_ticks:
                print("SUCCESS: Received live ticks for BTCUSD")
                break
            await asyncio.sleep(1)
        else:
            print("FAILURE: Did not receive live ticks for BTCUSD within 30 seconds")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await sio.disconnect()

if __name__ == "__main__":
    asyncio.run(verify_btc_feed())
