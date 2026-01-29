"""
pine_converted.py
Converted (approximate) from provided Pine Script to Python.
Modular functions, hybrid (TA-Lib if available, else pandas/numpy).
Produces numeric columns only.

Usage:
  import pandas as pd
  from pine_converted import add_emas_vwap, add_candle_metrics, add_volume_bubbles, add_mf_will, add_dynamic_pivot, add_avdbs, apply_all

  df = pd.read_csv("ohlcv.csv", parse_dates=True, index_col=0)  # must have open,high,low,close,volume
  df = add_emas_vwap(df, use_talib=True)
  df = add_candle_metrics(df)
  df = add_volume_bubbles(df)
  df = add_mf_will(df)
  df = add_dynamic_pivot(df)
  df = add_avdbs(df)
  # or
  df = apply_all(df)
"""

from typing import Optional, Dict
import numpy as np
import pandas as pd

# Try TA-Lib first (hybrid mode)
try:
    import talib
    _HAS_TALIB = True
except Exception:
    _HAS_TALIB = False

# -------------------------
# Helper wrappers (EMA, SMA, STD, RSI, ATR, DEMA)
# Use talib when available for faster native impls
# -------------------------
def _ensure_float(series: pd.Series) -> np.ndarray:
    """Convert pandas series to float64 numpy array (TA-Lib requirement)."""
    return series.astype(float).values


def _ema(series: pd.Series, timeperiod: int) -> pd.Series:
    if _HAS_TALIB:
        arr = _ensure_float(series)
        return pd.Series(talib.EMA(arr, timeperiod=timeperiod), index=series.index)
    else:
        return series.astype(float).ewm(span=timeperiod, adjust=False).mean()


def _sma(series: pd.Series, length: int) -> pd.Series:
    if _HAS_TALIB:
        arr = _ensure_float(series)
        return pd.Series(talib.SMA(arr, timeperiod=length), index=series.index)
    else:
        return series.astype(float).rolling(length, min_periods=1).mean()


def _stdev(series: pd.Series, length: int) -> pd.Series:
    # Use pandas; talib.STDDEV also expects float64
    return series.astype(float).rolling(length, min_periods=1).std(ddof=0)

def _rsi(series: pd.Series, length: int) -> pd.Series:
    if _HAS_TALIB:
        return pd.Series(talib.RSI(series.values, timeperiod=length), index=series.index)
    else:
        delta = series.diff()
        up = delta.clip(lower=0)
        down = -delta.clip(upper=0)
        ma_up = up.ewm(alpha=1/length, adjust=False).mean()
        ma_down = down.ewm(alpha=1/length, adjust=False).mean()
        rs = ma_up / (ma_down.replace(0, np.nan))
        rsi = 100 - 100 / (1 + rs)
        return rsi.fillna(50)

def _atr(df: pd.DataFrame, length: int) -> pd.Series:
    # df must have high, low, close
    high = df['high']
    low = df['low']
    close = df['close']
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Wilder smoothing (EMA with alpha=1/length but adjust=False -> Wilder)
    return tr.ewm(alpha=1/length, adjust=False).mean()

def _dema(series: pd.Series, length: int) -> pd.Series:
    e1 = _ema(series, length)
    e2 = _ema(e1, length)
    return 2 * e1 - e2

def _vwma(df: pd.DataFrame, length: int) -> pd.Series:
    """Volume-weighted moving average: sum(price*volume)/sum(volume) over window"""
    pv = (df['close'] * df['volume']).rolling(length, min_periods=1).sum()
    v = df['volume'].rolling(length, min_periods=1).sum()
    return pv.div(v.replace(0, np.nan)).fillna(method='ffill')

