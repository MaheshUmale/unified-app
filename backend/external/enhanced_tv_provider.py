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
        self.callback = callback
        self._is_started = False
        self._subscriptions = {} # symbol -> interval
        self._active_sessions = {} # symbol -> chart_session

    def set_callback(self, callback: Callable[[Dict[str, Any]], None]):
        self.callback = callback

    def start(self):
        if self._is_started:
            return
        asyncio.create_task(self._run_client())
        self._is_started = True

    async def _run_client(self):
        success = await self.client.connect()
        if success:
            logger.info("Enhanced TV Provider client connected")
            # Re-subscribe existing
            for symbol, interval in self._subscriptions.items():
                await self._subscribe_internal(symbol, interval)
        else:
            logger.error("Enhanced TV Provider client failed to connect")

    def stop(self):
        if self.client:
            asyncio.create_task(self.client.disconnect())
        self._is_started = False

    def is_connected(self) -> bool:
        return self.client.is_connected

    def subscribe(self, symbols: List[str], interval: str = "1"):
        for symbol in symbols:
            self._subscriptions[symbol] = interval
            if self.is_connected:
                asyncio.create_task(self._subscribe_internal(symbol, interval))

    async def _subscribe_internal(self, symbol: str, interval: str):
        try:
            if symbol in self._active_sessions:
                self._active_sessions[symbol].delete()

            chart = self.client.Session.Chart()
            self._active_sessions[symbol] = chart
            chart.set_market(symbol, {'timeframe': interval})

            def on_update():
                if chart.periods and self.callback:
                    latest = chart.periods[0]
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
                    self.callback(data)

            chart.on_update(on_update)
            logger.info(f"Enhanced TV Provider subscribed to {symbol} ({interval})")
        except Exception as e:
            logger.error(f"Error in Enhanced TV Provider subscription for {symbol}: {e}")

    def unsubscribe(self, symbol: str, interval: str = "1"):
        if symbol in self._subscriptions:
            del self._subscriptions[symbol]

        if symbol in self._active_sessions:
            logger.info(f"Enhanced TV Provider unsubscribing from {symbol}")
            try:
                self._active_sessions[symbol].delete()
                del self._active_sessions[symbol]
            except Exception as e:
                logger.error(f"Error deleting session for {symbol}: {e}")

    async def get_hist_candles(self, symbol: str, interval: str, count: int) -> List[List]:
        """Fetch historical candles using the enhanced client."""
        try:
            chart = self.client.Session.Chart()
            # ChartSession has a get_historical_data convenience method
            klines = await chart.get_historical_data(symbol, interval, count)
            # Format: [ts, o, h, l, c, v]
            return [[k['time'], k['open'], k['high'], k['low'], k['close'], k['volume']] for k in klines]
        except Exception as e:
            logger.error(f"Error fetching historical candles from Enhanced TV: {e}")
            return []

    async def get_indicators(self, symbol: str, interval: str, indicator_id: str, options: Dict = None) -> List[Dict]:
        """
        Specialized method for the enhanced provider to get indicator data.
        Uses an event-driven approach to wait for data instead of hardcoded sleep.
        """
        try:
            from tradingview import get_indicator
            ind = await get_indicator(indicator_id)
            if options:
                for k, v in options.items():
                    ind.set_option(k, v)

            chart = self.client.Session.Chart()
            chart.set_market(symbol, {'timeframe': interval})
            study = chart.Study(ind)

            # Create an event to wait for the first data update
            data_event = asyncio.Event()

            def on_study_update(*args):
                if study.periods:
                    data_event.set()

            study.on_update(on_study_update)

            # Wait with a timeout
            try:
                await asyncio.wait_for(data_event.wait(), timeout=10.0)
                return [p.__dict__ for p in study.periods]
            except asyncio.TimeoutError:
                logger.warning(f"Timeout waiting for indicator data: {indicator_id} for {symbol}")
                return [p.__dict__ for p in study.periods] if study.periods else []
            finally:
                # Cleanup temporary session
                chart.delete()

        except Exception as e:
            logger.error(f"Error fetching indicators from Enhanced TV: {e}")
            return []
