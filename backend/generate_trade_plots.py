
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from pymongo import MongoClient
import os
import numpy as np
from database import get_tick_data_collection

def plot_instrument_trades(instrument_key, trades_df):
    print(f"Plotting for {instrument_key}...")

    # 1. Fetch Tick Data
    collection = get_tick_data_collection()

    ticks = []
    # Fetch only needed fields to be fast
    cursor = collection.find({'instrumentKey': instrument_key}, {'fullFeed.marketFF.ltpc': 1, '_insertion_time': 1}).sort('_insertion_time', 1)

    for doc in cursor:
        try:
            ff = doc.get('fullFeed', {}).get('marketFF', {})
            ltp = ff.get('ltpc', {}).get('ltp')
            ltt = ff.get('ltpc', {}).get('ltt')

            if ltp:
                if ltt:
                    from datetime import datetime
                    # Match backtest logic: Local Time
                    ts = pd.to_datetime(datetime.fromtimestamp(int(ltt)/1000))
                else:
                    ts = pd.to_datetime(doc['_insertion_time'])

                # Round to nearest second to match trade logs essentially
                # or just keep ms. Trade logs have second precision.
                ticks.append({'time': ts, 'price': float(ltp)})
        except: continue

    if not ticks:
        print(f"No data for {instrument_key}")
        return

    df = pd.DataFrame(ticks)
    df.drop_duplicates(subset=['time'], keep='last', inplace=True)
    df.sort_values('time', inplace=True)
    df.reset_index(drop=True, inplace=True)

    # --- GAP REMOVAL STRATEGY ---
    # We plot against the INDEX (0, 1, 2...) instead of Time.
    # This removes visual gaps for missing data (overnight).

    fig, ax = plt.subplots(figsize=(20, 10))

    # Plot Price against Index
    ax.plot(df.index, df['price'], label='Price', color='gray', linewidth=0.8, alpha=0.7)

    # Filter trades for this instrument
    instr_trades = trades_df[trades_df['Instrument'] == instrument_key].copy()

    # We need to map Trade Times to our DataFrame Index
    # Since Trade Times (Seconds) might not exactly match Tick Times (Millis),
    # we use 'searchsorted' or 'get_indexer' with 'nearest'.

    # Ensure df time is sorted (it is)
    df_times = df['time'].values

    for idx, row in instr_trades.iterrows():
        try:
            # Parse Times (Full DateTime now expected)
            t_entry = pd.to_datetime(row['EntryTime'])
            t_exit = pd.to_datetime(row['ExitTime'])

            # Find nearest index in df
            # searchsorted returns insertion point.
            # We want the nearest existing index.

            idx_entry = df['time'].searchsorted(t_entry)
            idx_exit = df['time'].searchsorted(t_exit)

            # Clamp to bounds
            idx_entry = min(max(0, idx_entry), len(df)-1)
            idx_exit = min(max(0, idx_exit), len(df)-1)

            # If the timestamp diff is too large (> 1 minute), warn?
            # But searchsorted finds the "next" index if not found.
            # Let's assume it's close enough for visual check.

            price_entry = row['EntryPrice']
            price_exit = row['ExitPrice']

            color = 'g' if row['Type'] == 'LONG' else 'r'
            marker_entry = '^' if row['Type'] == 'LONG' else 'v'
            marker_exit = 'x'

            # Plot using INDEX x-coordinates
            ax.scatter(idx_entry, price_entry, color=color, marker=marker_entry, s=100, zorder=5)
            ax.scatter(idx_exit, price_exit, color='black', marker=marker_exit, s=100, zorder=5)
            ax.plot([idx_entry, idx_exit], [price_entry, price_exit], color=color, linestyle='--', linewidth=1.5)

            # Annotate PnL
            ax.annotate(f"{row['PnL']}", (idx_exit, price_exit), xytext=(5, 5), textcoords='offset points', fontsize=9, fontweight='bold')

        except Exception as e:
            print(f"Error plotting trade {idx}: {e}")
            continue

    # Format X-Axis to show Times
    # Pick ~10 ticks
    num_ticks = 12
    step = max(1, len(df) // num_ticks)
    xtick_locs = df.index[::step]
    xtick_labels = [df['time'].iloc[i].strftime('%Y-%m-%d\n%H:%M') for i in xtick_locs]

    ax.set_xticks(xtick_locs)
    ax.set_xticklabels(xtick_labels, rotation=45, ha='right')

    ax.set_title(f"Failed Auction Trades - {instrument_key}")
    ax.set_xlabel("Time (Gap Removed)")
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.3)
    ax.legend(['Price'])

    filename = f"chart_backtest_{instrument_key.replace('|','_')}.png"
    plt.savefig(filename, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved {filename}")

def run():
    csv_file = 'trades_failed_auction_backtest.csv'
    try:
        trades = pd.read_csv(csv_file)
    except:
        print(f"No {csv_file} found")
        return

    print(f"Loaded {len(trades)} trades from {csv_file}")

    instruments = trades['Instrument'].unique()
    for instr in instruments:
        plot_instrument_trades(instr, trades)

if __name__ == "__main__":
    run()
