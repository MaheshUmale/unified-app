"""
Upstox WebSocket Feed Module (External API Access)
Handles connection to Upstox Market Data Feed V3 and subscription management.
"""
import threading
import logging
from datetime import datetime
from upstox_client import ApiClient, Configuration, MarketDataStreamerV3
from typing import List, Callable, Optional

logger = logging.getLogger(__name__)

class UpstoxFeed:
    def __init__(self, access_token: str, on_message_callback: Callable):
        self.access_token = access_token
        self.on_message = on_message_callback
        self.streamer: Optional[MarketDataStreamerV3] = None
        self.subscribed_instruments = set()

    def connect(self, initial_instruments: List[str]):
        """Starts the Upstox SDK MarketDataStreamerV3 in a background thread."""
        def run_streamer():
            self.subscribed_instruments.update(initial_instruments)
            logger.info(f"Starting UPSTOX SDK Streamer with {len(initial_instruments)} instruments...")

            configuration = Configuration()
            configuration.access_token = self.access_token

            try:
                api_client = ApiClient(configuration)
                self.streamer = MarketDataStreamerV3(api_client, list(self.subscribed_instruments), "full")
                self.streamer.on("message", self.on_message)
                self.streamer.on("open", lambda: logger.info("WebSocket Connected (SDK)!"))
                self.streamer.on("error", lambda e: logger.error(f"WebSocket Error: {e}"))
                self.streamer.on("close", lambda c, r: logger.info(f"WebSocket Closed: {c} - {r}"))
                self.streamer.auto_reconnect(True, 5, 5)
                self.streamer.connect()
            except Exception as e:
                logger.error(f"SDK Streamer Fatal Error: {e}")

        t = threading.Thread(target=run_streamer, daemon=True)
        t.start()
        return t

    def subscribe(self, instrument_key: str):
        """Dynamic subscription to an instrument."""
        if self.streamer:
            if instrument_key in self.subscribed_instruments:
                return
            logger.info(f"[SDK] Subscribing to {instrument_key}")
            try:
                self.subscribed_instruments.add(instrument_key)
                self.streamer.subscribe([instrument_key], "full")
            except Exception as e:
                logger.error(f"[SDK] Subscription Error: {e}")
        else:
            logger.warning("[SDK] Streamer not active, cannot subscribe.")

    def disconnect(self):
        """Disconnects the Upstox SDK MarketDataStreamerV3."""
        if self.streamer:
            try:
                logger.info("Disconnecting UPSTOX SDK Streamer...")
                self.streamer.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting streamer: {e}")
            finally:
                self.streamer = None

    def is_connected(self) -> bool:
        """Returns True if the streamer is active."""
        return self.streamer is not None
