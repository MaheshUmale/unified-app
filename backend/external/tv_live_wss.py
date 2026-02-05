import websocket
import json
import random
import string
import threading
import time
import logging
import re

logger = logging.getLogger(__name__)

class TradingViewWSS:
    def __init__(self, on_message_callback):
        self.callback = on_message_callback
        self.ws = None
        self.session = self._generate_session()
        self.quote_session = self._generate_session("qs_")
        self.symbols = []
        self.symbol_map = {
            'NSE:NIFTY': 'NIFTY',
            'NSE:BANKNIFTY': 'BANKNIFTY',
            'NSE:CNXFINANCE': 'FINNIFTY',
            'NSE:INDIAVIX': 'INDIA VIX'
        }
        self.last_volumes = {} # track cumulative volume per symbol
        self.stop_event = threading.Event()
        self.thread = None

    def _generate_session(self, prefix=""):
        return prefix + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(12))

    def _prepend_header(self, message):
        return f"~m~{len(message)}~m~{message}"

    def _construct_message(self, func, param_list):
        return json.dumps({"m": func, "p": param_list}, separators=(",", ":"))

    def _send_message(self, func, param_list):
        if not self.ws or not self.ws.sock or not self.ws.sock.connected:
            return
        message = self._construct_message(func, param_list)
        payload = self._prepend_header(message)
        try:
            self.ws.send(payload)
        except Exception as e:
            logger.error(f"Error sending message to TV WSS: {e}")

    def subscribe(self, symbols):
        new_symbols = [s for s in symbols if s not in self.symbols]
        self.symbols.extend(new_symbols)
        if self.ws and self.ws.sock and self.ws.sock.connected:
            self._subscribe_symbols(new_symbols)

    def _subscribe_symbols(self, symbols):
        if not symbols: return
        for symbol in symbols:
            self._send_message("quote_add_symbols", [self.quote_session, symbol, {"flags": ["force_permission"]}])
        logger.info(f"Subscribed to {len(symbols)} symbols on TV WSS")

    def on_open(self, ws):
        logger.info("TV WSS Connection opened")
        self._send_message("set_auth_token", ["unauthorized_user_token"])
        self._send_message("quote_create_session", [self.quote_session])
        self._send_message("quote_set_fields", [self.quote_session, "lp", "lp_time", "ch", "chp", "volume", "open_interest", "bid", "ask"])
        if self.symbols:
            self._subscribe_symbols(self.symbols)

    def on_message(self, ws, message):
        if isinstance(message, bytes):
            message = message.decode('utf-8')

        # Heartbeat check
        if "~h~" in message:
            try:
                ws.send(message)
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
            return

        # Split multiple messages in one frame
        messages = re.split(r"~m~\d+~m~", message)
        for msg in messages:
            if not msg: continue
            try:
                data = json.loads(msg)
                if data.get("m") == "qsd" and len(data["p"]) > 1:
                    quote_data = data["p"][1]
                    symbol = quote_data["n"]
                    logger.info(f"TV WSS Raw Symbol: {symbol}")
                    values = quote_data.get("v", {})

                    hrn = self.symbol_map.get(symbol, symbol)

                    if 'lp' in values:
                        ts_ms = int(values.get('lp_time', time.time()) * 1000)

                        # Update and track latest cumulative volume
                        new_vol = values.get('volume')
                        if new_vol is not None:
                            self.last_volumes[symbol] = float(new_vol)

                        current_cum_vol = self.last_volumes.get(symbol)

                        feed_msg = {
                            'type': 'live_feed',
                            'feeds': {
                                hrn: {
                                    'fullFeed': {
                                        'indexFF' if 'VIX' in hrn or 'NIFTY' in hrn and ' ' not in hrn else 'marketFF': {
                                            'ltpc': {
                                                'ltp': str(values['lp']),
                                                'ltt': str(ts_ms),
                                                'ltq': '0' # Delta logic will be handled in data_engine
                                            },
                                            'oi': str(values.get('open_interest', 0))
                                        }
                                    },
                                    'tv_volume': current_cum_vol,
                                    'source': 'tradingview_wss'
                                }
                            }
                        }
                        self.callback(feed_msg)
            except Exception as e:
                pass

    def on_error(self, ws, error):
        logger.error(f"TV WSS Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        logger.info(f"TV WSS Connection closed: {close_status_code} - {close_msg}")
        if not self.stop_event.is_set():
            logger.info("TV WSS reconnecting in 5 seconds...")
            time.sleep(5)
            self.start()

    def start(self):
        self.stop_event.clear()
        self.ws = websocket.WebSocketApp(
            "wss://data.tradingview.com/socket.io/websocket",
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.thread = threading.Thread(target=self.ws.run_forever, kwargs={"skip_utf8_validation": True}, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.ws:
            self.ws.close()

tv_wss = None

def start_tv_wss(on_message_callback, symbols=None):
    global tv_wss
    if tv_wss is None:
        tv_wss = TradingViewWSS(on_message_callback)
        if symbols:
            tv_wss.subscribe(symbols)
        tv_wss.start()
    return tv_wss