# -------------------------
# 1) EMAs and VWAP and prior day H/L/O/C
# -------------------------
def add_emas_vwap(df: pd.DataFrame, use_talib: bool = True, ema_periods=(5, 9, 20, 200)) -> pd.DataFrame:
    """
    Adds columns:
      ema_5, ema_9, ema_20, ema_200, vwap, prior_high, prior_low, prior_open, prior_close
    """
    df = df.copy()
    open_col = df['open']; high_col = df['high']; low_col = df['low']; close_col = df['close']; vol = df['volume']

    # EMAs
    pmap = {5: 'ema_5', 9: 'ema_9', 20: 'ema_20', 200: 'ema_200'}
    for p in ema_periods:
        df[pmap.get(p,p)] = _ema(close_col, p)

    # VWAP - intraday VWAP requires intraday grouping, here we compute session VWAP using full index.
    # If df is daily, this is same as close-based VWAP over whole series; keep simple: rolling VWAP over all bars (cumulative).
    # We'll compute a session-like VWAP by resetting each day if index is DatetimeIndex
    if isinstance(df.index, pd.DatetimeIndex):
        # group by date
        vwap = (df['close'] * df['volume']).groupby(df.index.date).cumsum() / df['volume'].groupby(df.index.date).cumsum()
        # align index back
        vwap.index = df.index
        df['vwap'] = vwap
    else:
        df['vwap'] = (df['close'] * df['volume']).cumsum() / df['volume'].cumsum()

    # Prior daily HLOC (previous day's values). If intraday, we group by date.
    if isinstance(df.index, pd.DatetimeIndex):
        dates = pd.Series(df.index.date, index=df.index)
        # compute last daily values using groupby-apply shift
        daily = df.groupby(dates).agg({'high': 'max', 'low': 'min', 'open': 'first', 'close': 'last'})
        daily_shifted = daily.shift(1)
        # map back to rows using the date key
        df['prior_high'] = dates.map(lambda d: daily_shifted.loc[d]['high'] if d in daily_shifted.index else np.nan)
        df['prior_low'] = dates.map(lambda d: daily_shifted.loc[d]['low'] if d in daily_shifted.index else np.nan)
        df['prior_open'] = dates.map(lambda d: daily_shifted.loc[d]['open'] if d in daily_shifted.index else np.nan)
        df['prior_close'] = dates.map(lambda d: daily_shifted.loc[d]['close'] if d in daily_shifted.index else np.nan)
    else:
        # no datetime index -> prior values are simple shifts of daily rows
        df['prior_high'] = df['high'].shift(1)
        df['prior_low'] = df['low'].shift(1)
        df['prior_open'] = df['open'].shift(1)
        df['prior_close'] = df['close'].shift(1)

    return df

# -------------------------
# 2) Candle metrics (body, shadows, doji-like)
# -------------------------
def add_candle_metrics(df: pd.DataFrame,
                       bodyPercentThreshold: float = 10.0,
                       shadowRatioThreshold: float = 50.0,
                       topPercentThreshold: float = 80.0,
                       bottomPercentThreshold: float = 20.0) -> pd.DataFrame:
    """
    Adds:
      body_size, candle_range, upper_shadow, lower_shadow, total_range,
      is_small_body, is_balanced_wicks, is_doji_close_mid (approx), close_pos_pct, close_at_top, close_at_bottom
    """
    df = df.copy()
    o = df['open']; c = df['close']; h = df['high']; l = df['low']
    df['body_size'] = (c - o).abs()
    df['candle_range'] = h - l
    df['upper_shadow'] = h - df[['open', 'close']].max(axis=1)
    df['lower_shadow'] = df[['open', 'close']].min(axis=1) - l
    df['total_range'] = df['candle_range']  # alias

    # Avoid division by zero
    total_range = df['total_range'].replace(0, np.nan)

    df['is_small_body'] = (df['body_size'] / total_range * 100).fillna(0) <= bodyPercentThreshold
    df['is_balanced_wicks'] = (df['upper_shadow'] - df['lower_shadow']).abs() / total_range * 100
    df['is_balanced_wicks'] = df['is_balanced_wicks'].fillna(1000) <= shadowRatioThreshold
    df['is_doji_close_mid'] = df['is_small_body'] & df['is_balanced_wicks']

    df['close_pos_pct'] = ((c - l) / total_range * 100).fillna(50)
    df['close_at_top'] = df['close_pos_pct'] >= topPercentThreshold
    df['close_at_bottom'] = df['close_pos_pct'] <= bottomPercentThreshold

    return df

