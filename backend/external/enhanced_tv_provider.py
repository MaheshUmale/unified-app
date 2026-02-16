import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from core.interfaces import ILiveStreamProvider, IHistoricalDataProvider
import sys
from pathlib import Path

# Add project root to path for tradingview module
root_path = Path(__file__).parent.parent.parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

from tradingview.enhanced_client import EnhancedTradingViewClient, ConnectionState

logger = logging.getLogger(__name__)

class EnhancedTradingViewProvider(ILiveStreamProvider, IHistoricalDataProvider):
    """
    Enhanced TradingView Provider using the new integrated module.
    Conforms to ILiveStreamProvider and IHistoricalDataProvider.
    """
    def __init__(self, callback: Callable = None):
        self.client = EnhancedTradingViewClient()
        self.callbacks = set()
        if callback:
            self.callbacks.add(callback)
        self.manager = None # Optional: EnhancedTradingViewManager
        self._is_started = False
        self._subscriptions = {} # symbol -> interval
        self._active_sessions = {} # symbol -> chart_session
        self._lock = asyncio.Lock()
        self._subscribing_keys = set() # (symbol, interval)

    def set_manager(self, manager):
        """Link the enterprise-grade TradingView manager."""
        self.manager = manager
        logger.info("Enhanced TV Provider linked to enterprise manager")

    def set_callback(self, callback: Callable[[Dict[str, Any]], None]):
        self.callbacks.add(callback)

    def start(self):
        if self._is_started:
            return
        asyncio.create_task(self._run_client())
        self._is_started = True

    async def _run_client(self):
        success = await self.client.connect()
        if success:
            logger.info("Enhanced TV Provider client connected. Waiting for stability...")
            await asyncio.sleep(2.0) # Wait for connection stability
            # Re-subscribe existing
            for key, interval in self._subscriptions.items():
                symbol, _ = key
                await self._subscribe_internal(symbol, interval)
        else:
            logger.error("Enhanced TV Provider client failed to connect")

    def stop(self):
        if self.client:
            asyncio.create_task(self.client.disconnect())
        self._is_started = False

    def is_connected(self) -> bool:
        return self.client.is_connected

    def _map_symbol(self, symbol: str) -> str:
        """Maps internal symbol names to TradingView compatible symbols."""
        if not symbol:
            return ""
        s = symbol.upper()
        mapping = {
            'NSE:CNXFINANCE': 'NSE:CNXFINANCE',
            'CNXFINANCE': 'NSE:CNXFINANCE',
            'NSE:NIFTY': 'NSE:NIFTY',
            'NSE:BANKNIFTY': 'NSE:BANKNIFTY',
            'NSE:INDIAVIX': 'NSE:INDIAVIX',
            'NSE:INDIA VIX': 'NSE:INDIAVIX',
            'BTCUSD': 'BITSTAMP:BTCUSD',
            'COINBASE:BTCUSD': 'COINBASE:BTCUSD'
        }
        mapped = mapping.get(s, symbol)
        if mapped != symbol:
            logger.debug(f"Mapped symbol {symbol} -> {mapped}")
        return mapped

    def subscribe(self, symbols: List[str], interval: str = "1"):
        for symbol in symbols:
            key = (symbol, str(interval))
            self._subscriptions[key] = interval
            if self.is_connected:
                asyncio.create_task(self._subscribe_internal(symbol, interval))

    async def _subscribe_internal(self, symbol: str, interval: str):
        key = (symbol, str(interval))

        async with self._lock:
            if key in self._subscribing_keys:
                logger.debug(f"Already subscribing to {symbol} ({interval}m), skipping duplicate request")
                return
            self._subscribing_keys.add(key)

        try:
            if key in self._active_sessions:
                try:
                    # Async delete to avoid blocking
                    await self._active_sessions[key].remove()
                    del self._active_sessions[key]
                except Exception as e:
                    logger.debug(f"Error deleting old session for {symbol} ({interval}m): {e}")

            tv_symbol = self._map_symbol(symbol)
            logger.info(f"Enhanced TV Provider subscribing to {symbol} (TV: {tv_symbol}, TF: {interval})")

            chart = self.client.Session.Chart()
            self._active_sessions[key] = chart

            # Wait for market loading
            await chart.set_market(tv_symbol, {'timeframe': interval})

            def on_update(*args):
                try:
                    latest = chart.last_period
                    if latest and self.callbacks:
                        data = {
                            'feeds': {
                                symbol: {
                                    'last_price': latest.close,
                                    'tv_volume': latest.volume,
                                    'ts_ms': int(latest.time * 1000),
                                    'source': 'enhanced_tv'
                                }
                            }
                        }
                        for cb in list(self.callbacks):
                            try:
                                cb(data)
                            except Exception as e:
                                logger.error(f"Error in Enhanced TV callback: {e}")
                except Exception as e:
                    logger.error(f"Error in Enhanced TV on_update for {symbol}: {e}")

            chart.on_update(on_update)
            logger.info(f"✅ Enhanced TV Provider subscription active for {symbol}")
        except Exception as e:
            logger.error(f"❌ Error in Enhanced TV Provider subscription for {symbol} ({interval}m): {e}")
            if key in self._active_sessions:
                del self._active_sessions[key]
        finally:
            async with self._lock:
                if key in self._subscribing_keys:
                    self._subscribing_keys.remove(key)

    def unsubscribe(self, symbol: str, interval: str = "1"):
        key = (symbol, str(interval))
        if key in self._subscriptions:
            del self._subscriptions[key]

        if key in self._active_sessions:
            logger.info(f"Enhanced TV Provider unsubscribing from {symbol} ({interval}m)")
            try:
                self._active_sessions[key].delete()
                del self._active_sessions[key]
            except Exception as e:
                logger.error(f"Error deleting session for {symbol} ({interval}m): {e}")

    async def get_hist_candles(self, symbol: str, interval: str, count: int) -> List[List]:
        """Fetch historical candles using the manager or enhanced client."""
        tv_symbol = self._map_symbol(symbol)

        # 1. Try via manager (preferred for caching/reliability)
        if self.manager:
            try:
                from tradingview.enhanced_tradingview_manager import DataQualityLevel
                market_data = await self.manager.get_historical_data(
                    tv_symbol, interval, count, DataQualityLevel.PRODUCTION
                )
                if market_data and market_data.data:
                    # Format: [ts, o, h, l, c, v]
                    # Robust access for both dict and object
                    res = []
                    for k in market_data.data:
                        try:
                            if isinstance(k, dict):
                                ts = k.get('timestamp') or k.get('time')
                                o, h, l, c = k.get('open'), k.get('high'), k.get('low'), k.get('close')
                                v = k.get('volume', 0)
                            else:
                                ts = getattr(k, 'timestamp', getattr(k, 'time', 0))
                                o = getattr(k, 'open', 0)
                                h = getattr(k, 'high', 0)
                                l = getattr(k, 'low', 0)
                                c = getattr(k, 'close', 0)
                                v = getattr(k, 'volume', 0)

                            if ts and ts > 0:
                                res.append([ts, o, h, l, c, v])
                        except: continue
                    return res
            except Exception as e:
                logger.warning(f"Manager hist fetch failed for {symbol}, falling back to raw client: {e}")

        # 2. Fallback to raw client
        chart = None
        try:
            if not self.is_connected:
                await self.client.connect()

            chart = self.client.Session.Chart()
            # ChartSession has a get_historical_data convenience method
            klines = await chart.get_historical_data(tv_symbol, interval, count)
            # Format: [ts, o, h, l, c, v]
            res = []
            for k in klines:
                try:
                    if isinstance(k, dict):
                        ts = k.get('timestamp') or k.get('time')
                        o, h, l, c = k.get('open'), k.get('high'), k.get('low'), k.get('close')
                        v = k.get('volume', 0)
                    else:
                        ts = getattr(k, 'timestamp', getattr(k, 'time', 0))
                        o = getattr(k, 'open', 0)
                        h = getattr(k, 'high', 0)
                        l = getattr(k, 'low', 0)
                        c = getattr(k, 'close', 0)
                        v = getattr(k, 'volume', 0)

                    if ts and ts > 0:
                        res.append([ts, o, h, l, c, v])
                except: continue
            return res
        except Exception as e:
            logger.error(f"Error fetching historical candles from Enhanced TV for {symbol}: {e}")
            return []
        finally:
            if chart:
                chart.delete()

    async def get_indicators(self, symbol: str, interval: str, indicator_id: str, options: Dict = None) -> List[Dict]:
        """
        Specialized method for the enhanced provider to get indicator data.
        Uses an event-driven approach to wait for data instead of hardcoded sleep.
        """
        chart = None
        try:
            tv_symbol = self._map_symbol(symbol)
            from tradingview import get_indicator
            ind = await get_indicator(indicator_id)
            if options:
                for k, v in options.items():
                    ind.set_option(k, v)

            chart = self.client.Session.Chart()
            # Wait for symbol loading and chart data
            chart.set_market(tv_symbol, {'timeframe': interval})
            study = chart.Study(ind)

            # Create an event to wait for the first data update
            data_event = asyncio.Event()

            def on_study_update(*args):
                if study.periods:
                    data_event.set()

            study.on_update(on_study_update)

            # Wait with a timeout
            try:
                await asyncio.wait_for(data_event.wait(), timeout=15.0)
                return [p.__dict__ for p in study.periods]
            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for indicator data: {indicator_id} for {symbol}")
                return [p.__dict__ for p in study.periods] if study.periods else []

        except Exception as e:
            logger.error(f"Error fetching indicators from Enhanced TV: {e}")
            return []
        finally:
            # Cleanup temporary session
            if chart:
                chart.delete()
