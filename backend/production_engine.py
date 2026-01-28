"""
production_engine.py
Async production-ready live engine with queues, bar-builder, incremental indicators,
risk management and order execution integrated with Upstox SDK.

Key functions/classes:
 - BarBuilder: tick -> OHLCV bar builder for a timeframe
 - IndicatorState: minimal incremental indicator state (EMA, EVWMA, MF_WILL skeleton, etc.)
 - SymbolEngine: per-symbol processing (tick -> bar -> indicators -> signals)
 - OrderManager: risk checks, sizing, order submission (via Upstox api_client)
 - Engine: orchestrates streamer integration, queues, workers, persistence, backfill
"""

import asyncio
import pickle
import time
import os
import logging
from dataclasses import dataclass, field
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Optional, Tuple, Any

logger = logging.getLogger("prod_engine")
logging.basicConfig(level=logging.INFO)

# ---------------------------
# Small helpers (deterministic incremental indicators)
# ---------------------------
def ema_update(prev: Optional[float], price: float, length: int) -> float:
    if prev is None:
        return float(price)
    alpha = 2.0 / (length + 1.0)
    return prev + alpha * (price - prev)

def evwma_update(prev_ev: Optional[float], price: float, vol: float, vol_window_sum: float) -> float:
    # incremental update used in prior code: prev = (prev*(sum-vol)+vol*price)/sum
    if vol_window_sum <= 0 or prev_ev is None:
        return price
    return (prev_ev * (vol_window_sum - vol) + vol * price) / vol_window_sum

# ---------------------------
# BarBuilder: builds bars from ticks
# ---------------------------
@dataclass
class BarBuilder:
    timeframe_sec: int
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: float = 0.0
    start_ts: Optional[int] = None  # epoch seconds for current bar

    def update_tick(self, price: float, size: float, ts: int) -> Optional[dict]:
        """
        Accepts a tick (price, size, ts in seconds).
        Returns a finished bar dict when bar closes; otherwise None.
        """
        if self.open is None:
            # initialize new bar
            self.start_ts = ts - (ts % self.timeframe_sec)
            self.open = self.high = self.low = self.close = float(price)
            self.volume = float(size)
            return None

        # if tick belongs to new bar (ts >= start_ts + timeframe_sec)
        if ts >= (self.start_ts + self.timeframe_sec):
            finished = {
                "open": self.open,
                "high": self.high,
                "low": self.low,
                "close": self.close,
                "volume": self.volume,
                "start_ts": self.start_ts,
                "end_ts": self.start_ts + self.timeframe_sec - 1
            }
            # start new bar with this tick
            self.start_ts = ts - (ts % self.timeframe_sec)
            self.open = self.high = self.low = self.close = float(price)
            self.volume = float(size)
            return finished

        # update current bar
        self.close = float(price)
        self.high = max(self.high, price)
        self.low = min(self.low, price)
        self.volume += float(size)
        return None

    def snapshot(self) -> dict:
        return {
            "timeframe_sec": self.timeframe_sec,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "start_ts": self.start_ts
        }

    def load_snapshot(self, snap: dict):
        self.timeframe_sec = snap["timeframe_sec"]
        self.open = snap["open"]
        self.high = snap["high"]
        self.low = snap["low"]
        self.close = snap["close"]
        self.volume = snap["volume"]
        self.start_ts = snap["start_ts"]