# -------------------------
# 3) Volume Bubble / Normalized Volume
# -------------------------
def add_volume_bubbles(df: pd.DataFrame,
                       stdDevPeriod: int = 48,
                       std_multiplier: int = 4,
                       bubbleVolumePeriod: int = 100,
                       BubbleSize: float = 2.5,
                       BubbleSizeDelta: float = 0.75,
                       levels_qty: int = 20):
    """
    Adds:
      vol_std, vol_mean, norm_vol, bubble_size, bubble_cond_{1..5}
    bubble_size derived similar to Pine script:
      bubblesize = max(round(volume / avg(sma(volume,bubbleVolumePeriod), sma(volume,10))),
                       round(dema(volume,3) / avg(...)))
    """
    df = df.copy()
    vol = df['volume']
    df['vol_std'] = _stdev(vol, stdDevPeriod)
    df['vol_mean'] = _sma(vol, stdDevPeriod)
    # norm_vol similar to (volume - avg) / std
    df['norm_vol'] = (vol - df['vol_mean']).div(df['vol_std'].replace(0, np.nan))

    # bubble denominator
    avg_long_short = (_sma(vol, bubbleVolumePeriod) + _sma(vol, 10)) / 2.0
    denom = avg_long_short.replace(0, np.nan)

    with np.errstate(divide='ignore', invalid='ignore'):
        bs1 = (vol / denom).round().fillna(0)
        bs2 = (_dema(vol, 3) / denom).round().fillna(0)
        bubblesize = pd.concat([bs1, bs2], axis=1).max(axis=1)
    df['bubble_size'] = bubblesize

    # thresholds
    df['bubble_cond_5'] = bubblesize > (BubbleSize + 8 * BubbleSizeDelta)
    df['bubble_cond_4'] = bubblesize > (BubbleSize + 4 * BubbleSizeDelta)
    df['bubble_cond_3'] = bubblesize > (BubbleSize + 2 * BubbleSizeDelta)
    df['bubble_cond_2'] = bubblesize > (BubbleSize + BubbleSizeDelta)
    df['bubble_cond_1'] = bubblesize > BubbleSize

    # condition categories by norm_vol relative thresholds (as in Pine)
    threshold = BubbleSize
    thresholdStepDelta = BubbleSizeDelta
    nv = df['norm_vol'].fillna(0)
    df['vol_bucket_1'] = (nv > 0) & (nv < threshold)
    df['vol_bucket_2'] = (nv >= threshold) & (nv < (threshold + thresholdStepDelta))
    df['vol_bucket_3'] = (nv >= (threshold + 2 * thresholdStepDelta)) & (nv < (threshold + 4 * thresholdStepDelta))
    df['vol_bucket_4'] = (nv >= (threshold + 4 * thresholdStepDelta)) & (nv < (threshold + 6 * thresholdStepDelta))
    df['vol_bucket_5'] = nv >= (threshold + 6 * thresholdStepDelta)

    return df

# -------------------------
# 4) MF_WILL / Godmode / Order Block detection (approx)
#    - This is an approximate port. Many parts rely on multi-timeframe 'request.security' in Pine.
#    - We'll compute godmode using current timeframe's data.
# -------------------------
def _ttsi(src: pd.Series, len0: int, len1: int) -> pd.Series:
    # ttsi: pc = change(src)/avg(src, src.shift(1)), then ema twice
    pc = src.diff() / ((src + src.shift(1)) / 2.0).replace(0, np.nan)
    ma0 = _ema(pc.fillna(0), len0)
    ma1 = _ema(ma0, len1)
    apc = (src - src.shift(1)).abs()
    ma2 = _ema(apc.fillna(0), len0)
    ma3 = _ema(ma2, len1)
    return 100 * (ma1.div(ma3.replace(0, np.nan)))

def _tci(src: pd.Series, len0: int, len1: int) -> pd.Series:
    # TCI per script: ta.ema((_src - ta.ema(_src, len0)) / (0.025 * ta.ema(abs(_src - ta.ema(_src, len0)), len0)), len1) + 50
    ema_len0 = _ema(src, len0)
    denom = 0.025 * _ema((src - ema_len0).abs(), len0)
    base = (src - ema_len0).div(denom.replace(0, np.nan))
    return _ema(base.fillna(0), len1) + 50

def _mf_indicator(src: pd.Series, A: pd.Series, len2: int) -> pd.Series:
    # mf in pine: 100 - 100/(1 + sum(A*(change(_src) <=0 ? 0 : _src), len2) / sum(A*(change(_src) >=0 ? 0 : _src), len2))
    ch = src.diff()
    pos = src.where(ch > 0, 0) * A
    neg = src.where(ch < 0, 0) * A
    sum_pos = pos.rolling(len2, min_periods=1).sum()
    sum_neg = neg.rolling(len2, min_periods=1).sum().abs()
    ratio = sum_pos.div(sum_neg.replace(0, np.nan))
    return 100.0 - 100.0 / (1.0 + ratio.replace([np.inf, -np.inf], np.nan)).fillna(0)

def _willy(src: pd.Series, len1: int, len0: int) -> pd.Series:
    # willy(per pine): 60 * (src - highest(src,len1)) / (highest - lowest) + 80
    highest = src.rolling(len1, min_periods=1).max()
    lowest = src.rolling(len1, min_periods=1).min()
    denom = (highest - lowest).replace(0, np.nan)
    return 60 * (src - highest).div(denom) + 80

