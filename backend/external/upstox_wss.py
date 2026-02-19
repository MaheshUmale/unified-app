
import logging
import json
import threading
import upstox_client
from upstox_client.feeder.market_data_streamer_v3 import MarketDataStreamerV3
from config import UPSTOX_ACCESS_TOKEN
from core.symbol_mapper import symbol_mapper

logger = logging.getLogger(__name__)

class UpstoxWSS:
    def __init__(self, callback):
        self.callback = callback
        self.streamer = None
        self.api_client = None
        self.is_running = False
        self.subscribed_keys = set()

    def start(self):
        if self.is_running: return
        try:
            configuration = upstox_client.Configuration()
            configuration.access_token = UPSTOX_ACCESS_TOKEN
            self.api_client = upstox_client.ApiClient(configuration)
            self.streamer = MarketDataStreamerV3(api_client=self.api_client, mode="full")
            self.streamer.on("open", self._on_open)
            self.streamer.on("message", self._on_message)
            self.streamer.on("error", self._on_error)
            self.streamer.on("close", self._on_close)
            self.streamer.connect()
            self.is_running = True
            logger.info("Upstox WSS Streamer started")
        except Exception as e:
            logger.error(f"Failed to start Upstox WSS: {e}")

    def stop(self):
        if self.streamer:
            if hasattr(self.streamer, 'feeder') and self.streamer.feeder.ws:
                self.streamer.feeder.ws.close()
        self.is_running = False
        logger.info("Upstox WSS Streamer stopped")

    def subscribe(self, symbols, interval="1"):
        if not symbols: return

        upstox_keys = []
        for s in symbols:
            k = symbol_mapper.to_upstox_key(s)
            if k: upstox_keys.append(k)

        new_keys = [k for k in upstox_keys if k not in self.subscribed_keys]

        if not new_keys:
            return

        self.subscribed_keys.update(new_keys)

        if self.is_running and self.streamer:
            try:
                # Check if websocket is actually connected before subscribing
                is_connected = False
                if hasattr(self.streamer, 'feeder') and self.streamer.feeder and hasattr(self.streamer.feeder, 'ws'):
                    ws = self.streamer.feeder.ws
                    if ws and hasattr(ws, 'sock') and ws.sock and ws.sock.connected:
                        is_connected = True

                if is_connected:
                    self.streamer.subscribe(new_keys, "full")
                    logger.info(f"Upstox WSS subscribed to: {new_keys}")
                else:
                    logger.info(f"Upstox WSS subscription for {len(new_keys)} keys queued (waiting for connection)")
            except Exception as e:
                logger.error(f"Error subscribing in Upstox WSS: {e}")

    def unsubscribe(self, symbol, interval="1"):
        upstox_key = symbol_mapper.to_upstox_key(symbol)
        if upstox_key in self.subscribed_keys and self.is_running:
            self.streamer.unsubscribe([upstox_key])
            self.subscribed_keys.remove(upstox_key)

    def _on_open(self):
        if self.subscribed_keys:
            self.streamer.subscribe(list(self.subscribed_keys), "full")

    def _on_message(self, data):
        try:
            feeds_map = data.get('feeds', {})
            if not feeds_map: return
            normalized_feeds = {}
            for u_key, tick in feeds_map.items():
                internal_key = symbol_mapper.from_upstox_key(u_key)
                feed_data = {}
                full_feed = tick.get('fullFeed')
                ltpc_feed = tick.get('ltpc')
                if full_feed:
                    market_pic = full_feed.get('marketPic', {})
                    feed_data = {'last_price': float(market_pic.get('ltp', 0)), 'ltq': int(market_pic.get('ltq', 0)), 'ts_ms': int(market_pic.get('ltt', 0)), 'upstox_volume': float(market_pic.get('vtt', 0))}
                elif ltpc_feed:
                    feed_data = {'last_price': float(ltpc_feed.get('ltp', 0)), 'ts_ms': int(ltpc_feed.get('ltt', 0))}
                if feed_data:
                    feed_data['source'] = 'upstox_wss'
                    normalized_feeds[internal_key] = feed_data
            if normalized_feeds:
                self.callback({'feeds': normalized_feeds})
        except Exception as e:
            logger.error(f"Error processing Upstox WSS message: {e}")

    def _on_error(self, error):
        logger.error(f"Upstox WSS Error: {error}")

    def _on_close(self, ws, close_status_code=None, close_msg=None):
        self.is_running = False
