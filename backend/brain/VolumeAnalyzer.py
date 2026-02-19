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
            'lines': []      # list of price line objects {price, color, width}
        }
        """
        if len(candles) < 20:
            return {'rvol': [1.0] * len(candles), 'markers': [], 'lines': []}

        df = pd.DataFrame(candles, columns=['ts', 'o', 'h', 'l', 'c', 'v'])

        # 1. RVOL Calculation (for coloring)
        df['v_sma20'] = df['v'].rolling(window=self.rvol_len).mean()
        df['rvol'] = df['v'] / df['v_sma20'].replace(0, 1)

        # 2. Bubble Calculation (for dots)
        df['v_sma100'] = df['v'].rolling(window=self.bubble_long_len).mean()
        df['v_sma10'] = df['v'].rolling(window=self.bubble_short_len).mean()
        df['v_avg_bubble'] = (df['v_sma100'] + df['v_sma10']) / 2
        df['bubble_ratio'] = df['v'] / df['v_avg_bubble'].replace(0, 1)

        # 3. Normalized Volume (for High Volume Nodes/Lines)
        df['v_sma48'] = df['v'].rolling(window=self.node_std_len).mean()
        df['v_std48'] = df['v'].rolling(window=self.node_std_len).std()
        df['v_norm'] = (df['v'] - df['v_sma48']) / df['v_std48'].replace(0, 1)

        markers = []
        lines = []

        # Determine markers (Bubbles)
        for i in range(len(df)):
            row = df.iloc[i]
            ratio = row['bubble_ratio']

            if ratio > self.BUBBLE_THRESHOLD:
                # Determine size category
                size = "tiny"
                if ratio > self.BUBBLE_THRESHOLD + 8 * self.BUBBLE_DELTA: size = "huge"
                elif ratio > self.BUBBLE_THRESHOLD + 4 * self.BUBBLE_DELTA: size = "large"
                elif ratio > self.BUBBLE_THRESHOLD + 2 * self.BUBBLE_DELTA: size = "normal"
                elif ratio > self.BUBBLE_THRESHOLD + self.BUBBLE_DELTA: size = "small"

                is_up = row['c'] > row['o']
                color = "rgba(34, 197, 94, 0.5)" if is_up else "rgba(239, 68, 68, 0.5)"

                markers.append({
                    "time": int(row['ts']),
                    "position": "belowBar" if is_up else "aboveBar",
                    "color": color,
                    "shape": "circle",
                    "text": f"V:{ratio:.1f}x",
                    "id": f"bubble_{i}"
                })

            # Determine High Volume Nodes (Lines)
            v_norm = row['v_norm']
            step = (v_norm - self.BUBBLE_THRESHOLD) / self.BUBBLE_DELTA
            if step >= 4:
                # High Volume Node Detected
                price = row['h'] if row['c'] < row['o'] else row['l']
                # Base colors from Pine Script
                # baseCOLOR = v_doji ? color.gray : v_top ? color.green : v_bot ? #d32626 : v_up ? color.aqua : color.orange
                # Simplified coloring for now: aqua for up, orange for down
                color = "#00ffff" if row['c'] > row['o'] else "#ffa500"
                width = 4 if step >= 8 else 3 if step >= 6 else 2

                lines.append({
                    "price": float(price),
                    "color": color,
                    "width": width,
                    "time": int(row['ts'])
                })

        # 4. EVWMA Calculation
        evma_len = 5
        df['shares_sum'] = df['v'].rolling(window=evma_len).sum()
        evma = [0.0] * len(df)
        for i in range(1, len(df)):
            shares = df['shares_sum'].iloc[i]
            vol = df['v'].iloc[i]
            price = df['c'].iloc[i]
            if shares > 0:
                evma[i] = (evma[i-1] * (shares - vol) / shares) + (vol * price / shares)
            else:
                evma[i] = evma[i-1] if i > 0 else price
        df['evwma'] = evma

        # 5. Dynamic Pivot Calculation
        # Simplified version of the complex Pine Script logic
        force_len = 20
        pivot_len = 10
        df['pC'] = df['c'] - df['o']
        df['mB'] = df['pC'].abs().rolling(window=force_len).max()
        df['sc'] = df['pC'].abs() / df['mB'].replace(0, 1)
        # Assuming no VWAP for now or use simplified
        df['netF'] = (df['pC'] * df['v'] * df['sc']).rolling(window=force_len).mean()
        df['baseP'] = df.apply(lambda r: r['h'] if r['pC'] > 0 else r['l'], axis=1).rolling(window=pivot_len).mean()
        df['fS'] = (df['c'].diff().abs() / df['c']).rolling(window=pivot_len).mean()
        df['hN'] = df['netF'].abs().rolling(window=pivot_len).max()
        df['fA'] = df['netF'] / df['hN'].replace(0, 1)
        df['dynP'] = df['baseP'] + (df['fA'] * df['c'] * df['fS'].fillna(0))

        return {
            'rvol': df['rvol'].fillna(1.0).tolist(),
            'markers': markers,
            'lines': lines,
            'evwma': [{"time": int(ts), "value": float(v)} for ts, v in zip(df['ts'], df['evwma'])],
            'dyn_pivot': [{"time": int(ts), "value": float(v)} for ts, v in zip(df['ts'], df['dynP'])]
        }