def add_mf_will(df: pd.DataFrame,
                len0: int = 9, len1: int = 26, len2: int = 13, cou0: int = 3,
                smo0: bool = True, highLevel: int = 70, lowLevel: int = 30):
    """
    Adds:
      gm_raw, gm_smooth, gm_overbought (boolean), gm_oversold (boolean),
      vol_support_high, vol_support_low, vol_resist_high, vol_resist_low
    Notes:
      - This is an approximate translation of the 'godmode' composite and the calc() block.
      - The original made MTF security calls; here we operate on the provided df only.
    """
    df = df.copy()
    close = df['close']
    vol = df['volume']

    # ttsi and tci require parameters (we'll use len0,len1, len2 from function signature)
    ttsi_series = _ttsi(close, len0, len1)
    tci_series = _tci(close, len0, len1)
    rsi_series = _rsi(close, len2)

    # mf uses volume A in original, use vol
    mf_series = _mf_indicator(close, vol, len2)
    willy_series = _willy(close, len1, len0)

    # godmode = avg(tci, csi, mf, willy) where csi = avg(rsi, ttsi*50+50)
    csi = (rsi_series + (ttsi_series * 50 + 50)) / 2.0
    gm_raw = (tci_series + csi + mf_series + willy_series) / 4.0

    # smoothing
    smt = _sma(gm_raw, len0) if smo0 else gm_raw
    df['gm_raw'] = gm_raw
    df['gm_smooth'] = smt

    # counters for overbought/oversold runs (gr, gs, gsdx)
    # gr increments if gm>highLevel else resets
    gr = (smt > highLevel).astype(int)
    gs = (smt < lowLevel).astype(int)
    # count consecutive runs
    df['gr_run'] = gr.groupby((gr == 0).cumsum()).cumsum()
    df['gs_run'] = gs.groupby((gs == 0).cumsum()).cumsum()
    df['gsdx_run'] = ((smt > highLevel) | (smt < lowLevel)).astype(int).groupby(lambda x: 0).cumsum()

    # mark support/resistance points when run >= cou0 -> store high or low
    cond_gr = df['gr_run'] >= cou0
    cond_gs = df['gs_run'] >= cou0
    # For mapping to price, we follow pine where grH= h else na etc.
    df['vol_resist_high'] = df['high'].where(cond_gr, np.nan)
    df['vol_resist_low'] = df['low'].where(cond_gr, np.nan)
    df['vol_support_high'] = df['high'].where(cond_gs, np.nan)
    df['vol_support_low'] = df['low'].where(cond_gs, np.nan)

    # boolean overbought/oversold
    df['gm_overbought'] = smt > highLevel
    df['gm_oversold'] = smt < lowLevel

    # cleanup intermediate counters (user asked to skip unused large internals, but keep run if needed)
    df.drop(columns=[c for c in ['gr_run', 'gs_run', 'gsdx_run'] if c in df.columns], inplace=True, errors='ignore')

    return df

# -------------------------
# 5) Dynamic Pivot (mumale) - simplified; omit dyn_range as requested
# -------------------------
def _calc_evwma(price: pd.Series, vol: pd.Series, evBandlength: int) -> pd.Series:
    """
    Elastic VWMA approximation from Pine calc_evwma:
    data := (nz(data[1]) * (nb_floating_shares - vol)/nb_floating_shares) + (vol*price/nb_floating_shares)
    where nb_floating_shares = sum(vol, evBandlength)
    We'll compute a rolling eVWMA via explicit loop for correctness (vectorized windows are possible but more complex).
    """
    price = price.fillna(method='ffill').fillna(0.0)
    vol = vol.fillna(0.0)
    res = pd.Series(np.nan, index=price.index)
    # compute rolling sum of vol for denominator by index
    rv = vol.rolling(evBandlength, min_periods=1).sum()
    # We'll compute the formula per row using previous cached value
    prev_val = 0.0
    # To avoid heavy Python loops over very long series we'll use a faster cumulative approach approximating their update:
    # Implement as: eVWMA[t] = (eVWMA[t-1] * (rv[t] - vol[t]) + vol[t] * price[t]) / rv[t]
    # initialize first valid
    for i in range(len(price)):
        denom = rv.iat[i] if rv.iat[i] != 0 else 1.0
        prev_val = (prev_val * (denom - vol.iat[i]) + vol.iat[i] * price.iat[i]) / denom
        res.iat[i] = prev_val
    return res

