import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../services")))

import pytest
import pandas as pd
from core.pcr_logic import calculate_total_pcr, analyze_oi_buildup, aggregate_option_chain_pcr

def test_calculate_total_pcr():
    assert calculate_total_pcr(100, 50) == 2.0
    assert calculate_total_pcr(50, 100) == 0.5
    assert calculate_total_pcr(100, 0) == 0.0
    assert calculate_total_pcr(0, 100) == 0.0

def test_analyze_oi_buildup():
    # Price Up, OI Up -> Long Buildup
    assert analyze_oi_buildup(105, 100, 1000, 900) == "Long Buildup"
    # Price Up, OI Down -> Short Covering
    assert analyze_oi_buildup(105, 100, 900, 1000) == "Short Covering"
    # Price Down, OI Up -> Short Buildup
    assert analyze_oi_buildup(95, 100, 1000, 900) == "Short Buildup"
    # Price Down, OI Down -> Long Unwinding
    assert analyze_oi_buildup(95, 100, 900, 1000) == "Long Unwinding"
    # No Change
    assert analyze_oi_buildup(100, 100, 1000, 1000) == "Neutral"

def test_aggregate_option_chain_pcr():
    data = {
        'pe_open_interest': [100, 200, 300],
        'ce_open_interest': [50, 150, 250]
    }
    df = pd.DataFrame(data)
    # Total Put OI = 600, Total Call OI = 450
    # PCR = 600 / 450 = 1.3333
    assert aggregate_option_chain_pcr(df) == 1.3333
