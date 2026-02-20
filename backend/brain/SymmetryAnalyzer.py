import pandas as pd
import numpy as np
from datetime import datetime
import logging
from core.utils import safe_int, safe_float

logger = logging.getLogger(__name__)

class SymmetryAnalyzer:
    """
    Implements Triple-Stream Symmetry & Panic Strategy.
    Monitors Index Spot, ATM Call, and ATM Put simultaneously.
    """
    def __init__(self, underlying="NSE:NIFTY"):
        self.underlying = underlying
        self.reference_levels = {'High': None, 'Low': None}
        self.swing_window = 15
        self.confluence_threshold = 3

    def identify_swing(self, subset_df):
        """
        Identify Significant Swings where a 'Wall' exists.
        Returns the data of the peak/trough candle.
        """
        if len(subset_df) < 3:
            return None

        # Simple swing detection: local high/low in the window
        last_n = subset_df.tail(self.swing_window)

        # We look for a peak that is NOT the very last candle (because we need a pullback)
        # Peak is at index -2
        last_candle = subset_df.iloc[-1]
        prev_candle = subset_df.iloc[-2]
        prev_prev = subset_df.iloc[-3]

        # Bullish Wall (High)
        if prev_candle['h_idx'] > prev_prev['h_idx'] and prev_candle['h_idx'] > last_candle['h_idx']:
            return {'type': 'High', 'data': prev_candle}

        # Bearish Wall (Low)
        if prev_candle['l_idx'] < prev_prev['l_idx'] and prev_candle['l_idx'] < last_candle['l_idx']:
            return {'type': 'Low', 'data': prev_candle}

        return None

    def check_decay_filter(self, current_index_price, current_ce_price, ref_level):
        """
        Phase II: The Pullback & Decay Filter (Anti-Theta)
        If Index returns to Ref_Price_Index but Current_Price_CE is higher than Ref_Price_CE
        """
        if not ref_level or ref_level['type'] != 'High':
            return False

        if current_index_price >= ref_level['index_price']:
            if current_ce_price > ref_level['ce_price']:
                return True # Bullish Divergence
        return False

    def analyze(self, idx_candles, ce_candles, pe_candles, oi_data=None):
        """
        Generate signals based on Triple-Symmetry.
        idx_candles, ce_candles, pe_candles: list of [ts, o, h, l, c, v]
        oi_data: dict {ts: {'ce_oi_chg':, 'pe_oi_chg':}}
        """
        if not idx_candles or not ce_candles or not pe_candles:
            return []

        # Convert to DataFrames
        idx_df = pd.DataFrame(idx_candles, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        ce_df = pd.DataFrame(ce_candles, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        pe_df = pd.DataFrame(pe_candles, columns=['ts', 'o', 'h', 'l', 'c', 'v'])

        # Align by timestamp
        combined = pd.merge(idx_df, ce_df, on='ts', suffixes=('_idx', '_ce'))
        combined = pd.merge(combined, pe_df, on='ts')
        combined.rename(columns={'o': 'o_pe', 'h': 'h_pe', 'l': 'l_pe', 'c': 'c_pe', 'v': 'v_pe'}, inplace=True)
        combined.sort_values('ts', inplace=True)

        signals = []
        # Keep track of signals to avoid duplicates at same timestamp
        seen_timestamps = set()

        for i in range(self.swing_window, len(combined)):
            subset = combined.iloc[:i+1] # Include current to see if previous was a peak
            current = combined.iloc[i]
            prev = combined.iloc[i-1]
            ts = int(current['ts'])

            # 1. Update Reference Levels
            swing = self.identify_swing(subset)
            if swing:
                l_type = swing['type']
                peak_data = swing['data']
                # Record prices of all three at the exact moment of peak
                self.reference_levels[l_type] = {
                    'index_price': float(peak_data['h_idx'] if l_type == 'High' else peak_data['l_idx']),
                    'ce_price': float(peak_data['c_ce']),
                    'pe_price': float(peak_data['c_pe']),
                    'type': l_type,
                    'time': int(peak_data['ts'])
                }
                logger.info(f"New Reference {l_type} set at {peak_data['ts']}: Index={self.reference_levels[l_type]['index_price']}")

            # 2. Check for Signals
            ref_high = self.reference_levels.get('High')
            ref_low = self.reference_levels.get('Low')

            # --- Bullish Trigger (Call Buy) ---
            if ref_high:
                score = 0
                details = {}

                # 1. Index: Crosses above Ref_High_Index
                if current['c_idx'] > ref_high['index_price']:
                    score += 1
                    details['index_break'] = True

                # 2. CE Symmetry: ATM Call breaks above Ref_High_CE
                if current['c_ce'] > ref_high['ce_price']:
                    score += 1
                    details['ce_break'] = True

                # 3. PE Symmetry: ATM Put breaks below its own local low at peak
                if current['c_pe'] < ref_high['pe_price']:
                    score += 1
                    details['pe_breakdown'] = True

                # 4. OI Panic (if available)
                if oi_data and ts in oi_data:
                    d = oi_data[ts]
                    if d.get('ce_oi_chg', 0) < 0 and d.get('pe_oi_chg', 0) > 0:
                        score += 1
                        details['oi_panic'] = True

                # 5. Decay Filter
                if self.check_decay_filter(current['c_idx'], current['c_ce'], ref_high):
                    score += 1
                    details['decay_divergence'] = True

                if score >= self.confluence_threshold and ts not in seen_timestamps:
                    # Guardrail: Absorption check (Index high but CE rejected)
                    if not (current['c_idx'] > prev['c_idx'] and current['c_ce'] <= prev['c_ce']):
                        signals.append({
                            'time': ts,
                            'type': 'BUY_CE',
                            'score': score,
                            'price': float(current['c_ce']),
                            'sl': float(ref_high['ce_price'] * 0.90), # 10% hard SL
                            'tp': float(current['c_ce'] + (current['c_ce'] - ref_high['ce_price']) * 2.5),
                            'details': details
                        })
                        seen_timestamps.add(ts)

            # --- Bearish Trigger (Put Buy) ---
            if ref_low:
                score = 0
                details = {}

                if current['c_idx'] < ref_low['index_price']:
                    score += 1
                    details['index_break'] = True

                if current['c_pe'] > ref_low['pe_price']:
                    score += 1
                    details['pe_break'] = True

                if current['c_ce'] < ref_low['ce_price']:
                    score += 1
                    details['ce_breakdown'] = True

                if score >= self.confluence_threshold and ts not in seen_timestamps:
                    signals.append({
                        'time': ts,
                        'type': 'BUY_PE',
                        'score': score,
                        'price': float(current['c_pe']),
                        'sl': float(ref_low['pe_price'] * 0.90),
                        'tp': float(current['c_pe'] + (current['c_pe'] - ref_low['pe_price']) * 2.5),
                        'details': details
                    })
                    seen_timestamps.add(ts)

        return signals