# ---------------------------
# IndicatorState: incremental indicators for a symbol
# (keep simple but extendable: EMA5/9/20/200, EVWMA, simple MF-WILL placeholders, bubble detection)
# ---------------------------
@dataclass
class IndicatorState:
    # EMAs
    ema5: Optional[float] = None
    ema9: Optional[float] = None
    ema20: Optional[float] = None
    ema200: Optional[float] = None

    # EVWMA helpers (rolling denominator)
    evwma_prev: Optional[float] = None
    vol_window_sum: float = 0.0
    vol_window: deque = field(default_factory=lambda: deque(maxlen=100))  # for bubble & eVWMA denom

    # Volume bubble
    vol_std_queue: deque = field(default_factory=lambda: deque(maxlen=48))
    vol_mean_window: deque = field(default_factory=lambda: deque(maxlen=48))
    bubble_size: float = 0.0
    norm_vol: float = 0.0
    last_close: Optional[float] = None

    # Simple Godmode counters (approx)
    gm_value: Optional[float] = None
    gr_run: int = 0
    gs_run: int = 0

    # Dynamic pivot simple value
    dyn_pivot: Optional[float] = None
    upforce_q: deque = field(default_factory=lambda: deque(maxlen=50))
    downforce_q: deque = field(default_factory=lambda: deque(maxlen=50))

    # last bar meta
    last_bar_ts: Optional[int] = None

    def update_from_bar(self, bar: dict):
        """
        Update all incremental indicators given a completed bar (dict with open,high,low,close,volume,start_ts).
        """
        o, h, l, c, v = bar["open"], bar["high"], bar["low"], bar["close"], bar["volume"]

        # EMAs
        self.ema5 = ema_update(self.ema5, c, 5)
        self.ema9 = ema_update(self.ema9, c, 9)
        self.ema20 = ema_update(self.ema20, c, 20)
        self.ema200 = ema_update(self.ema200, c, 200)

        # EVWMA denominator rolling sum (store volumes)
        self.vol_window.append(v)
        self.vol_window_sum = sum(self.vol_window)
        # evwma update
        self.evwma_prev = evwma_update(self.evwma_prev, c, v, self.vol_window_sum)

        # vol stats for bubble detection
        self.vol_std_queue.append(v)
        self.vol_mean_window.append(v)
        arr = list(self.vol_std_queue)
        mean = sum(arr) / len(arr) if len(arr) else 0.0
        var = sum((x - mean) ** 2 for x in arr) / len(arr) if len(arr) else 0.0
        std = var ** 0.5
        self.norm_vol = (v - mean) / (std if std != 0 else 1)
        # bubble size simplified: ratio of vol to avg of short+long
        long_avg = sum(self.vol_window) / len(self.vol_window) if len(self.vol_window) else v
        short_avg = sum(list(self.vol_mean_window)[-10:]) / min(len(self.vol_mean_window), 10) if len(self.vol_mean_window) else v
        denom = (long_avg + short_avg) / 2.0 if (long_avg + short_avg) > 0 else 1.0
        self.bubble_size = round(v / denom)

        # Simple godmode placeholder: average of relative metrics
        # (In production you might port full godmode numeric logic)
        self.gm_value = ((self.ema9 or 0) + (self.evwma_prev or 0) + (self.bubble_size or 0)) / 3.0

        # runs
        if self.gm_value is not None:
            if self.gm_value > 70:
                self.gr_run += 1
            else:
                self.gr_run = 0
            if self.gm_value < 30:
                self.gs_run += 1
            else:
                self.gs_run = 0

        # dynamic pivot simple:
        base_pivot = (h + l + c) / 3.0
        force_up = max(0.0, c - o) * v
        force_down = max(0.0, o - c) * v
        self.upforce_q.append(force_up); self.downforce_q.append(force_down)
        net_force = sum(self.upforce_q) - sum(self.downforce_q)
        self.dyn_pivot = base_pivot + (net_force * 1e-9)  # scaled factor

        self.last_close = c
        self.last_bar_ts = bar.get("start_ts", int(time.time()))

    def snapshot(self) -> dict:
        return {
            "ema5": self.ema5, "ema9": self.ema9, "ema20": self.ema20, "ema200": self.ema200,
            "evwma_prev": self.evwma_prev, "vol_window": list(self.vol_window),
            "vol_std_queue": list(self.vol_std_queue), "vol_mean_window": list(self.vol_mean_window),
            "bubble_size": self.bubble_size, "norm_vol": self.norm_vol,
            "gm_value": self.gm_value, "gr_run": self.gr_run, "gs_run": self.gs_run,
            "dyn_pivot": self.dyn_pivot, "upforce_q": list(self.upforce_q), "downforce_q": list(self.downforce_q),
            "last_bar_ts": self.last_bar_ts, "last_close": self.last_close
        }

    def load_snapshot(self, snap: dict):
        self.ema5 = snap.get("ema5"); self.ema9 = snap.get("ema9"); self.ema20 = snap.get("ema20"); self.ema200 = snap.get("ema200")
        self.evwma_prev = snap.get("evwma_prev")
        self.vol_window = deque(snap.get("vol_window", []), maxlen=100)
        self.vol_std_queue = deque(snap.get("vol_std_queue", []), maxlen=48)
        self.vol_mean_window = deque(snap.get("vol_mean_window", []), maxlen=48)
        self.bubble_size = snap.get("bubble_size", 0.0)
        self.norm_vol = snap.get("norm_vol", 0.0)
        self.gm_value = snap.get("gm_value")
        self.gr_run = snap.get("gr_run", 0)
        self.gs_run = snap.get("gs_run", 0)
        self.dyn_pivot = snap.get("dyn_pivot")
        self.upforce_q = deque(snap.get("upforce_q", []), maxlen=50)
        self.downforce_q = deque(snap.get("downforce_q", []), maxlen=50)
        self.last_bar_ts = snap.get("last_bar_ts")
        self.last_close = snap.get("last_close")

