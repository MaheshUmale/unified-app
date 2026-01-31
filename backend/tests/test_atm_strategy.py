
import pytest
from core.strategies.atm_buying_strategy import ATMOptionBuyingStrategy

def test_atm_strategy_logic():
    strategy = ATMOptionBuyingStrategy()

    # Mock data
    market_data = {
        "spot_price": 25000,
        "india_vix": 15,
        "atm_strike": 25000,
        "atm_ce": {
            "price": 100,
            "iv": 16,
            "iv_15m_ago": 15,
            "theta": -20,
            "gamma": 0.002,
            "oi": 1000000,
            "oi_15m_ago": 900000,
            "spread": 0.05,
            "open_spread": 0.1,
            "vol_spike": True
        },
        "atm_pe": {
            "price": 95,
            "iv": 16,
            "iv_15m_ago": 15,
            "theta": -20,
            "gamma": 0.002,
            "oi": 1000000,
            "oi_15m_ago": 900000,
            "spread": 0.05,
            "open_spread": 0.1,
            "vol_spike": True
        }
    }

    # We need to mock get_nifty_adv and get_5day_median_gamma
    # For now, just test if analyze runs without crashing and returns expected structure
    results = strategy.analyze("NIFTY", market_data)

    assert "decision" in results
    assert "edge_scores" in results
    assert "filters" in results
    assert "metrics" in results

    print(f"Decision: {results['decision']}")
    print(f"Edge Scores: {results['edge_scores']}")

if __name__ == "__main__":
    test_atm_strategy_logic()
