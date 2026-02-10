import asyncio
import logging
from core.options_manager import options_manager
from db.local_db import db

async def manual_snapshot():
    logging.basicConfig(level=logging.INFO)
    await options_manager.take_snapshot("NSE:NIFTY")
    res = db.query("SELECT * FROM pcr_history ORDER BY timestamp DESC LIMIT 1", json_serialize=True)
    import json
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    asyncio.run(manual_snapshot())
