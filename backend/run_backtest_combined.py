
import sys
import os
import csv
from datetime import datetime
import json

# Ensure root directory is in path for imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import get_tick_data_collection
# Import the new factory
try:
    from strategies.combined_signal_engine import CombinedSignalEngine
except ImportError:
    # If not in path, try appending strategies dir
    sys.path.append(os.path.join(os.path.dirname(__file__), 'strategies'))
    from combined_signal_engine import CombinedSignalEngine

def run_backtest_combined():
    collection = get_tick_data_collection()

    # Validation keys: Requested by User
    target_keys = [
        "NSE_EQ|INE009A01021",
        "NSE_EQ|INE040A01034",
        "NSE_EQ|INE062A01020",
        "NSE_EQ|INE467B01029",
        "NSE_EQ|INE002A01018",
        "NSE_EQ|INE090A01021",
        "NSE_EQ|INE030A01027",
        "NSE_EQ|INE081A01020",
        "NSE_EQ|INE101A01026",
        "NSE_EQ|INE860A01027",
        "NSE_EQ|INE397D01024",
        "NSE_EQ|INE075A01022",
        "NSE_EQ|INE721A01047",
        "NSE_EQ|INE669C01036"
    ]

    # Get any key that has data if targets empty
    if not collection.find_one({'instrumentKey': target_keys[0]}):
         print("Warning: Default keys have no data. Fetching active keys...")
         target_keys = collection.distinct('instrumentKey')[:5]

    print(f"Starting Combined Strategy Backtest on: {target_keys}")

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"backtest_combined_{timestamp_str}.csv"
    html_filename = f"backtest_report_{timestamp_str}.html"

    csv_file = open(csv_filename, "w", newline='')

    class CSVWrapper:
        def __init__(self, f):
            self.f = f
        def write(self, s):
            self.f.write(s)
            self.f.flush()

    writer = CSVWrapper(csv_file)
    header = "Instrument,EntryTime,Type,EntryPrice,ExitTime,ExitPrice,PnL,Reason\n"
    writer.write(header)

    all_trades = []

    total_trades = 0
    total_pnl = 0

    for key in target_keys:
        print(f"Processing {key}...")

        # Instantiate Combined Engine
        # disable throttling for backtest to act on every valid tick time
        # or keep it to simulate realistic skip?
        # Setting obi_throttle_sec=0 for backtest accuracy (assuming we process every recorded tick as 'new')
        # Actually, in backtest, time jumps.
        # The engine uses time.time() for throttling. That's a problem for backtest!
        # CombinedSignalEngine uses time.time().
        # I need to patch it or update it to use tick time.

        # Checking CombinedSignalEngine logic...
        # "now = time.time()" -> This is Wall Clock time!
        # For backtest, we must override this to use Simulation Time.
        # I'll subclass here or modify the engine.
        # Modifying engine is cleaner but risks breaking live if not careful.
        # Subclassing is safer for backtest.

        class BacktestCombinedEngine(CombinedSignalEngine):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.current_sim_time = 0

            def process_tick(self, tick):
                # Extract tick time to fake 'now'
                ff = tick.get('fullFeed', {}).get('marketFF', {})
                ltt = ff.get('ltpc', {}).get('ltt')
                if ltt:
                    self.current_sim_time = int(ltt) / 1000.0
                else:
                    self.current_sim_time = tick.get('_insertion_time', datetime.now()).timestamp()

                # Monkey patch time.time? No, just override the logic or use internal var
                # Actually, CombinedSignalEngine calls time.time() inside process_tick.
                # I cannot easily override a local var 'now = time.time()'.
                # I must override process_tick entire logic? That duplicates code.
                # OR, I temporarily mock time.time in this script loop.
                # Mocking time.time is easiest.

                super().process_tick(tick)

        # Mocking time.time locally
        import time
        original_time = time.time

        # Context variable for current tick time
        current_tick_time = [0]
        def mock_time():
            return current_tick_time[0]

        time.time = mock_time

        analyzer = BacktestCombinedEngine(
            instrument_key=key,
            csv_writer=writer,
            obi_throttle_sec=1.0, # Throttle logic will use mock_time
        )

        # Fetch data
        cursor = collection.find({'instrumentKey': key}).sort('_insertion_time', 1)
        count = 0

        for tick in cursor:
            # Update mock time
            ff = tick.get('fullFeed', {}).get('marketFF', {})
            ltt = ff.get('ltpc', {}).get('ltt')
            if ltt:
                ts = int(ltt) / 1000.0
            else:
                 # Fallback to insertion time
                ts = tick.get('_insertion_time').timestamp()

            current_tick_time[0] = ts

            analyzer.process_tick(tick)
            count += 1
            if count % 10000 == 0:
                print(f"  Processed {count} ticks...", end='\r')

        # Restore time
        time.time = original_time

        print(f"  Processed {count} ticks. Done.")
        # analyzer.finish() # TapeReadingEngine has finish() to close log file

        t_count = analyzer.stats['TRADES_TAKEN']
        trades = analyzer.trades
        all_trades.extend([{**t, 'instrument': key} for t in trades])

        pnl = sum(t['pnl'] for t in trades)
        print(f"  -> {key}: {t_count} Trades | PnL: {pnl:.2f}")

        total_trades += t_count
        total_pnl += pnl

    csv_file.close()

    # --- HTML Report Generation ---
    generate_html_report(all_trades, total_pnl, total_trades, html_filename)

    print("\n--- BACKTEST SUMMARY ---")
    print(f"Total Trades: {total_trades}")
    print(f"Total PnL: {total_pnl:.2f}")
    print(f"Report saved to: {html_filename}")
    print(f"CSV saved to: {csv_filename}")

