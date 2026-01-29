"""
PCR and OI Buildup Engine
Calculates Put-Call Ratio (PCR) and analyzes Open Interest (OI) buildup patterns to determine market sentiment.
"""
import pandas as pd
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def calculate_total_pcr(put_oi: float, call_oi: float) -> float:
    """
    Calculates the Put-Call Ratio (PCR).

    Args:
        put_oi (float): Total Open Interest of Put options.
        call_oi (float): Total Open Interest of Call options.

    Returns:
        float: The calculated PCR. Returns 0 if call_oi is 0.
    """
    if call_oi == 0:
        return 0.0
    return round(put_oi / call_oi, 4)

def analyze_oi_buildup(current_price: float, prev_price: float, current_oi: int, prev_oi: int) -> str:
    """
    Identifies the type of Open Interest buildup based on price and OI changes.

    Args:
        current_price (float): Current price of the instrument.
        prev_price (float): Previous price of the instrument.
        current_oi (int): Current Open Interest.
        prev_oi (int): Previous Open Interest.

    Returns:
        str: The sentiment label (e.g., "Long Buildup", "Short Covering").
    """
    price_change = current_price - prev_price
    oi_change = current_oi - prev_oi

    if price_change > 0 and oi_change > 0:
        return "Long Buildup"
    elif price_change > 0 and oi_change < 0:
        return "Short Covering"
    elif price_change < 0 and oi_change > 0:
        return "Short Buildup"
    elif price_change < 0 and oi_change < 0:
        return "Long Unwinding"
    else:
        return "Neutral"

def aggregate_option_chain_pcr(option_chain_df: pd.DataFrame) -> float:
    """
    Calculates the overall PCR for an entire option chain.
    Expects a DataFrame with 'pe_open_interest' and 'ce_open_interest' columns.
    """
    total_put_oi = option_chain_df['pe_open_interest'].sum()
    total_call_oi = option_chain_df['ce_open_interest'].sum()
    return calculate_total_pcr(total_put_oi, total_call_oi)