def add_dynamic_pivot(df: pd.DataFrame,
                      forceLength3: int = 50, pivotLength3: int = 10,
                      evmaLen: int = 5):
    """
    Adds:
      dyn_pivot
    Approximates dynamicPivot() in Pine script. Omits dyn_range as requested.
    """
    df = df.copy()
    # bodySize from earlier; if not present compute
    if 'body_size' not in df.columns:
        df = add_candle_metrics(df)

    bodySize = df['body_size']
    # scaling per pine: scaling = bodySize / max(bodySize, forceLen) where maxBody = highest(bodySize, forceLen)
    maxBody = bodySize.rolling(forceLength3, min_periods=1).max().replace(0, np.nan)
    scaling = bodySize.div(maxBody.fillna(1.0)).fillna(0.0)

    # vwap used for vwapFactor
    if 'vwap' not in df.columns:
        df = add_emas_vwap(df)
    vwap = df['vwap']

    vwapFactorUp = (df['close'] > vwap).astype(int) * 0.5 + 1.0  # 1.5 if above else 1.0
    vwapFactorDown = (df['close'] < vwap).astype(int) * 0.5 + 1.0

    upForce = ((df['close'] - df['open']) > 0).astype(float) * df['volume'] * scaling * vwapFactorUp
    downForce = ((df['close'] - df['open']) < 0).astype(float) * df['volume'] * scaling * vwapFactorDown

    smUp = _sma(upForce.fillna(0), forceLength3)
    smDown = _sma(downForce.fillna(0), forceLength3)
    netForce = smUp - smDown

    typicalPrice = (df['high'] + df['low'] + df['close']) / 3.0
    basePivot = _sma(typicalPrice, pivotLength3)

    forceScale = _sma((df['close'].diff().abs() / df['close']).replace([np.inf, -np.inf], 0).fillna(0), pivotLength3)
    highestNetForce = netForce.abs().rolling(pivotLength3, min_periods=1).max().replace(0, np.nan)
    forceAdj = netForce.div(highestNetForce.replace(0, np.nan)).fillna(0)

    dynPivot = basePivot + (forceAdj * df['close'] * forceScale).fillna(0)
    df['dyn_pivot'] = dynPivot
    return df

