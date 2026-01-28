import pandas as pd
import numpy as np
from backtesting import Strategy, Backtest
from backtesting.lib import crossover, plot_heatmaps

from pydash import result
import upstox_client
import sys
import os
import config

configuration = upstox_client.Configuration()
ACCESS_TOKEN =  config.ACCESS_TOKEN
configuration.access_token = config.ACCESS_TOKEN
api_client = upstox_client.ApiClient(configuration)
history_api_instance = upstox_client.HistoryV3Api(api_client)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- 1. Custom Indicators ---

import pandas as pd
import numpy as np
# --- UPSTOX CLIENT PLACEHOLDERS ---
# NOTE: These lines are commented out. You must uncomment and ensure
# your Upstox client is correctly initialized in your local environment.
# import upstox_client
# import sys
# import os
# configuration = upstox_client.Configuration()
# ACCESS_TOKEN =  configuration.access_token
# api_client = upstox_client.ApiClient(configuration)
# history_api_instance = upstox_client.HistoryV3Api(api_client)
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# --- 1. Custom Indicators (Contain Fix for .rolling() error) ---

def V_levels(series_volume, sd_period: int = 50, hvb_period: int = 100):
    """
    Calculates boolean flags for High Volume Bars (HVB) and 4X Standard Deviation (SD) volume levels.
    FIX: Converts input array to Pandas Series for .rolling() method usage.
    """
    # *** CRITICAL FIX 1: Convert the backtesting _Array object to a Pandas Series ***
    series_volume_pd = pd.Series(series_volume)

    # 1. 4X Standard Deviation Level (Rolling)
    vol_mean = series_volume_pd.rolling(sd_period).mean()
    vol_std = series_volume_pd.rolling(sd_period).std()

    # Threshold: Volume is 4 times the standard deviation above the mean
    v_4x_sd_threshold = vol_mean.shift(1) + (4 * vol_std.shift(1))

    is_4x_sd_bar = series_volume_pd > v_4x_sd_threshold

    # 2. Highest Volume Bar (Rolling)
    is_hvb_bar = series_volume_pd == series_volume_pd.rolling(hvb_period).max().shift(1)

    # Return as NumPy arrays
    return is_4x_sd_bar.values.astype(bool), is_hvb_bar.values.astype(bool)


def get_swing_high_low_lookback(series_high, series_low, window: int = 10):
    """
    Identifies Swing High/Low using only a lookback window (NO lookahead bias).
    FIX: Converts input arrays to Pandas Series for .rolling() method usage.
    """
    # *** CRITICAL FIX 1: Convert the backtesting _Array object to a Pandas Series ***
    series_high_pd = pd.Series(series_high)
    series_low_pd = pd.Series(series_low)

    is_swing_high = series_high_pd == series_high_pd.rolling(window).max()
    is_swing_low = series_low_pd == series_low_pd.rolling(window).min()

    # Return as NumPy arrays
    return is_swing_high.values.astype(bool), is_swing_low.values.astype(bool)

# --- NEW HELPER FUNCTION (Contains Fix for _Indicator.shift() error) ---
def get_key_levels_price(close, is_key_bar):
    """
    Calculates the price of the previous key bar.
    FIX: Converts input arrays to Pandas Series for .shift() method usage.
    """
    # *** CRITICAL FIX 2: Convert the backtesting _Indicator objects to a Pandas Series ***
    close_series = pd.Series(close)
    is_key_bar_series = pd.Series(is_key_bar)

    # Shift the boolean mask AND the close price backward by 1.
    key_bar_price = np.where(is_key_bar_series.shift(1), close_series.shift(1), np.nan)

    return key_bar_price


# --- 2. Strategy Class Implementation ---

