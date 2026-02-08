import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from tvDatafeed import TvDatafeed, Interval
from mplfinance.original_flavor import candlestick_ohlc

class MarketPsychologyAnalyzer:
    def __init__(self, vol_lookback=20, atr_lookback=20):
        self.vol_lookback = vol_lookback
        self.atr_lookback = atr_lookback
        self.active_zones = [] 
        self.confirmed_signals = {} # {timestamp: signal_type}

    def _calculate_metrics(self, df):
        """Calculates indicators on the full dataset to ensure consistency [cite: 2026-01-28]."""
        df = df.copy()
        df['vol_sma'] = df['volume'].rolling(window=self.vol_lookback).mean()
        df['r_vol'] = df['volume'] / df['vol_sma']
        df['tr'] = np.maximum(df['high'] - df['low'], np.abs(df['high'] - df['close'].shift(1)))
        df['atr'] = df['tr'].rolling(window=self.atr_lookback).mean()
        df['eff'] = (df['tr'] / df['atr']) / df['r_vol'].replace(0, 1)
        df['ema'] = df['close'].ewm(span=50, adjust=False).mean()
        return df

    def build_global_map(self, df):
        """Identifies levels across the entire history so they don't move [cite: 2026-01-28]."""
        zones = []
        for i in range(self.vol_lookback, len(df) - 1):
            row = df.iloc[i]
            # Create a zone if we see massive absorption (High volume, low price progress)
            if row['r_vol'] > 2.5 and row['eff'] < 0.6:
                price = row['high'] if row['close'] < row['open'] else row['low']
                zones.append({'price': price, 'type': 'BATTLE_ZONE', 'time': df.index[i]})
        self.active_zones = zones

    def run_state_machine(self, df):
        """Persistent State Machine: No resets between tests [cite: 2026-01-28]."""
        self.confirmed_signals = {}
        for i in range(50, len(df)):
            row = df.iloc[i]
            # Check proximity to any global zone
            is_near_zone = any(abs(row['close'] - z['price'])/row['close'] < 0.0015 for z in self.active_zones)
            
            if is_near_zone and row['r_vol'] > 2.2 and row['eff'] < 0.65:
                # Identification of a Trap
                if row['close'] < row['ema'] and row['close'] < row['open']:
                    self.confirmed_signals[df.index[i]] = "SHORT_TRAP"
                elif row['close'] > row['ema'] and row['close'] > row['open']:
                    self.confirmed_signals[df.index[i]] = "LONG_TRAP"

def process(data, live_test_size=200):
    # 1. Initialize and Process Global Data
    bot = MarketPsychologyAnalyzer()
    full_df = bot._calculate_metrics(data)
    bot.build_global_map(full_df)
    bot.run_state_machine(full_df)

    # 2. Prepare Plot Data
    plot_data = full_df.tail(live_test_size).copy()
    # Convert index to matplotlib date format for the X-axis
    plot_data['date_num'] = mdates.date2num(plot_data.index)
    
    fig, ax = plt.subplots(figsize=(15, 8))
    
    # 3. Plot Candlesticks with Time Axis
    # Width for 1-minute candles in date_num format is approx 0.0006
    ohlc = plot_data[['date_num', 'open', 'high', 'low', 'close']].values
    candlestick_ohlc(ax, ohlc, width=0.0005, colorup='#26a69a', colordown='#ef5350', alpha=0.8)
    
    # 4. Format X-Axis as Timestamps
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    
    # 5. Plot Battle Zones
    for zone in bot.active_zones:
        # Only plot zones that are within the current price range to keep chart clean
        if plot_data['low'].min() <= zone['price'] <= plot_data['high'].max():
            ax.axhline(y=zone['price'], color='blue', linestyle='--', alpha=0.2)
            
    # 6. Plot Persistent Signals
    for ts, sig_type in bot.confirmed_signals.items():
        if ts in plot_data.index:
            date_num = mdates.date2num(ts)
            price = plot_data.loc[ts, 'high'] if "SHORT" in sig_type else plot_data.loc[ts, 'low']
            color = 'red' if "SHORT" in sig_type else 'green'
            
            ax.annotate(sig_type, xy=(date_num, price), 
                        xytext=(0, 20 if "SHORT" in sig_type else -20),
                        textcoords='offset points', ha='center',
                        arrowprops=dict(facecolor=color, shrink=0.05, width=1, headwidth=4),
                        color=color, fontweight='bold')

    plt.title(f"NIFTY Timestamp Analysis (Window: {live_test_size} min)")
    plt.grid(True, alpha=0.1)
    plt.xticks(rotation=45)
    plt.show()

def main():
    tv = TvDatafeed()
    # Always fetch a large enough buffer for indicator warm-up
    data = tv.get_hist(symbol='NIFTY', exchange='NSE', interval=Interval.in_1_minute, n_bars=3000)
    
    # Compare 100 vs 400 - Signals will now be perfectly aligned on the time axis
    process(data, live_test_size=100)
    process(data, live_test_size=400)

if __name__ == "__main__":
    main()