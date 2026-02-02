
import sys
import os
import asyncio
import logging

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.backfill_manager import BackfillManager
from config import ACCESS_TOKEN

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

async def main():
    if not ACCESS_TOKEN or ACCESS_TOKEN == 'YOUR_ACCESS_TOKEN_HERE':
        print("Error: UPSTOX_ACCESS_TOKEN not found in config/env.")
        return

    manager = BackfillManager(ACCESS_TOKEN)
    print("Starting manual backfill for today's session...")
    result = await manager.backfill_today_session()

    print("\nBackfill Result:")
    print(f"Status: {result.get('status')}")
    print(f"Instruments Processed: {result.get('instruments_processed')}")
    print(f"Data Points Recovered: {result.get('data_points_recovered')}")
    if 'message' in result:
        print(f"Message: {result.get('message')}")

if __name__ == "__main__":
    asyncio.run(main())
