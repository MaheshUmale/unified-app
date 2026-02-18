import asyncio
from backend.core.options_manager import options_manager
from backend.db.local_db import db

async def test():
    # Setup some mock symbols in cache
    underlying = "NSE:NIFTY"
    options_manager.symbol_map_cache[underlying] = {
        "25000.0_call": "NIFTY25000CE",
        "25000.0_put": "NIFTY25000PE",
        "25100.0_call": "NIFTY25100CE",
        "25100.0_put": "NIFTY25100PE",
        "25200.0_call": "NIFTY25200CE",
        "25200.0_put": "NIFTY25200PE",
    }

    # Mock chain data
    chain = [
        {"strike": 25000.0, "option_type": "call"},
        {"strike": 25100.0, "option_type": "call"},
        {"strike": 25200.0, "option_type": "call"},
    ]

    # Mock get_chain_with_greeks
    options_manager.get_chain_with_greeks = lambda u: {"chain": chain}

    await options_manager._update_monitored_range(underlying, 25100)
    print(f"Monitored symbols: {options_manager.monitored_symbols.get(underlying)}")

if __name__ == "__main__":
    asyncio.run(test())
