
from pymongo import MongoClient
import csv
from tape_reading_engine_v2 import OrderFlowAnalyzerV2
from database import get_tick_data_collection

def run_backtest():
    collection = get_tick_data_collection()

    # Validation keys: Reliance & Infy (from user request)
    target_keys = ['NSE_EQ|INE002A01018', 'NSE_EQ|INE009A01021']
    print(f"Starting Failure Auction Strategy Backtest on: {target_keys}")

    output_filename = "trades_failed_auction_backtest.csv"
    csv_file = open(output_filename, "w", newline='')

    # Simple writer wrapper to match expected interface
    class CSVWrapper:
        def __init__(self, f):
            self.f = f
        def write(self, s):
            self.f.write(s)
            self.f.flush()

    writer = CSVWrapper(csv_file)
    writer.write("Instrument,EntryTime,Type,EntryPrice,ExitTime,ExitPrice,PnL,Reason\n")

    total_trades = 0
    total_pnl = 0

    for key in target_keys:
        print(f"Processing {key}...")

        # Use V2 Analyzer
        analyzer = OrderFlowAnalyzerV2(
            instrument_key=key,
            csv_writer=writer,
            trailing_stop_points=5.0,
            target_1_points=10.0
        )

        # Fetch data sorted by time
        cursor = collection.find({'instrumentKey': key}).sort('_insertion_time', 1)
        count = 0

        for tick in cursor:
            analyzer.process_tick(tick)
            count += 1
            if count % 10000 == 0:
                print(f"  Processed {count} ticks...", end='\r')

        print(f"  Processed {count} ticks. Done.")
        analyzer.finish()

        t_count = analyzer.stats['TRADES_TAKEN']
        # Calculate PL from trades list
        pnl = sum(t['pnl'] for t in analyzer.trades)
        print(f"  -> {key}: {t_count} Trades | PnL: {pnl:.2f}")
        print(f"     Signals: {analyzer.stats}")

        total_trades += t_count
        total_pnl += pnl

    csv_file.close()

    print("\n--- BACKTEST SUMMARY ---")
    print(f"Total Trades: {total_trades}")
    print(f"Total PnL: {total_pnl:.2f}")
    print(f"Trades saved to {output_filename}")

if __name__ == "__main__":
    run_backtest()
