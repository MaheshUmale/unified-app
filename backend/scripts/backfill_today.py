
import sys
import os
import asyncio
import logging

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.backfill_manager import BackfillManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

async def main():
    manager = BackfillManager()
    print("Starting manual backfill for today's session (TradingView + Trendlyne)...")
    result = await manager.backfill_today_session()

    print("\nBackfill Result:")
    print(f"Status: {result.get('status')}")
    print(f"Instruments Processed: {result.get('instruments_processed')}")
    print(f"Data Points Recovered: {result.get('data_points_recovered')}")
    if 'message' in result:
        print(f"Message: {result.get('message')}")

if __name__ == "__main__":
    asyncio.run(main())
