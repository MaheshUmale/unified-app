
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.strategy_builder import strategy_builder, StrategyType
from datetime import datetime, timedelta

def test_custom_strategy():
    print("Testing Custom Strategy Analysis...")

    underlying = "NSE:NIFTY"
    spot_price = 21500.0
    expiry = (datetime.now() + timedelta(days=7)).strftime('%Y-%m-%d')

    # Bull Call Spread as a custom strategy
    legs = [
        {
            'strike': 21500.0,
            'option_type': 'call',
            'position': 'long',
            'quantity': 1,
            'premium': 150.0,
            'expiry': expiry
        },
        {
            'strike': 21700.0,
            'option_type': 'call',
            'position': 'short',
            'quantity': 1,
            'premium': 60.0,
            'expiry': expiry
        }
    ]

    strategy = strategy_builder.create_strategy(
        "TestCustomBullCall",
        StrategyType.CUSTOM,
        underlying,
        spot_price,
        legs
    )

    analysis = strategy_builder.analyze_strategy("TestCustomBullCall")

    print(f"Strategy: {analysis['name']}")
    print(f"Net Premium: {analysis['net_premium']}")
    print(f"Max Profit: {analysis['max_profit']}")
    print(f"Max Loss: {analysis['max_loss']}")
    print(f"Breakevens: {analysis['breakeven_points']}")
    print(f"Net Delta: {analysis['net_delta']}")
    print(f"Net Gamma: {analysis['net_gamma']}")
    print(f"Net Theta: {analysis['net_theta']}")

    # Expected:
    # Net Premium: 90.0 (150 - 60)
    # Max Profit: 110.0 (200 - 90)
    # Max Loss: 90.0
    # Breakeven: 21590.0
    # Greeks: non-zero

    assert analysis['net_premium'] == 90.0
    assert analysis['max_profit'] == 110.0
    assert analysis['max_loss'] == 90.0
    assert 21590.0 in analysis['breakeven_points']
    assert analysis['net_delta'] != 0

    print("\nSUCCESS: Custom strategy analyzed correctly.")

if __name__ == "__main__":
    test_custom_strategy()
