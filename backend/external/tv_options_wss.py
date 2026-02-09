import websocket
import json
import threading
import time
import logging
import re
from datetime import datetime
from config import TV_COOKIE

logger = logging.getLogger(__name__)

class OptionsWSS:
    def __init__(self, underlying: str, on_data_callback):
        self.underlying = underlying.upper().replace(':', '-') # e.g. NSE-NIFTY
        if ':' in underlying:
             self.underlying = underlying.split(':')[-1]
             # For options chain, TV uses format like NSE-NIFTY
             # But the user provided options%2Fchain%2FNSE-BANKNIFTY%2F
             # So it is NSE-BANKNIFTY
             prefix = underlying.split(':')[0]
             self.underlying = f"{prefix}-{self.underlying}"

        self.callback = on_data_callback
        self.ws = None
        self.stop_event = threading.Event()
        self.thread = None

    def _get_url(self):
        now_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        session_id = TV_COOKIE.get('sessionid', '')
        # Base URL from user
        url = f"wss://data.tradingview.com/socket.io/websocket?from=options/chain/{self.underlying}/&date={now_iso}&auth={session_id}"
        return url

    def start(self):
        url = self._get_url()
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Origin": "https://www.tradingview.com"
        }
        self.ws = websocket.WebSocketApp(
            url,
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.thread.start()
        logger.info(f"Options WSS started for {self.underlying}")

    def stop(self):
        self.stop_event.set()
        if self.ws:
            self.ws.close()

    def on_open(self, ws):
        logger.info(f"Options WSS Connection opened for {self.underlying}")

    def on_message(self, ws, message):
        # Handle heartbeat and data
        if message.startswith("~h~"):
            ws.send(f"~m~{len(message)}~m~{message}")
            return

        try:
            # TV WSS messages usually start with ~m~length~m~
            payloads = re.split(r"~m~\d+~m~", message)
            for p in payloads:
                if not p: continue
                data = json.loads(p)
                # Process options chain data
                # Typically it contains updates to the chain
                self.callback(data)
        except Exception as e:
            logger.error(f"Error in Options WSS message handling: {e}")

    def on_error(self, ws, error):
        logger.error(f"Options WSS Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        logger.info(f"Options WSS Closed: {close_status_code} {close_msg}")
