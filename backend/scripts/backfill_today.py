
import os
import sys
import asyncio
import logging

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.backfill_manager import BackfillManager
import config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("BackfillScript")

async def run_backfill():
    if not config.ACCESS_TOKEN or config.ACCESS_TOKEN == 'YOUR_ACCESS_TOKEN_HERE':
        logger.error("UPSTOX_ACCESS_TOKEN not found in environment.")
        return

    manager = BackfillManager(config.ACCESS_TOKEN)
    result = await manager.backfill_today_session()

    if result.get("status") == "success":
        logger.info(f"Backfill successful! Recovered {result.get('data_points_recovered')} data points.")
    else:
        logger.error(f"Backfill failed: {result.get('message')}")

if __name__ == "__main__":
    asyncio.run(run_backfill())
