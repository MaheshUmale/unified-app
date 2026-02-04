import tvkit
import asyncio
from tvkit.api.chart.ohlcv import OHLCV

async def stream_bitcoin():
    async with OHLCV() as client:
        # Stream real-time OHLCV data for Bitcoin
        count = 0
        async for bar in client.get_ohlcv("NSE:NIFTY", interval="1"):
            count += 1
            print(f"Bar {count}: NIFTY ${bar.close:,.2f} | Volume: {bar.volume:,.0f}")
            
            # Limit demo to 5 bars
            if count >= 50:
                break

asyncio.run(stream_bitcoin())