class VolumeStructureStrategy(Strategy):

    # Strategy parameters
    sd_period = 50
    hvb_period = 100
    swing_window = 10
    sl_distance = 0.00
    tp_ratio = 2

    def init(self):
        close = self.data.Close
        high = self.data.High
        low = self.data.Low
        volume = self.data.Volume

        # 1. Volume Levels
        self.is_4x_sd_bar, self.is_hvb_bar = self.I(
            V_levels, volume, self.sd_period, self.hvb_period, name='V_Level_Checks'
        )

        # 2. Swing Levels
        self.is_swing_high, self.is_swing_low = self.I(
            get_swing_high_low_lookback, high, low, self.swing_window, name='Swing_Checks'
        )

        self.is_key_bar = self.is_4x_sd_bar | self.is_hvb_bar | self.is_swing_high | self.is_swing_low

        # 3. Store the price of the key level (Uses the helper function fix)
        self.key_levels = self.I(
            get_key_levels_price, close, self.is_key_bar, name='KeyLevels', plot=False
        )

    def next(self):
        if self.position:


            if self.position.is_long:
                self.risk_points =  self.stop_loss_price-self.entry_price
                # Logic to handle open position and 1:1 move
                current_price = self.data.Close[-1]

                # Calculate the 1:1 profit target
                profit_target_price = self.entry_price + self.risk_points

                # Check if the 1:1 target has been reached or exceeded
                if current_price >= profit_target_price and not self.target_hit:
                    self.target_hit = True
                    # Move the Stop Loss to breakeven (entry price) or higher
                    new_sl = self.entry_price

                    # Ensure new stop loss is not below the current stop loss (backtesting.py handles this automatically)
                    # and update the stop loss
                    if new_sl > self.stop_loss_price:
                        self.stop_loss_price = new_sl

                    # Optional: continue trailing beyond breakeven
                    self.stop_loss_price = max(self.stop_loss_price, current_price - self.risk_points)

                # If the target was hit, you can also implement a continuous trail
                if self.target_hit:
                    # Example: trail at a fixed distance once triggered
                    trailing_distance = self.risk_points * 0.5 # A tighter trail, for example
                    self.stop_loss_price = max(self.stop_loss_price, current_price - trailing_distance)
            elif self.position.is_short:
                self.risk_points =  self.stop_loss_price - self.entry_price
                # Logic to handle open position and 1:1 move
                current_price = self.data.Close[-1]

                # Calculate the 1:1 profit target
                profit_target_price = self.entry_price - self.risk_points

                # Check if the 1:1 target has been reached or exceeded
                if current_price <= profit_target_price and not self.target_hit:
                    self.target_hit = True
                    # Move the Stop Loss to breakeven (entry price) or lower
                    new_sl = self.entry_price

                    # Ensure new stop loss is not above the current stop loss (backtesting.py handles this automatically)
                    # and update the stop loss
                    if new_sl < self.stop_loss_price:
                        self.risk_points = new_sl

                    # Optional: continue trailing beyond breakeven
                    self.stop_loss_price = min(self.stop_loss_price, current_price + self.risk_points)

                # If the target was hit, you can also implement a continuous trail
                if self.target_hit:
                    # Example: trail at a fixed distance once triggered
                    trailing_distance = self.risk_points * 0.5 # A tighter trail, for example
                    self.stop_loss_price = min(self.stop_loss_price, current_price + trailing_distance)

            return


        self.entry_price = self.data.Close[-1]
        self.target_hit = False

        current_close = self.data.Close[-1]
        current_low = self.data.Low[-1]
        current_high = self.data.High[-1]
        is_vol_conf = self.is_4x_sd_bar[-1]

        # --- Identify the most recent significant level ---
        last_key_level_idx = np.flatnonzero(~np.isnan(self.key_levels)).max() if not np.all(np.isnan(self.key_levels)) else None

        if last_key_level_idx is None:
            return

        last_key_level_price = self.key_levels[last_key_level_idx]
        is_last_swing_low = self.is_swing_low[last_key_level_idx]
        is_last_swing_high = self.is_swing_high[last_key_level_idx]

        proximity_threshold = 0.001 * last_key_level_price
        is_near_key_level = abs(current_close - last_key_level_price) < proximity_threshold

        # --- Entry Logic ---

        # 1. Bullish Setup (Bounce off Support)
        if is_near_key_level and (is_last_swing_low or last_key_level_price < current_close):
            if current_close > self.data.Open[-1] and is_vol_conf:

                stop_loss_price = current_low - 1#* (1 - self.sl_distance)
                risk = current_close - stop_loss_price
                take_profit_price = current_close + risk * self.tp_ratio
                self.stop_loss_price = stop_loss_price
                self.buy(sl=stop_loss_price, tp=take_profit_price)

        # 2. Bearish Setup (Rejection off Resistance)
        elif is_near_key_level and (is_last_swing_high or last_key_level_price > current_close):
            if current_close < self.data.Open[-1] and is_vol_conf:

                stop_loss_price = current_high +1#* (1 + self.sl_distance)
                risk = stop_loss_price - current_close
                take_profit_price = current_close - risk * self.tp_ratio
                self.stop_loss_price = stop_loss_price
                self.sell(sl=stop_loss_price, tp=take_profit_price)


# --- 3. Data Preparation and Backtest Execution ---