# -------------------------
# 6) Advanced Volume-Driven Breakout System (AVDBS)
# -------------------------
def add_avdbs(df: pd.DataFrame,
              vf_ma_type: str = 'eVWMA', vf_ma_period: int = 20, vf_breakout_multiplier: float = 2.0,
              vs_ma_type: str = 'eVWMA', vs_ma_period: int = 20, vs_threshold_multiplier: float = 4.0,
              use_rvol: bool = False, rvol_ma_type: str = 'eVWMA', rvol_ma_period: int = 10, rvol_threshold: float = 2.0,
              use_cnv: bool = False, cnv_ma_type: str = 'eVWMA', cnv_ma_period: int = 10):
    """
    Adds columns related to AVDBS:
      bull_volume, bear_volume, rvol, buy_volume_signal, sell_volume_signal,
      vs_significant, vs_high, vs_low, net_volume, cnv, smoothed_cnv, cnv_bullish, cnv_bearish
    """

    df = df.copy()
    vol = df['volume']
    # bull/bear volumes
    bull_volume = vol.where(df['close'] > df['open'], 0.0)
    bear_volume = vol.where(df['open'] > df['close'], 0.0)
    df['bull_volume'] = bull_volume
    df['bear_volume'] = bear_volume

    # Helper: MA selection
    def calc_ma(ma_type: str, series: pd.Series, length: int):
        if ma_type == 'SMA':
            return _sma(series, length)
        elif ma_type == 'EMA':
            return _ema(series, length)
        elif ma_type == 'WMA':
            # simple weighted moving average via convolution
            weights = np.arange(1, length + 1)
            return series.rolling(length).apply(lambda x: np.dot(x, weights[-len(x):]) / weights[-len(x):].sum(), raw=True)
        elif ma_type == 'HMA':
            half = int(length / 2) if length > 1 else 1
            wma1 = calc_ma('WMA', series, half)
            wma2 = calc_ma('WMA', series, length)
            return calc_ma('WMA', 2 * wma1 - wma2, int(np.sqrt(length)))
        elif ma_type == 'VWMA':
            # volume-weighted moving average using close*vol over vol
            tmp_df = pd.DataFrame({'p': series, 'v': df['volume']})
            return (tmp_df['p'] * tmp_df['v']).rolling(length, min_periods=1).sum().div(tmp_df['v'].rolling(length, min_periods=1).sum().replace(0, np.nan))
        elif ma_type == 'eVWMA':
            return _calc_evwma(series, df['volume'], length)
        else:
            return _sma(series, length)

    # Relative Volume
    if use_rvol:
        avg_volume_for_rvol = calc_ma(rvol_ma_type, vol, rvol_ma_period)
        df['rvol'] = vol.div(avg_volume_for_rvol.replace(0, np.nan))
    else:
        df['rvol'] = np.nan

    # Volume spike thresholds
    vs_ma = calc_ma(vs_ma_type, vol, vs_ma_period)
    vs_high_threshold = vs_ma * vs_threshold_multiplier
    vs_mid_threshold = vs_high_threshold / 2.0
    vs_low_threshold = vs_ma / 2.0

    # Volume flow MAs
    bull_ma = calc_ma(vf_ma_type, bull_volume, vf_ma_period)
    bear_ma = calc_ma(vf_ma_type, bear_volume, vf_ma_period)

    # Signals (use crossover: current > ma and previous <= ma)
    def crossover(series, ma):
        return (series > ma) & (series.shift(1) <= ma.shift(1))

    buy_volume_signal = crossover(bull_volume, bull_ma) & (~(use_rvol) | (df['rvol'] > rvol_threshold))
    sell_volume_signal = crossover(bear_volume, bear_ma) & (~(use_rvol) | (df['rvol'] > rvol_threshold))

    vs_significant = crossover(vol, vs_high_threshold)
    vs_high = crossover(vol, vs_mid_threshold)
    vs_low = crossover(vol, vs_low_threshold)

    # Net volume and CNV
    price_change = df['close'].diff()
    net_volume = price_change.apply(lambda x: 0 if pd.isna(x) else (df['volume'] * (1 if x > 0 else (-1 if x < 0 else 0))))
    # cumulative net volume
    cnv = net_volume.cumsum() if use_cnv else pd.Series(np.nan, index=df.index)

    # smoothed cnv
    if use_cnv:
        smoothed_cnv = cnv - calc_ma(cnv_ma_type, cnv, cnv_ma_period)
    else:
        smoothed_cnv = pd.Series(np.nan, index=df.index)

    cnv_bullish = (smoothed_cnv > 0) if use_cnv else pd.Series(True, index=df.index)
    cnv_bearish = (smoothed_cnv <= 0) if use_cnv else pd.Series(True, index=df.index)

    # Final combined conditions excluding significant volume moves (per script logic)
    buy_volume_condition = buy_volume_signal & ((~use_rvol) | (df['rvol'] > rvol_threshold)) & cnv_bullish & (~(vs_high | vs_significant).fillna(False))
    sell_volume_condition = sell_volume_signal & ((~use_rvol) | (df['rvol'] > rvol_threshold)) & cnv_bearish & (~(vs_high | vs_significant).fillna(False))

    bearish_overextension = (vs_high | vs_significant).fillna(False) & (df['close'] < df['open']) & ((~use_rvol) | (df['rvol'] > rvol_threshold)) & (~sell_volume_signal)
    bullish_overextension = (vs_high | vs_significant).fillna(False) & (df['close'] > df['open']) & ((~use_rvol) | (df['rvol'] > rvol_threshold)) & (~buy_volume_signal)

    df['rvol'] = df['rvol']
    df['vs_significant'] = vs_significant.fillna(False)
    df['vs_high'] = vs_high.fillna(False)
    df['vs_low'] = vs_low.fillna(False)
    df['buy_volume_signal'] = buy_volume_condition.fillna(False)
    df['sell_volume_signal'] = sell_volume_condition.fillna(False)
    df['bearish_overext_signal'] = bearish_overextension.fillna(False)
    df['bullish_overext_signal'] = bullish_overextension.fillna(False)
    df['net_volume'] = net_volume
    df['cnv'] = cnv
    df['smoothed_cnv'] = smoothed_cnv
    df['cnv_bullish'] = cnv_bullish
    df['cnv_bearish'] = cnv_bearish

    return df

