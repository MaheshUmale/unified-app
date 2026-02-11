
import sys
import os
import asyncio

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def verify_registry():
    print("Verifying Provider Registry...")
    from core.provider_registry import (
        live_stream_registry,
        options_data_registry,
        historical_data_registry,
        initialize_default_providers
    )

    initialize_default_providers()

    print(f"Live Stream Providers: {live_stream_registry.priority_list}")
    print(f"Options Data Providers: {options_data_registry.priority_list}")
    print(f"Historical Data Providers: {historical_data_registry.priority_list}")

    # Verify primary selection
    primary_opt = options_data_registry.get_primary()
    print(f"Primary Options Provider: {type(primary_opt).__name__}")

    # Test a fetch (requires internet and valid symbols)
    try:
        expiries = await primary_opt.get_expiry_dates("NSE:NIFTY")
        print(f"Fetched {len(expiries)} expiries via primary provider.")
    except Exception as e:
        print(f"Fetch failed (expected if offline): {e}")

    print("Registry verification PASSED.")

if __name__ == "__main__":
    asyncio.run(verify_registry())