def run_backtest(data: pd.DataFrame, symbol:str):
    """Initializes and runs the backtest."""

    if data.empty or data.shape[0] < 500:
        print("Error: DataFrame is empty or too short. Need at least 500 bars for indicators.")
        return
# UserWarning: Data index is not sorted in ascending order. Sorting.
    data = data.sort_index()
    bt = Backtest(
        data,
        VolumeStructureStrategy,
        cash=100000,
        commission=0.0001,
        exclusive_orders=True,
        finalize_trades=True,

    )

    print("Running Backtest...")
    stats = bt.run()
    #bt.plot() save file to png bt.plot(filename='backtest_plot'+symbol.replace('|','_')+'.png')
    bt.plot(filename='backtest_plot'+symbol.replace('|','_')+'')

    # print("\n--- Strategy Performance Statistics ---")
    # print(stats)

    return stats
all_stats = {}
# --- Main Execution Block ---
if __name__ == '__main__':

    # --------------------------------------------------------------------------------
    # --- Fallback to Synthetic Data for immediate testing without live API ---
    # --------------------------------------------------------------------------------
    from_date = "2025-12-01"
    to_date = "2025-12-08"
    symbols  = ["NSE_EQ|INE585B01010","NSE_EQ|INE139A01034","NSE_EQ|INE1NPP01017"]
    initial_instruments =["NSE_EQ|INE585B01010","NSE_EQ|INE139A01034","NSE_EQ|INE1NPP01017","NSE_EQ|INE917I01010","NSE_EQ|INE267A01025","NSE_EQ|INE466L01038","NSE_EQ|INE070A01015","NSE_EQ|INE749A01030","NSE_EQ|INE171Z01026","NSE_EQ|INE591G01025","NSE_EQ|INE160A01022","NSE_EQ|INE814H01029","NSE_EQ|INE102D01028","NSE_EQ|INE134E01011","NSE_EQ|INE009A01021","NSE_EQ|INE376G01013","NSE_EQ|INE619A01035","NSE_EQ|INE465A01025","NSE_EQ|INE540L01014","NSE_EQ|INE237A01028","NSE_EQ|INE361B01024","NSE_EQ|INE811K01011","NSE_EQ|INE01EA01019","NSE_EQ|INE030A01027","NSE_EQ|INE476A01022","NSE_EQ|INE721A01047","NSE_EQ|INE028A01039"]#,"NSE_EQ|INE670K01029","NSE_EQ|INE158A01026","NSE_EQ|INE123W01016","NSE_EQ|INE192A01025","NSE_EQ|INE118A01012","NSE_EQ|INE674K01013","NSE_EQ|INE094A01015","NSE_EQ|INE528G01035","NSE_EQ|INE093I01010","NSE_EQ|INE073K01018","NSE_EQ|INE006I01046","NSE_EQ|INE142M01025","NSE_EQ|INE169A01031","NSE_EQ|INE849A01020","NSE_EQ|INE669C01036","NSE_EQ|INE216A01030","NSE_EQ|INE111A01025","NSE_EQ|INE062A01020","NSE_EQ|INE081A01020","NSE_EQ|INE883A01011","NSE_EQ|INE075A01022","NSE_EQ|INE498L01015","NSE_EQ|INE377N01017","NSE_EQ|INE484J01027","NSE_EQ|INE205A01025","NSE_EQ|INE027H01010","NSE_EQ|INE121A01024","NSE_EQ|INE974X01010","NSE_EQ|INE854D01024","NSE_EQ|INE742F01042","NSE_EQ|INE226A01021","NSE_EQ|INE047A01021","NSE_EQ|INE326A01037","NSE_EQ|INE584A01023","NSE_EQ|INE414G01012","NSE_EQ|INE669E01016","NSE_EQ|INE211B01039","NSE_EQ|INE813H01021","NSE_EQ|INE213A01029","NSE_EQ|INE335Y01020","NSE_EQ|INE931S01010","NSE_EQ|INE704P01025","NSE_EQ|INE053F01010","NSE_EQ|INE127D01025","NSE_EQ|INE021A01026","NSE_EQ|INE356A01018","NSE_EQ|INE733E01010","NSE_EQ|INE115A01026","NSE_EQ|INE702C01027","NSE_EQ|INE388Y01029","NSE_EQ|INE117A01022","NSE_EQ|INE239A01024","NSE_EQ|INE437A01024","NSE_EQ|INE245A01021","NSE_EQ|INE053A01029","NSE_EQ|INE196A01026","NSE_EQ|INE121J01017","NSE_EQ|INE399L01023","NSE_EQ|INE121E01018","NSE_EQ|INE019A01038","NSE_EQ|INE151A01013","NSE_EQ|INE522F01014","NSE_EQ|INE296A01032","NSE_EQ|INE066F01020","NSE_EQ|INE002A01018","NSE_EQ|INE203G01027","NSE_EQ|INE467B01029","NSE_EQ|INE0ONG01011","NSE_EQ|INE079A01024","NSE_EQ|INE0J1Y01017","NSE_EQ|INE260B01028","NSE_EQ|INE040A01034"]

    # NiftyFO = ["NSE_FO|41910","NSE_FO|41913","NSE_FO|41914","NSE_FO|41915","NSE_FO|41916","NSE_FO|41917","NSE_FO|41918","NSE_FO|41921","NSE_FO|41922","NSE_FO|41923","NSE_FO|41924","NSE_FO|41925","NSE_FO|41926","NSE_FO|41927","NSE_FO|41928","NSE_FO|41935","NSE_FO|41936","NSE_FO|41939","NSE_FO|41940","NSE_FO|41943","NSE_FO|41944","NSE_FO|41945","NSE_FO|41946"]
    BN_FO =["NSE_FO|51414","NSE_FO|51415","NSE_FO|51416","NSE_FO|51417","NSE_FO|51420","NSE_FO|51421","NSE_FO|51439","NSE_FO|51440","NSE_FO|51460","NSE_FO|51461","NSE_FO|51475","NSE_FO|51476","NSE_FO|51493","NSE_FO|51498","NSE_FO|51499","NSE_FO|51500","NSE_FO|51501","NSE_FO|51502","NSE_FO|51507","NSE_FO|51510","NSE_FO|60166","NSE_FO|60167"]
    # initial_instruments = symbols
    testresults = []
    for symbol in initial_instruments:
        print(f"\nFetching historical data for {symbol} from {from_date} to {to_date}...")

        historCandlejson = history_api_instance.get_historical_candle_data1(symbol, "minutes", "1", from_date=from_date, to_date=to_date)
        data_example = pd.DataFrame( )
        # json to DF
        ohlc_data = []
        for candle in historCandlejson.data.candles:
            #json to DF time, open, high, low, close, volume, ts_epoch
            ohlc_data.append({
                'time': candle[0],
                'Open': candle[1],
                'High': candle[2],
                'Low': candle[3],
                'Close': candle[4],
                'Volume': candle[5],
                'ts_epoch': candle[6]
            })
        #size of ohlc_data print
        print(f"Number of candles fetched: {len(ohlc_data)}")
        data_example = pd.DataFrame(ohlc_data)
        data_example['time'] = pd.to_datetime(data_example['time'])
    #pd.DateTimeIndex
        data_example.set_index('time', inplace=True)
        # Run the backtest with the prepared data
        stats = run_backtest(data_example, symbol)
        #put all test results in a list
        all_stats[symbol] = {
        'Return [%]': round(stats['Return [%]'], 2),
        'Sharpe Ratio': round(stats['Sharpe Ratio'], 2),
        'Max Drawdown [%]': round(stats['Max. Drawdown [%]'], 2),
        'Trades': stats['# Trades'],
        'Win Rate [%]': round(stats['Win Rate [%]'], 2),
        'Equity Final [$]': round(stats['Equity Final [$]'], 2)
    }
    # Optional: Plot the backtest for one symbol if you like
    # if symbol == 'AAPL':
    #     bt.plot()

# --- 4. Display Aggregated Results ---

print("\n" + "="*50)
print("AGGREGATED BACKTEST RESULTS")
print("="*50)

# Convert results dictionary to a pandas DataFrame for easy viewing
results_df = pd.DataFrame.from_dict(all_stats, orient='index')
print(results_df)

#sum of all final equity
# len initial_instruments
total_symbols = len(initial_instruments)
print(f"\nTotal Symbols Tested: {total_symbols}")
average_return_per_symbol = results_df['Return [%]'].mean()
print(f"Average Return per Symbol [%]: {average_return_per_symbol}")

total_equity = results_df['Equity Final [$]'].sum()
print(f"Total Equity Final [$]: {total_equity}")
average_return = total_equity/total_symbols
print(f"Average Equity Final per Symbol [$]: {average_return}")
#tolal return percentage average
average_return = results_df['Return [%]'].mean()
print(f"Average Return [%]: {average_return}")

# plot_heatmaps(stats)
# plot_heatmaps(stats, plot_returns=True)
#PLOT TRADES for SYMBOLS ans save charts
for symbol in initial_instruments:
    print(f"\nPlotting backtest results for {symbol}...")