# -------------------------
# 7) Order Block ROC-based signals (basic)
# -------------------------
def add_order_block_signals(df: pd.DataFrame, sens: int = 28):
    """
    Adds:
      roc_4 (percentage), ob_bull_signal (crossover of roc and sens_adj), ob_bear_signal (crossunder)
    Uses roc computed on open (to mimic Pine script roc = (open - open[4])/open[4]*100)
    sens input is percent; sens_adj in Pine was sens / 100
    """
    df = df.copy()
    df['roc_4'] = (df['open'] - df['open'].shift(4)).div(df['open'].shift(4).replace(0, np.nan)) * 100
    sens_adj = sens / 100.0
    # crossover of roc and sens_adj: since roc in percent while sens_adj is fractional in Pine, Pine's roc variable was calculated differently (they used open differences then compared to sens_adj). To keep the spirit:
    df['ob_bull_signal'] = (df['roc_4'] > sens_adj) & (df['roc_4'].shift(1) <= sens_adj)
    df['ob_bear_signal'] = (df['roc_4'] < -sens_adj) & (df['roc_4'].shift(1) >= -sens_adj)
    return df

# -------------------------
# Convenience: apply all selected modules (modular)
# -------------------------
def apply_all(df: pd.DataFrame,
              apply_ema_vwap: bool = True,
              apply_candle_metrics: bool = True,
              apply_vol_bubbles: bool = True,
              apply_mf_will: bool = True,
              apply_dynamic_pivot: bool = True,
              apply_avdbs: bool = True,
              apply_order_block: bool = True,
              hybrid_use_talib: bool = True) -> pd.DataFrame:
    """
    Convenience wrapper that applies modules in a safe order and returns the extended DataFrame.
    """
    result = df.copy()
    # Use hybrid flag to set global _HAS_TALIB? We won't toggle import dynamic; leave as-is.
    if apply_ema_vwap:
        result = add_emas_vwap(result, use_talib=hybrid_use_talib)
    if apply_candle_metrics:
        result = add_candle_metrics(result)
    if apply_vol_bubbles:
        result = add_volume_bubbles(result)
    if apply_mf_will:
        result = add_mf_will(result)
    if apply_dynamic_pivot:
        result = add_dynamic_pivot(result)
    if apply_avdbs:
        result = add_avdbs(result)
    if apply_order_block:
        result = add_order_block_signals(result)
    return result

# End of module

import upstox_client
import sys
import os
import config

configuration = upstox_client.Configuration()
ACCESS_TOKEN =  config.ACCESS_TOKEN
configuration.access_token = config.ACCESS_TOKEN
api_client = upstox_client.ApiClient(configuration)
history_api_instance = upstox_client.HistoryV3Api(api_client)
import pandas as pd
# from pine_converted import apply_all
initial_instruments =["NSE_EQ|INE585B01010"]#,"NSE_EQ|INE139A01034","NSE_EQ|INE1NPP01017","NSE_EQ|INE917I01010","NSE_EQ|INE267A01025","NSE_EQ|INE466L01038","NSE_EQ|INE070A01015","NSE_EQ|INE749A01030","NSE_EQ|INE171Z01026","NSE_EQ|INE591G01025","NSE_EQ|INE160A01022","NSE_EQ|INE814H01029","NSE_EQ|INE102D01028","NSE_EQ|INE134E01011","NSE_EQ|INE009A01021","NSE_EQ|INE376G01013","NSE_EQ|INE619A01035","NSE_EQ|INE465A01025","NSE_EQ|INE540L01014","NSE_EQ|INE237A01028","NSE_EQ|INE361B01024","NSE_EQ|INE811K01011","NSE_EQ|INE01EA01019","NSE_EQ|INE030A01027","NSE_EQ|INE476A01022","NSE_EQ|INE721A01047","NSE_EQ|INE028A01039"]#,"NSE_EQ|INE670K01029","NSE_EQ|INE158A01026","NSE_EQ|INE123W01016","NSE_EQ|INE192A01025","NSE_EQ|INE118A01012","NSE_EQ|INE674K01013","NSE_EQ|INE094A01015","NSE_EQ|INE528G01035","NSE_EQ|INE093I01010","NSE_EQ|INE073K01018","NSE_EQ|INE006I01046","NSE_EQ|INE142M01025","NSE_EQ|INE169A01031","NSE_EQ|INE849A01020","NSE_EQ|INE669C01036","NSE_EQ|INE216A01030","NSE_EQ|INE111A01025","NSE_EQ|INE062A01020","NSE_EQ|INE081A01020","NSE_EQ|INE883A01011","NSE_EQ|INE075A01022","NSE_EQ|INE498L01015","NSE_EQ|INE377N01017","NSE_EQ|INE484J01027","NSE_EQ|INE205A01025","NSE_EQ|INE027H01010","NSE_EQ|INE121A01024","NSE_EQ|INE974X01010","NSE_EQ|INE854D01024","NSE_EQ|INE742F01042","NSE_EQ|INE226A01021","NSE_EQ|INE047A01021","NSE_EQ|INE326A01037","NSE_EQ|INE584A01023","NSE_EQ|INE414G01012","NSE_EQ|INE669E01016","NSE_EQ|INE211B01039","NSE_EQ|INE813H01021","NSE_EQ|INE213A01029","NSE_EQ|INE335Y01020","NSE_EQ|INE931S01010","NSE_EQ|INE704P01025","NSE_EQ|INE053F01010","NSE_EQ|INE127D01025","NSE_EQ|INE021A01026","NSE_EQ|INE356A01018","NSE_EQ|INE733E01010","NSE_EQ|INE115A01026","NSE_EQ|INE702C01027","NSE_EQ|INE388Y01029","NSE_EQ|INE117A01022","NSE_EQ|INE239A01024","NSE_EQ|INE437A01024","NSE_EQ|INE245A01021","NSE_EQ|INE053A01029","NSE_EQ|INE196A01026","NSE_EQ|INE121J01017","NSE_EQ|INE399L01023","NSE_EQ|INE121E01018","NSE_EQ|INE019A01038","NSE_EQ|INE151A01013","NSE_EQ|INE522F01014","NSE_EQ|INE296A01032","NSE_EQ|INE066F01020","NSE_EQ|INE002A01018","NSE_EQ|INE203G01027","NSE_EQ|INE467B01029","NSE_EQ|INE0ONG01011","NSE_EQ|INE079A01024","NSE_EQ|INE0J1Y01017","NSE_EQ|INE260B01028","NSE_EQ|INE040A01034"]

