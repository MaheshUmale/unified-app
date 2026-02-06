import websocket
import json
import random
import string
import threading
import time
import logging
import re
import requests
from config import TV_COOKIE
from core.symbol_mapper import symbol_mapper

logger = logging.getLogger(__name__)

class TradingViewWSS:
    def __init__(self, on_message_callback):
        self.callback = on_message_callback
        self.ws = None
        self.session = self._generate_session()
        self.quote_session = self._generate_session("qs_")
        self.chart_session = self._generate_session("cs_")
        self.series_id = "s1"
        self.study_id = "st1"
        self.current_chart_symbol = None
        self.symbols = []
        self.last_volumes = {} # track cumulative volume per symbol
        self.last_prices = {} # track latest price per symbol
        self.last_times = {} # track latest time per symbol
        self.history = {} # store historical OHLCV + Indicators per symbol
        self.indicator_metadata = {} # store plots for each study
        self.stop_event = threading.Event()
        self.thread = None

    def _generate_session(self, prefix=""):
        return prefix + "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(12))

    def _send_message(self, func, param_list):
        if not self.ws or not self.ws.sock or not self.ws.sock.connected:
            return
        try:
            message = json.dumps({"m": func, "p": param_list}, separators=(",", ":"))
            payload = f"~m~{len(message)}~m~{message}"
            self.ws.send(payload)
        except Exception as e:
            logger.error(f"Error sending message to TV WSS: {e}")

    def subscribe(self, symbols):
        symbols = [s.upper() for s in symbols]
        new_symbols = [s for s in symbols if s not in self.symbols]
        self.symbols.extend(new_symbols)
        if self.ws and self.ws.sock and self.ws.sock.connected:
            self._subscribe_symbols(new_symbols)
            # Switch chart to the latest requested symbol
            if symbols:
                self.resolve_symbol(symbols[-1])

    def _subscribe_symbols(self, symbols):
        if not symbols: return
        for symbol in symbols:
            # Simple symbol string for quote session is more stable
            self._send_message("quote_add_symbols", [self.quote_session, symbol])
        logger.info(f"Subscribed to {len(symbols)} symbols on TV WSS")

    def chart_create_session(self):
        self._send_message("chart_create_session", [self.chart_session, ""])

    def resolve_symbol(self, symbol):
        self.current_chart_symbol = symbol
        symbol_payload = f"={json.dumps({'symbol': symbol, 'adjustment': 'splits'})}"
        self._send_message("resolve_symbol", [self.chart_session, "sds_sym_1", symbol_payload])

    def create_series(self, timeframe="1", bars=300):
        # Standard parameters for create_series
        self._send_message("create_series", [self.chart_session, "sds_1", "s1", "sds_sym_1", timeframe, bars, ""])

    def create_study(self, study_id, metadata, custom_inputs=None):
        inputs = {"text": metadata["script"]}
        if "pineId" in metadata: inputs["pineId"] = metadata["pineId"]
        if "pineVersion" in metadata: inputs["pineVersion"] = metadata["pineVersion"]

        final_inputs = metadata.get("inputs", {}).copy()
        if custom_inputs:
            for k, v in custom_inputs.items():
                if k in final_inputs: final_inputs[k]["value"] = v

        for input_id, input_val in final_inputs.items():
            inputs[input_id] = {
                "v": input_val.get("value"),
                "f": input_val.get("isFake", False),
                "t": input_val.get("type")
            }

        indicator_type = "Script@tv-scripting-101!"
        if metadata.get("type") == "strategy":
            indicator_type = "StrategyScript@tv-scripting-101!"

        # Param order: [session, study_id, study_alias, series_id, type, inputs]
        self._send_message("create_study", [self.chart_session, study_id, study_id, "sds_1", indicator_type, inputs])

    def get_user_data(self):
        if not TV_COOKIE: return None
        url = "https://www.tradingview.com/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            res = requests.get(url, headers=headers, cookies=TV_COOKIE, timeout=15)
            # logger.info(res.text)
            auth_token = re.search(r'"auth_token":"(.*?)"', res.text)
            logger.info(f"auth TOKEN {auth_token.group(1) if auth_token else 'None'}")
            if auth_token: return auth_token.group(1)
        except Exception as e:
            logger.error(f"Error getting user data: {e}")
        return None

    def get_indicator_metadata(self, indicator_id, version="last"):
        url = f"https://pine-facade.tradingview.com/pine-facade/translate/{indicator_id}/{version}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        cookies = None
        if TV_COOKIE:
            try:
                # Basic session cookie parsing if it's a simple string
                cookies =  TV_COOKIE
            except: pass

        response = requests.get(url, headers=headers, cookies=cookies)
        try:
            data = response.json()
        except:
            logger.error(f"Failed to parse metadata JSON from {url}. Status: {response.status_code}, Body: {response.text[:100]}")
            raise Exception(f"Invalid JSON response from TradingView metadata API: {response.status_code}")

        if not isinstance(data, dict) or not data.get("success"):
            raise Exception(f"Failed to get indicator metadata: {data.get('reason') if isinstance(data, dict) else 'Unknown error'}")

        result = data.get("result", {})
        metaInfo = result.get("metaInfo", {})

        inputs = {}
        for item in metaInfo.get("inputs", []):
            if item.get("id") in ["text", "pineId", "pineVersion"]: continue
            inputs[item["id"]] = {"name": item.get("name"), "type": item.get("type"), "value": item.get("defval"), "isFake": item.get("isFake", False)}

        plots = {}
        # Use plots metaInfo to get all plot IDs and their types
        plots_meta = metaInfo.get("plots", [])
        styles = metaInfo.get("styles", {})

        for i, p in enumerate(plots_meta):
            plot_id = p.get("id")
            style = styles.get(plot_id, {})
            title = style.get("title", plot_id).replace(" ", "_")
            # Ensure title is unique within this study
            if title in [p["title"] for p in plots.values()]:
                title = f"{title}_{plot_id}"

            plots[plot_id] = {
                "id": plot_id,
                "index": i,
                "title": title,
                "type": style.get("plottype"),
                "color": style.get("color"),
                "linewidth": style.get("linewidth", 1),
                "linestyle": style.get("linestyle", 0)
            }

        return {
            "pineId": metaInfo.get("scriptIdPart", indicator_id),
            "pineVersion": metaInfo.get("pine", {}).get("version", version),
            "inputs": inputs, "plots": plots, "script": result.get("ilTemplate"),
            "type": metaInfo.get("extra", {}).get("kind") or metaInfo.get("package", {}).get("type") or "study"
        }

    def on_open(self, ws):
        logger.info("TV WSS Connection opened")
        token = self.get_user_data() or "unauthorized_user_token"
        self._send_message("set_auth_token", [token])
        self._send_message("set_locale", ["en", "US"])

        # Quote session for all symbols
        self._send_message("quote_create_session", [self.quote_session])
        self._send_message("quote_set_fields", [self.quote_session, "lp", "lp_time", "volume"])

        # Chart session for the primary symbol
        self._send_message("chart_create_session", [self.chart_session, ""])

        if self.symbols:
            self._subscribe_symbols(self.symbols)
            # Setup chart for first symbol
            self.resolve_symbol(self.symbols[0])
            self.create_series(timeframe="1", bars=300)
            from config import TV_STUDY_ID
            if TV_STUDY_ID:
                try:
                    meta = self.get_indicator_metadata(TV_STUDY_ID)
                    self.indicator_metadata[self.study_id] = meta
                    self.create_study(self.study_id, meta)
                    logger.info(f"Loaded study: {TV_STUDY_ID}")
                except Exception as e:
                    logger.error(f"Failed to load study {TV_STUDY_ID}: {e}")

    def on_message(self, ws, message):
        if isinstance(message, bytes):
            message = message.decode('utf-8')

        # Heartbeat check - TV WSS sends ~m~<len>~m~~h~<num>
        if "~h~" in message:
            try:
                ws.send(message)
            except Exception as e:
                logger.error(f"Error sending heartbeat: {e}")
            return

        # Split multiple messages in one frame
        # We use a more robust split to avoid missing data
        messages = re.split(r"~m~\d+~m~", message)
        for msg in messages:
            if not msg: continue
            try:
                data = json.loads(msg)
                m_type = data.get("m")
                p = data.get("p", [])

                # logger.debug(f"TV WSS Message: {m_type}")

                if m_type == "qsd" and len(p) > 1:
                    self._handle_qsd(p[1])
                elif m_type in ["timescale_update", "du"] and len(p) > 1:
                    self._handle_chart_update(p[1])
                elif m_type == "error":
                    logger.error(f"TV WSS Protocol Error: {p}")

            except Exception as e:
                pass

    def _handle_qsd(self, quote_data):
        symbol = quote_data["n"]
        clean_symbol = symbol[1:] if symbol.startswith('=') else symbol
        values = quote_data.get("v", {})

        # Update tracked values
        if 'lp' in values: self.last_prices[clean_symbol] = values['lp']
        if 'last_price' in values: self.last_prices[clean_symbol] = values['last_price']
        if 'lp_time' in values: self.last_times[clean_symbol] = values['lp_time']
        if 'volume' in values: self.last_volumes[clean_symbol] = float(values['volume'])

        hrn = symbol_mapper.get_hrn(clean_symbol)
        price = self.last_prices.get(clean_symbol)
        if price is not None:
            ts_ms = int(self.last_times.get(clean_symbol, time.time()) * 1000)
            current_cum_vol = self.last_volumes.get(clean_symbol)

            feed_msg = {
                'type': 'live_feed',
                'feeds': {
                    hrn: {
                        'last_price': float(price),
                        'ts_ms': ts_ms,
                        'tv_volume': current_cum_vol,
                        'oi': float(values.get('open_interest', 0)),
                        'source': 'tradingview_wss'
                    }
                }
            }
            self.callback(feed_msg)

    def _handle_chart_update(self, chart_data):
        # We only care about prices for now
        symbol = self.current_chart_symbol
        hrn = symbol_mapper.get_hrn(symbol) if symbol else None
        update_msg = {'type': 'chart_update', 'instrumentKey': hrn, 'data': {}}

        # OHLCV data
        if "$prices" in chart_data:
            prices = chart_data["$prices"].get("s", [])
            ohlcv = [item['v'] for item in prices]
            update_msg['data']['ohlcv'] = ohlcv

            if hrn and len(ohlcv) > 10:
                if hrn not in self.history: self.history[hrn] = {}
                self.history[hrn]['ohlcv'] = ohlcv

        # Study data
        if self.study_id in chart_data:
            study_val = chart_data[self.study_id]
            if "st" in study_val and study_val["st"]:
                plots_rows = [item["v"] for item in study_val["st"]]

                # Map plots if we have metadata
                meta = self.indicator_metadata.get(self.study_id)
                plot_data = plots_rows
                if meta and meta.get("plots"):
                    plot_defs = list(meta["plots"].values())
                    mapped_plots = []
                    # Check first row to see if response is interleaved: 1 (timestamp) + 2 * num_plots
                    is_interleaved = len(plots_rows[0]) >= (1 + 2 * len(plot_defs)) if plots_rows else False

                    for row in plots_rows:
                        mapped_row = {"timestamp": row[0]}
                        for p_def in plot_defs:
                            p_idx = p_def["index"]
                            val_idx = 1 + (2 * p_idx if is_interleaved else p_idx)

                            if val_idx < len(row):
                                mapped_row[p_def["title"]] = row[val_idx]
                                mapped_row[f"{p_def['title']}_meta"] = p_def
                                if is_interleaved:
                                    color_idx = val_idx + 1
                                    if color_idx < len(row):
                                        mapped_row[f"{p_def['title']}_color"] = row[color_idx]

                        mapped_plots.append(mapped_row)

                    # If study_val has 'ba' (bar colors), map them by index
                    if "ba" in study_val and study_val["ba"]:
                        for ba_item in study_val["ba"]:
                            ba_val = ba_item.get("v")
                            if isinstance(ba_val, list) and len(ba_val) > 1:
                                idx = ba_val[0]
                                if isinstance(idx, int) and 0 <= idx < len(mapped_plots):
                                    mapped_plots[idx]["Bar_Color"] = ba_val[1]

                    plot_data = mapped_plots

                update_msg['data']['indicators'] = plot_data
                if hrn and len(plot_data) > 10:
                    if hrn not in self.history: self.history[hrn] = {}
                    self.history[hrn]['indicators'] = plot_data

        if update_msg['data']:
            self.callback(update_msg)

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
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Origin": "https://www.tradingview.com"
        }
        self.ws = websocket.WebSocketApp(
            "wss://data.tradingview.com/socket.io/websocket?type=chart",
            header=headers,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.thread = threading.Thread(
            target=self.ws.run_forever,
            kwargs={
                "skip_utf8_validation": True,
                "ping_interval": 20,
                "ping_timeout": 10
            },
            daemon=True
        )
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

def get_tv_wss():
    return tv_wss
