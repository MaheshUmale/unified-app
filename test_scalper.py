
import sys
import os
import asyncio

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

async def test_scalper_init():
    print("Testing Scalper Initialization...")
    try:
        from brain.nse_confluence_scalper import scalper
        print("Scalper imported successfully.")

        print(f"Scalper Underlying: {scalper.underlying}")
        print(f"Scalper Is Running: {scalper.is_running}")

        # Test level detection skeleton
        import pandas as pd
        df = pd.DataFrame({
            'h': [100, 101, 102, 101, 100, 101, 103, 101, 100] * 5,
            'l': [99, 100, 101, 100, 99, 100, 102, 100, 99] * 5,
            'c': [99.5, 100.5, 101.5, 100.5, 99.5, 100.5, 102.5, 100.5, 99.5] * 5
        })
        levels = scalper.engine.find_levels(df)
        print(f"Detected levels: {levels}")

        print("Scalper basic logic test PASSED.")
    except Exception as e:
        print(f"Scalper logic test FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_scalper_init())