# NiftyFO = ["NSE_FO|41910","NSE_FO|41913","NSE_FO|41914","NSE_FO|41915","NSE_FO|41916","NSE_FO|41917","NSE_FO|41918","NSE_FO|41921","NSE_FO|41922","NSE_FO|41923","NSE_FO|41924","NSE_FO|41925","NSE_FO|41926","NSE_FO|41927","NSE_FO|41928","NSE_FO|41935","NSE_FO|41936","NSE_FO|41939","NSE_FO|41940","NSE_FO|41943","NSE_FO|41944","NSE_FO|41945","NSE_FO|41946"]
BN_FO =["NSE_FO|51414","NSE_FO|51415","NSE_FO|51416","NSE_FO|51417","NSE_FO|51420","NSE_FO|51421","NSE_FO|51439","NSE_FO|51440","NSE_FO|51460","NSE_FO|51461","NSE_FO|51475","NSE_FO|51476","NSE_FO|51493","NSE_FO|51498","NSE_FO|51499","NSE_FO|51500","NSE_FO|51501","NSE_FO|51502","NSE_FO|51507","NSE_FO|51510","NSE_FO|60166","NSE_FO|60167"]
# initial_instruments = symbols
testresults = []
from_date = "2025-12-11"
to_date = "2025-12-12"
for symbol in initial_instruments:
    print(f"\nFetching historical data for {symbol} from {from_date} to {to_date}...")

    historCandlejson = history_api_instance.get_historical_candle_data1(symbol, "minutes", "1", from_date=from_date, to_date=to_date)
    df = pd.DataFrame( )
    # json to DF
    ohlc_data = []
    for candle in historCandlejson.data.candles:
        #json to DF time, open, high, low, close, volume, ts_epoch
        ohlc_data.append({
            'datetime': candle[0],
            'open': candle[1],
            'high': candle[2],
            'low': candle[3],
            'close': candle[4],
            'volume': candle[5]
        })
    #size of ohlc_data print
    print(f"Number of candles fetched: {len(ohlc_data)}")
    df = pd.DataFrame(ohlc_data)
    df['datetime'] = pd.to_datetime(df['datetime'])
#pd.DateTimeIndex
    df.set_index('datetime', inplace=True)

# df = pd.read_csv("ohlcv.csv", parse_dates=['datetime'], index_col='datetime')  # columns: open,high,low,close,volume


    # df_ext = apply_all(df)
    df = add_emas_vwap(df, use_talib=True)
    df = add_candle_metrics(df)

    df = add_mf_will(df)
    df = add_dynamic_pivot(df)
    df = add_avdbs(df)

    df = add_volume_bubbles(df)
    print(df.columns)
    print(df.tail())
    #print to csv
    df.to_csv(f".pine_report_{symbol.replace('|','_')}.csv")