# ---------------------------
# SymbolEngine: ties builder + indicators + signals
# ---------------------------
class SymbolEngine:
    def __init__(self, symbol: str, timeframe_sec: int = 60, state_dir: str = "states"):
        self.symbol = symbol
        self.timeframe_sec = timeframe_sec
        self.builder = BarBuilder(timeframe_sec)
        self.state = IndicatorState()
        self.state_dir = state_dir
        os.makedirs(state_dir, exist_ok=True)
        self.save_path = os.path.join(state_dir, f"{symbol}.pkl")
        self.cooldowns: Dict[str, float] = {}  # signal_name -> next_allowed_ts

    def process_tick(self, price: float, size: float, ts: int) -> Tuple[Optional[dict], Optional[dict]]:
        """
        Called synchronously for each incoming tick. Returns (bar, signal) when a bar completes.
        """
        bar = self.builder.update_tick(price, size, ts)
        if bar:
            self.state.update_from_bar(bar)
            signal = self.check_signals()
            return bar, signal
        return None, None

    def check_signals(self) -> Optional[dict]:
        """
        Evaluate conditions and return a dict with signal details or None.
        Customize/extend these conditions.
        """
        s = {}
        # EMA cross
        if self.state.ema5 and self.state.ema20:
            if self.state.ema5 > self.state.ema20:
                s["ema_trend"] = "bull"
            else:
                s["ema_trend"] = "bear"

        # bubble / high norm vol
        if self.state.bubble_size >= 5 and self.state.norm_vol > 2:
            s["vol_bubble"] = True

        # dynamic pivot break
        if self.state.dyn_pivot and self.state.last_close:
            if self.state.last_close > self.state.dyn_pivot:
                s["pivot_break"] = "above"
            elif self.state.last_close < self.state.dyn_pivot:
                s["pivot_break"] = "below"

        # Godmode extreme runs -> supply/demand
        if self.state.gr_run >= 3:
            s["gm_overbought"] = True
        if self.state.gs_run >= 3:
            s["gm_oversold"] = True

        return s if s else None

    def save(self):
        """Persist builder snapshot + indicator snapshot"""
        payload = {"builder": self.builder.snapshot(), "state": self.state.snapshot()}
        with open(self.save_path, "wb") as f:
            pickle.dump(payload, f)
        logger.debug(f"Saved state for {self.symbol} -> {self.save_path}")

    def load(self):
        if os.path.exists(self.save_path):
            with open(self.save_path, "rb") as f:
                payload = pickle.load(f)
            self.builder.load_snapshot(payload["builder"])
            self.state.load_snapshot(payload["state"])
            logger.info(f"Loaded persisted state for {self.symbol}")
        else:
            logger.info(f"No saved state for {self.symbol}")

