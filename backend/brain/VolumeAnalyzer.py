import numpy as np
import pandas as pd
from datetime import datetime

class VolumeAnalyzer:
    def __init__(self, rvol_len=20, bubble_long_len=100, bubble_short_len=10, node_std_len=48):
        self.rvol_len = rvol_len
        self.bubble_long_len = bubble_long_len
        self.bubble_short_len = bubble_short_len
        self.node_std_len = node_std_len

        # Thresholds from Pine Script
        self.BUBBLE_THRESHOLD = 2.5
        self.BUBBLE_DELTA = 0.75

    def analyze(self, candles):
        """
        candles: list of [ts, o, h, l, c, v]
        Returns: {
            'rvol': [float], # same length as candles
            'markers': [],   # list of marker objects
            'lines': [],      # High Volume Nodes
            'volume_rays': [] # NEW: Requested Ray Levels
        }
        """
        if len(candles) < 20:
            return {'rvol': [1.0] * len(candles), 'markers': [], 'lines': [], 'volume_rays': []}

        df = pd.DataFrame(candles, columns=['ts', 'o', 'h', 'l', 'c', 'v'])

        # 1. RVOL Calculation
        df['v_sma20'] = df['v'].rolling(window=self.rvol_len).mean()
        df['rvol'] = df['v'] / df['v_sma20'].replace(0, 1)

        # 2. Bubble & Ray Calculation
        df['v_sma100'] = df['v'].rolling(window=self.bubble_long_len).mean()
        df['v_sma10'] = df['v'].rolling(window=self.bubble_short_len).mean()
        df['v_avg_bubble'] = (df['v_sma100'] + df['v_sma10']) / 2
        df['bubble_ratio'] = df['v'] / df['v_avg_bubble'].replace(0, 1)

        # 3. Normalized Volume (for High Volume Nodes)
        df['bubble_ratio'] = df['bubble_ratio'].fillna(0.0)
        df['v_sma48'] = df['v'].rolling(window=self.node_std_len).mean()
        df['v_std48'] = df['v'].rolling(window=self.node_std_len).std()
        df['v_norm'] = (df['v'] - df['v_sma48']) / df['v_std48'].replace(0, 1)

        markers = []
        lines = []
        volume_rays = []

        # Wick calculation helper
        # upper_wick = high - max(open, close)
        # lower_wick = min(open, close) - low

        for i in range(len(df)):
            row = df.iloc[i]
            ratio = row['bubble_ratio']
            rvol = row['rvol']

            # Identify high volume candle for Ray/Level logic
            # User mentioned "HIGH RVOL CANDLES" and "VOLUME BUBBLES are supposed to be starting point"
            if ratio > self.BUBBLE_THRESHOLD or rvol > 2.0:
                # Starting point logic
                o, h, l, c = row['o'], row['h'], row['l'], row['c']
                uw = h - max(o, c)
                lw = min(o, c) - l

                # if upper wick is longer than 1.5X lower wick then at "HIGH"
                # ELSE if lower wick is longer than 1.5X higher wick then "LOW"
                # else CLOSE
                if uw > 1.5 * lw:
                    start_price = h
                    level_type = "Resistance"
                elif lw > 1.5 * uw:
                    start_price = l
                    level_type = "Support"
                else:
                    start_price = c
                    level_type = "Pivot"

                is_up = c > o
                color = "rgba(34, 197, 94, 0.6)" if level_type == "Support" else "rgba(239, 68, 68, 0.6)" if level_type == "Resistance" else "rgba(59, 130, 246, 0.6)"

                volume_rays.append({
                    "price": float(start_price),
                    "color": color,
                    "width": 2,
                    "title": f"V-Level ({level_type})",
                    "time": int(row['ts'])
                })

                # Add bubble marker as well
                markers.append({
                    "time": int(row['ts']),
                    "position": "belowBar" if is_up else "aboveBar",
                    "color": "rgba(34, 197, 94, 0.3)" if is_up else "rgba(239, 68, 68, 0.3)",
                    "shape": "circle",
                    "text": f"V:{ratio:.1f}x",
                    "id": f"bubble_{i}"
                })

            # High Volume Nodes (Existing logic)
            v_norm = row['v_norm']
            step = (v_norm - self.BUBBLE_THRESHOLD) / self.BUBBLE_DELTA
            if step >= 4:
                price = h if c < o else l
                lines.append({
                    "price": float(price),
                    "color": "#00ffff" if c > o else "#ffa500",
                    "width": 2,
                    "time": int(row['ts'])
                })

        # Limit to last 50 rays as requested
        volume_rays = sorted(volume_rays, key=lambda x: x['time'])[-50:]

        # 4. EVWMA Calculation (Existing)
        evma_len = 5
        df['shares_sum'] = df['v'].rolling(window=evma_len).sum()
        evma = [np.nan] * len(df)
        for i in range(1, len(df)):
            shares = df['shares_sum'].iloc[i]
            vol = df['v'].iloc[i]
            price = df['c'].iloc[i]
            prev_val = evma[i-1] if i > 0 and not np.isnan(evma[i-1]) else price
            if shares > 0:
                evma[i] = (prev_val * (shares - vol) / shares) + (vol * price / shares)
            else:
                evma[i] = prev_val

        # 5. Dynamic Pivot Calculation (Existing)
        force_len = 20
        pivot_len = 10
        df['pC'] = df['c'] - df['o']
        df['mB'] = df['pC'].abs().rolling(window=force_len).max()
        df['sc'] = df['pC'].abs() / df['mB'].replace(0, 1)
        df['netF'] = (df['pC'] * df['v'] * df['sc']).rolling(window=force_len).mean()
        df['baseP'] = df.apply(lambda r: r['h'] if r['pC'] > 0 else r['l'], axis=1).rolling(window=pivot_len).mean()
        df['fS'] = (df['c'].diff().abs() / df['c']).rolling(window=pivot_len).mean()
        df['hN'] = df['netF'].abs().rolling(window=pivot_len).max()
        df['fA'] = df['netF'] / df['hN'].replace(0, 1)
        df['dynP'] = df['baseP'] + (df['fA'] * df['c'] * df['fS'].fillna(0))

        return {
            'rvol': [float(v) if np.isfinite(v) else 1.0 for v in df['rvol'].fillna(1.0)],
            'markers': markers,
            'lines': lines,
            'volume_rays': volume_rays,
            'evwma': [{"time": int(ts), "value": float(v)} for ts, v in zip(df['ts'], evma) if np.isfinite(v) and v > 0],
            'dyn_pivot': [{"time": int(ts), "value": float(v)} for ts, v in zip(df['ts'], df['dynP']) if np.isfinite(v) and v > 0]
        }