def generate_html_report(trades, total_pnl, total_account_trades, filename):

    # Calculate stats
    wins = len([t for t in trades if t['pnl'] > 0])
    losses = len([t for t in trades if t['pnl'] <= 0])
    win_rate = (wins / len(trades) * 100) if trades else 0

    trade_rows = ""
    for t in trades:
        color = "green" if t['pnl'] > 0 else "red"
        row = f"""
        <tr>
            <td>{t['entry_time']}</td>
            <td>{t['instrument']}</td>
            <td>{t['side']}</td>
            <td>{t['entry_price']:.2f}</td>
            <td>{t['exit_price']:.2f}</td>
            <td style="color:{color}; font-weight:bold;">{t['pnl']:.2f}</td>
            <td>{t['exit_time']}</td>
        </tr>
        """
        trade_rows += row

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Backtest Report</title>
        <style>
            body {{ font-family: sans-serif; padding: 20px; background: #f0f2f5; }}
            .container {{ max-width: 1000px; margin: auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
            h1 {{ border-bottom: 2px solid #eee; padding-bottom: 10px; }}
            .stats {{ display: flex; gap: 20px; margin-bottom: 20px; }}
            .card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; flex: 1; text-align: center; }}
            .num {{ font-size: 24px; font-weight: bold; color: #333; }}
            .green {{ color: green; }} .red {{ color: red; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background: #eee; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Combined Strategy Backtest Report</h1>
            <div class="stats">
                <div class="card">
                    <div>Net PnL</div>
                    <div class="num { 'green' if total_pnl >= 0 else 'red' }">{total_pnl:.2f}</div>
                </div>
                <div class="card">
                    <div>Total Trades</div>
                    <div class="num">{total_account_trades}</div>
                </div>
                <div class="card">
                    <div>Win Rate</div>
                    <div class="num">{win_rate:.1f}%</div>
                </div>
            </div>

            <h2>Trade Log</h2>
            <table>
                <thead>
                    <tr>
                        <th>Entry Time</th>
                        <th>Instrument</th>
                        <th>Side</th>
                        <th>Entry</th>
                        <th>Exit</th>
                        <th>PnL</th>
                        <th>Exit Time</th>
                    </tr>
                </thead>
                <tbody>
                    {trade_rows}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """

    with open(filename, "w") as f:
        f.write(html)

if __name__ == "__main__":
    run_backtest_combined()