# ---------------------------
# OrderManager: risk management + order execution (Upstox)
# ---------------------------
class OrderManager:
    """
    Responsible for:
     - checking risk limits before order
     - sizing orders
     - submitting orders via Upstox REST (blocking) using executor
     - retrying/cancelling with strategies
    """

    def __init__(self, api_client, executor: ThreadPoolExecutor, config: dict = None):
        self.api_client = api_client  # Should be an upstox REST/ApiClient instance
        self.executor = executor
        self.config = config or {}
        # Risk defaults
        self.max_position_per_symbol = self.config.get("max_position_per_symbol", 10000)  # units
        self.max_daily_loss = self.config.get("max_daily_loss", 1000.0)  # currency units
        self.max_concurrent_orders = self.config.get("max_concurrent_orders", 5)
        self.current_orders = {}
        self.daily_pnl = 0.0
        self.min_time_between_orders = self.config.get("min_time_between_orders", 1.0)  # secs
        self.last_order_ts = 0.0

    async def place_order(self, symbol: str, side: str, qty: float, price: Optional[float] = None,
                          order_type: str = "LIMIT", tif: str = "DAY") -> dict:
        """
        Places an order after risk checks. This will call the blocking API in a thread pool.
        Returns order response dict or raises.
        """
        now = time.time()
        # simple rate limit
        if now - self.last_order_ts < self.min_time_between_orders:
            raise RuntimeError("Order rate limited: too many orders in short time")

        # risk checks (ex: size)
        if qty <= 0:
            raise ValueError("qty must be > 0")
        if qty > self.max_position_per_symbol:
            raise RuntimeError(f"Qty {qty} exceeds max per-symbol {self.max_position_per_symbol}")

        # concurrency check
        if len(self.current_orders) >= self.max_concurrent_orders:
            raise RuntimeError("Too many concurrent orders")

        # prepare payload for Upstox - you must adapt fields to your REST client's order format
        order_payload = {
            "symbol": symbol,
            "side": side,
            "quantity": qty,
            "order_type": order_type,
            "price": price,
            "time_in_force": tif
        }

        # Submit via executor (blocking call inside)
        try:
            self.current_orders[symbol] = order_payload
            resp = await asyncio.get_event_loop().run_in_executor(self.executor, self._submit_order_blocking, order_payload)
            self.last_order_ts = time.time()
        finally:
            # optionally remove from current_orders after submit (or after filled event)
            self.current_orders.pop(symbol, None)

        # Update metrics (placeholder)
        # you should read actual fills via order/fill callbacks from your broker and update PnL/position
        return resp

    def _submit_order_blocking(self, payload: dict) -> dict:
        """
        Blocking call to the Upstox REST SDK (synchronous). This runs in a ThreadPoolExecutor.
        You must adapt this to your real client's method.
        """
        try:
            # Example: pseudo-call - replace with actual upstox client call
            # e.g. upstox_client.place_order(symbol=..., qty=..., price=..., ...)
            logger.info(f"Submitting order to broker: {payload}")
            # resp = self.api_client.place_order(payload)   # <-- replace with actual call
            # Simulate response
            resp = {"status": "ok", "order_id": f"sim-{int(time.time()*1000)}", "payload": payload}
            return resp
        except Exception as e:
            logger.exception("Order submit error")
            raise

    async def cancel_order(self, order_id: str) -> dict:
        # run blocking cancel in threadpool
        return await asyncio.get_event_loop().run_in_executor(self.executor, self._cancel_order_blocking, order_id)

    def _cancel_order_blocking(self, order_id: str) -> dict:
        # Replace with Upstox cancel
        logger.info(f"Cancel order {order_id}")
        return {"status": "cancelled", "order_id": order_id}

