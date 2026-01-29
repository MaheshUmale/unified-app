import json
import os
from collections import deque
from dataclasses import dataclass, field
import math


# ============================================================
# Utility helpers
# ============================================================

def ema_update(prev, price, length):
    if prev is None:
        return price
    alpha = 2 / (length + 1)
    return prev + alpha * (price - prev)

def sma_update(queue: deque, value: float, length: int):
    queue.append(value)
    if len(queue) > length:
        queue.popleft()
    return sum(queue) / len(queue)

def rolling_max(queue: deque, window: int, new_value: float):
    """Faster rolling max for small windows."""
    queue.append(new_value)
    if len(queue) > window:
        queue.popleft()
    return max(queue)

def rolling_min(queue: deque, window: int, new_value: float):
    queue.append(new_value)
    if len(queue) > window:
        queue.popleft()
    return min(queue)

def atr_update(prev_atr, high, low, prev_close, length=14):
    tr = max(
        high - low,
        abs(high - prev_close),
        abs(low - prev_close)
    )
    if prev_atr is None:
        return tr
    return (prev_atr * (length - 1) + tr) / length


# ============================================================
# Tick → Bar Builder (multi-timeframe)
# ============================================================

@dataclass
class BarBuilder:
    timeframe_sec: int
    open: float = None
    high: float = None
    low: float = None
    close: float = None
    volume: float = 0
    last_ts: int = None  # unix timestamp (sec)

    def update_tick(self, price: float, volume: float, ts: int):
        """
        Accepts tick, returns None or a completed bar
        """
        # First bar
        if self.open is None:
            self.open = self.high = self.low = self.close = price
            self.volume = volume
            self.last_ts = ts
            return None

        elapsed = ts - self.last_ts
        bar_closed = elapsed >= self.timeframe_sec

        if bar_closed:
            # Emit finished bar
            bar = {
                'open': self.open,
                'high': self.high,
                'low': self.low,
                'close': self.close,
                'volume': self.volume
            }

            # Start new bar
            self.open = self.high = self.low = self.close = price
            self.volume = volume
            self.last_ts = ts
            return bar

        # Inside same bar → update values
        self.close = price
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.volume += volume
        return None


# ============================================================
# Incremental Indicator Engine (ALL indicators)
# ============================================================

@dataclass
class IndicatorState:
    # --- EMAs ---
    ema5: float = None
    ema9: float = None
    ema20: float = None
    ema200: float = None

    # --- Candle metrics ---
    body_size: float = 0
    upper_shadow: float = 0
    lower_shadow: float = 0
    close_pos_pct: float = 50

    # --- Volume Bubble components ---
    vol_queue_long: deque = field(default_factory=lambda: deque(maxlen=100))
    vol_queue_short: deque = field(default_factory=lambda: deque(maxlen=10))
    vol_queue_std: deque = field(default_factory=lambda: deque(maxlen=48))

    vol_std: float = 0
    vol_mean: float = 0

    bubble_size: float = 0
    norm_vol: float = 0

    # --- MF-WILL / Godmode ---
    ttsi_prev: float = None
    tci_prev: float = None
    mf_prev: float = None
    willy_prev: float = None
    gm_prev: float = None

    prev_close: float = None

    # --- Dynamic Pivot ---
    dyn_pivot: float = None
    upforce_queue: deque = field(default_factory=lambda: deque(maxlen=50))
    downforce_queue: deque = field(default_factory=lambda: deque(maxlen=50))

    # --- AVDBS ---
    prev_evwma: float = 0
    prev_cnv: float = 0
    prev_smooth_cnv: float = 0

    # ============================================================
    # Incremental update per single candle
    # ============================================================
    def update(self, candle):
        o = candle['open']
        h = candle['high']
        l = candle['low']
        c = candle['close']
        v = candle['volume']

        # ============================================================
        # 1. EMAs
        # ============================================================
        self.ema5 = ema_update(self.ema5, c, 5)
        self.ema9 = ema_update(self.ema9, c, 9)
        self.ema20 = ema_update(self.ema20, c, 20)
        self.ema200 = ema_update(self.ema200, c, 200)

        # ============================================================
        # 2. Candle metrics
        # ============================================================
        body = abs(c - o)
        total_range = max(h - l, 1e-12)
        self.body_size = body
        self.upper_shadow = h - max(o, c)
        self.lower_shadow = min(o, c) - l
        self.close_pos_pct = 100 * (c - l) / total_range

        # ============================================================
        # 3. Volume Bubble components
        # ============================================================
        self.vol_queue_long.append(v)
        self.vol_queue_short.append(v)
        self.vol_queue_std.append(v)

        long_avg = sum(self.vol_queue_long) / len(self.vol_queue_long)
        short_avg = sum(self.vol_queue_short) / len(self.vol_queue_short)
        avg_denom = (long_avg + short_avg) / 2

        self.vol_mean = sum(self.vol_queue_std) / len(self.vol_queue_std)
        std = math.sqrt(sum((x - self.vol_mean)**2 for x in self.vol_queue_std) / len(self.vol_queue_std))
        self.vol_std = std

        self.norm_vol = (v - self.vol_mean) / (std if std != 0 else 1)

        # bubble size
        if avg_denom != 0:
            b1 = round(v / avg_denom)
        else:
            b1 = 0
        self.bubble_size = b1

        # ============================================================
        # 4. MF-WILL / Godmode (simplified)
        # ============================================================
        if self.prev_close is not None:
            ch = c - self.prev_close
            ttsi = ema_update(self.ttsi_prev, ch, 9)
            tci = ema_update(self.tci_prev, ch, 9)
            mf = ema_update(self.mf_prev, ch, 13)
            willy = ema_update(self.willy_prev, c, 26)

            self.gm_prev = (ttsi + tci + mf + willy) / 4

            self.ttsi_prev = ttsi
            self.tci_prev = tci
            self.mf_prev = mf
            self.willy_prev = willy

        self.prev_close = c

        # ============================================================
        # 5. Dynamic Pivot (simple)
        # ============================================================
        force_up = max(0, c - o) * v
        force_down = max(0, o - c) * v
        self.upforce_queue.append(force_up)
        self.downforce_queue.append(force_down)
        net_force = sum(self.upforce_queue) - sum(self.downforce_queue)

        base_pivot = (h + l + c) / 3
        self.dyn_pivot = base_pivot + net_force * 1e-8

        # ============================================================
        # 6. AVDBS
        # ============================================================
        bull = v if c > o else 0
        bear = v if o > c else 0

        # EVWMA incremental
        fs = sum(self.vol_queue_std)
        if fs > 0:
            self.prev_evwma = (
                (self.prev_evwma * (fs - v)) + (v * c)
            ) / fs

        # Net volume
        if self.prev_close is not None:
            direction = 1 if c > self.prev_close else -1 if c < self.prev_close else 0
            cnv = self.prev_cnv + direction * v
            self.prev_cnv = cnv

            # smooth
            self.prev_smooth_cnv = ema_update(self.prev_smooth_cnv, cnv, 10)

        return self  # return updated state