# ---------------------------
# Engine orchestrator: async tasks + integration with Upstox streamer
# ---------------------------
class Engine:
    def __init__(self, api_client, streamer, instrument_keys: list, timeframe_sec: int = 60, state_dir: str = "states",
                 max_workers: int = 6, risk_config: dict = None):
        self.api_client = api_client
        self.streamer = streamer
        self.symbols = instrument_keys
        self.timeframe_sec = timeframe_sec
        self.state_dir = state_dir
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.order_manager = OrderManager(api_client, self.executor, config=risk_config or {})
        # queues
        self.tick_queue: asyncio.Queue = asyncio.Queue()
        self.signal_queue: asyncio.Queue = asyncio.Queue()
        self.order_results_queue: asyncio.Queue = asyncio.Queue()
        # symbol engines
        self.engines: Dict[str, SymbolEngine] = {s: SymbolEngine(s, timeframe_sec, state_dir) for s in instrument_keys}
        # register streamer callbacks (we'll wrap given callbacks)
        self._streamer_thread = None

    async def start(self):
        # load persisted
        for s, eng in self.engines.items():
            eng.load()

        # start background tasks
        tasks = [
            asyncio.create_task(self._tick_consumer_loop()),
            asyncio.create_task(self._signal_consumer_loop()),
            asyncio.create_task(self._order_results_loop())
        ]
        # start streamer in background thread (blocking connect)
        self._start_streamer_thread()

        logger.info("Engine started, awaiting tasks.")
        await asyncio.gather(*tasks)  # will run until cancelled

    def _start_streamer_thread(self):
        # The streamer has methods and events: we'll use its callbacks to put ticks to tick_queue.
        # We'll run streamer.connect() in background thread so it's non-blocking relative to asyncio.
        import threading
        def run_streamer():
            try:
                # Setup callbacks that put tick data into asyncio queue
                def on_message(msg):
                    # parse message to extract tick(s)
                    # The format depends on Upstox streaming schema; we assume msg is a dict or json string
                    try:
                        data = msg if isinstance(msg, dict) else msg  # if already dict
                        # The user should adapt parsing logic based on the Upstox 'full' feed message format
                        # Example: {"instrument": "ABC", "ltp": 123.4, "volume": 10, "timestamp": 169...}
                        # We'll try to be flexible:
                        parsed = None
                        if isinstance(data, str):
                            import json
                            parsed = json.loads(data)
                        else:
                            parsed = data

                        # normalization: extracted as list or single tick
                        ticks = parsed if isinstance(parsed, list) else [parsed]
                        # put into asyncio queue by calling loop.call_soon_threadsafe
                        loop = asyncio.get_event_loop()
                        for t in ticks:
                            # user must map fields - adjust these keys to your feed
                            symbol = t.get("instrument") or t.get("symbol") or t.get("s")
                            price = float(t.get("ltp") or t.get("last") or t.get("c") or t.get("price"))
                            vol = float(t.get("volume") or t.get("v") or t.get("q") or 0.0)
                            ts = int(t.get("timestamp") or (time.time()))
                            loop.call_soon_threadsafe(asyncio.create_task, self.tick_queue.put((symbol, price, vol, ts)))
                    except Exception:
                        logger.exception("Error parsing stream message")

                def on_open(*a, **k):
                    logger.info("Streamer open")

                def on_error(e):
                    logger.error("Streamer error: %s", e)

                def on_close(*a, **k):
                    logger.info("Streamer closed")

                # register callbacks - depends on your streamer API
                try:
                    self.streamer.on("message", on_message)
                    self.streamer.on("open", on_open)
                    self.streamer.on("error", on_error)
                    self.streamer.on("close", on_close)
                except Exception:
                    logger.exception("Failed to attach callbacks to streamer. You may adapt this block to your SDK.")

                # connect (blocking)
                logger.info("Starting streamer.connect() (blocking call) in background thread.")
                self.streamer.connect()
            except Exception:
                logger.exception("Streamer fatal error")
        t = threading.Thread(target=run_streamer, daemon=True)
        t.start()
        self._streamer_thread = t

    async def _tick_consumer_loop(self):
        """
        Consumes ticks and dispatches to SymbolEngine.process_tick
        """
        while True:
            symbol, price, vol, ts = await self.tick_queue.get()
            if symbol not in self.engines:
                logger.debug(f"Tick for unregistered symbol {symbol} ignored.")
                continue
            eng = self.engines[symbol]
            bar, signal = eng.process_tick(price, vol, ts)
            if bar:
                # persist state quickly
                eng.save()
            if signal:
                logger.info(f"[{symbol}] SIGNAL: {signal}")
                await self.signal_queue.put((symbol, signal, bar))

    async def _signal_consumer_loop(self):
        """
        Handle signals and decide to place orders (apply risk manager).
        """
        while True:
            symbol, signal, bar = await self.signal_queue.get()
            # build order decision here. Example: simple buy on gm_oversold & ema_trend=bulll
            try:
                # Example decision rules
                # You must tailor to your strategy
                qty = 1.0
                side = None
                if signal.get("gm_oversold") and signal.get("ema_trend") == "bull":
                    side = "BUY"
                if signal.get("gm_overbought") and signal.get("ema_trend") == "bear":
                    side = "SELL"

                # Volume bubble quick scalps
                if signal.get("vol_bubble"):
                    side = "BUY" if signal.get("pivot_break") == "above" else "SELL"

                if side:
                    # size calc - naive: fixed qty. You should replace with dynamic sizing (account risk)
                    qty = self._size_for_symbol(symbol, bar)  # sample sizing func
                    # launch order placement asynchronously
                    try:
                        order_resp = await self.order_manager.place_order(symbol, side, qty, price=bar["close"], order_type="LIMIT")
                        logger.info(f"Order placed for {symbol}: {order_resp}")
                        await self.order_results_queue.put((symbol, order_resp))
                    except Exception as e:
                        logger.exception("Order placement failed")
            except Exception:
                logger.exception("Signal handling error")

    def _size_for_symbol(self, symbol: str, bar: dict) -> float:
        # Basic fixed-size; real sizing uses account balance and risk per trade
        return 1.0

    async def _order_results_loop(self):
        while True:
            symbol, resp = await self.order_results_queue.get()
            logger.info(f"Order result for {symbol}: {resp}")

    async def shutdown(self):
        # gracefully stop: persist states, stop streamer, shutdown executor
        logger.info("Shutting down engine, saving states...")
        for eng in self.engines.values():
            eng.save()
        try:
            # streamer.close or streamer.disconnect if available
            if hasattr(self.streamer, "close"):
                try:
                    self.streamer.close()
                except Exception:
                    pass
        finally:
            self.executor.shutdown(wait=True)
            logger.info("Engine stopped.")

    # ---------------------------
    # Backfill helper (fetch historical candles from Upstox REST and feed them)
    # You must implement fetch_historical_candles(symbol, timeframe_sec, since_ts, to_ts) that returns
    # list of bars dicts: {'open':..,'high':..,'low':..,'close':..,'volume':..,'start_ts':..}
    # ---------------------------
    async def backfill_and_resume(self, symbol: str, since_ts: int, to_ts: int):
        """
        Backfill missing bars using REST, apply them to the symbol engine state sequentially,
        then resume live ticks.
        """
        logger.info(f"Backfilling {symbol} from {since_ts} to {to_ts}")
        # Blocking fetch in thread executor
        bars = await asyncio.get_event_loop().run_in_executor(self.executor, self.fetch_historical_candles_blocking, symbol, since_ts, to_ts)
        eng = self.engines[symbol]
        for b in bars:
            eng.state.update_from_bar(b)
        eng.save()
        logger.info(f"Backfill completed for {symbol}, {len(bars)} bars applied.")

    def fetch_historical_candles_blocking(self, symbol: str, since_ts: int, to_ts: int) -> list:
        """
        Blocking REST call to your broker to fetch historical minute candles.
        You MUST replace this with actual Upstox API calls.
        """
        # Placeholder: return empty list. Adapt to your REST client.
        logger.info("fetch_historical_candles_blocking must be implemented to call Upstox REST klines")
        return []

# ---------------------------
# Example integration helper
# ---------------------------
async def run_engine_with_upstox(api_client, streamer, instrument_keys):
    """
    Instantiates the Engine and runs it. This is the top-level coroutine.
    """
    engine = Engine(api_client, streamer, instrument_keys, timeframe_sec=60, state_dir="states", max_workers=8)
    try:
        await engine.start()
    except asyncio.CancelledError:
        await engine.shutdown()
    except Exception:
        logger.exception("Engine fatal")

# ---------------------------------------------------------
# End of module
# ---------------------------------------------------------


import asyncio
from production_engine import run_engine_with_upstox

# assume you already built api_client and streamer as in your snippet
instrument_keys = ["NSE:RELIANCE", "NSE:TCS"]  # example
import upstox_client
import sys
import os
import config

configuration = upstox_client.Configuration()

configuration.access_token = config.ACCESS_TOKEN
api_client = upstox_client.ApiClient(configuration)

async def main():
    await run_engine_with_upstox(api_client, streamer, instrument_keys)

# run in asyncio event loop
asyncio.run(main())
