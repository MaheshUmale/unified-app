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

        self.chart_sessions = {} # session_id -> {'hrn': hrn, 'interval': interval, 'symbol': symbol}
        self.symbol_interval_to_session = {} # (symbol, interval) -> session_id

        self.series_id = "s1"
        self.study_id = "st1"
        self.symbols = [] # For quote session
        self.last_volumes = {}
        self.last_prices = {}
        self.last_times = {}
        self.history = {} # (hrn, interval) -> data
        self.indicator_metadata = {}
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

    def subscribe(self, symbols, interval="1"):
        symbols = [s.upper() for s in symbols]
        new_symbols = [s for s in symbols if s not in self.symbols]
        self.symbols.extend(new_symbols)
        if self.ws and self.ws.sock and self.ws.sock.connected:
            if new_symbols:
                for symbol in new_symbols:
                    self._send_message("quote_add_symbols", [self.quote_session, symbol])

            for symbol in symbols:
                self.ensure_chart_session(symbol, interval)

    def ensure_chart_session(self, symbol, interval):
        key = (symbol, interval)
        if key in self.symbol_interval_to_session:
            return

        session_id = self._generate_session("cs_")
        self.symbol_interval_to_session[key] = session_id
        self.chart_sessions[session_id] = {'hrn': symbol_mapper.get_hrn(symbol), 'interval': interval, 'symbol': symbol}

        logger.info(f"Creating chart session {session_id} for {symbol} ({interval}m)")

        self._send_message("chart_create_session", [session_id, ""])

        symbol_payload = f"={json.dumps({'symbol': symbol, 'adjustment': 'splits'})}"
        self._send_message("resolve_symbol", [session_id, "sds_sym_1", symbol_payload])
        self._send_message("create_series", [session_id, "sds_1", "s1", "sds_sym_1", interval, 300, ""])

        from config import TV_STUDY_ID
        if TV_STUDY_ID:
            try:
                if TV_STUDY_ID not in self.indicator_metadata:
                    self.indicator_metadata[TV_STUDY_ID] = self.get_indicator_metadata(TV_STUDY_ID)

                meta_info = self.indicator_metadata[TV_STUDY_ID]
                self._create_study(session_id, self.study_id, "sds_1", meta_info)
            except Exception as e:
                logger.error(f"Failed to load study for {symbol}: {e}")

    def _create_study(self, session_id, study_id, series_id, metadata):
        inputs = {"text": metadata["script"]}
        if "pineId" in metadata: inputs["pineId"] = metadata["pineId"]
        if "pineVersion" in metadata: inputs["pineVersion"] = metadata["pineVersion"]
        for input_id, input_val in metadata.get("inputs", {}).items():
            inputs[input_id] = {"v": input_val.get("value"), "f": input_val.get("isFake", False), "t": input_val.get("type")}
        indicator_type = "Script@tv-scripting-101!"
        if metadata.get("type") == "strategy": indicator_type = "StrategyScript@tv-scripting-101!"
        self._send_message("create_study", [session_id, study_id, study_id, series_id, indicator_type, inputs])

    def get_user_data(self):
        if not TV_COOKIE: return None
        url = "https://www.tradingview.com/"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            res = requests.get(url, headers=headers, cookies=TV_COOKIE, timeout=15)
            auth_token = re.search(r'"auth_token":"(.*?)"', res.text)
            if auth_token: return auth_token.group(1)
        except Exception as e:
            logger.error(f"Error getting user data: {e}")
        return None

    def get_indicator_metadata(self, indicator_id, version="last"):
        url = f"https://pine-facade.tradingview.com/pine-facade/translate/{indicator_id}/{version}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        try:
            response = requests.get(url, headers=headers, cookies=TV_COOKIE, timeout=10)
            data = response.json()
        except Exception as e:
            logger.error(f"Error fetching indicator metadata: {e}")
            raise Exception(f"Failed to fetch indicator metadata: {e}")
        if not isinstance(data, dict) or not data.get("success"):
            raise Exception(f"Failed to get indicator metadata: {data.get('reason') if isinstance(data, dict) else 'Unknown error'}")
        result = data.get("result", {})
        metaInfo = result.get("metaInfo", {})
        inputs = {item["id"]: {"name": item.get("name"), "type": item.get("type"), "value": item.get("defval"), "isFake": item.get("isFake", False)} for item in metaInfo.get("inputs", []) if item.get("id") not in ["text", "pineId", "pineVersion"]}
        plots = {}
        styles = metaInfo.get("styles", {})
        for i, p in enumerate(metaInfo.get("plots", [])):
            plot_id = p.get("id")
            style = styles.get(plot_id, {})
            title = style.get("title", plot_id).replace(" ", "_")
            if title in [p["title"] for p in plots.values()]: title = f"{title}_{plot_id}"
            plots[plot_id] = {"id": plot_id, "index": i, "title": title, "type": style.get("plottype"), "color": style.get("color"), "linewidth": style.get("linewidth", 1), "linestyle": style.get("linestyle", 0)}
        return {"pineId": metaInfo.get("scriptIdPart", indicator_id), "pineVersion": metaInfo.get("pine", {}).get("version", version), "inputs": inputs, "plots": plots, "script": result.get("ilTemplate"), "type": metaInfo.get("extra", {}).get("kind") or metaInfo.get("package", {}).get("type") or "study"}

    def on_open(self, ws):
        logger.info("TV WSS Connection opened")
        token = self.get_user_data() or "unauthorized_user_token"
        self._send_message("set_auth_token", [token])
        self._send_message("set_locale", ["en", "US"])
        self._send_message("quote_create_session", [self.quote_session])
        self._send_message("quote_set_fields", [self.quote_session, "lp", "lp_time", "volume"])

        # We don't create a default chart session anymore, they are created per subscription.

    def on_message(self, ws, message):
        if isinstance(message, bytes): message = message.decode('utf-8')
        payloads = [p for p in re.split(r"~m~\d+~m~", message) if p]
        for msg in payloads:
            if msg.startswith("~h~"):
                try: ws.send(f"~m~{len(msg)}~m~{msg}")
                except: pass
                continue
            try:
                data = json.loads(msg)
                m_type = data.get("m")
                p = data.get("p", [])
                if m_type == "qsd" and len(p) > 1:
                    self._handle_qsd(p[1])
                elif m_type in ["timescale_update", "du"] and len(p) > 1:
                    logger.info(f"Chart update received for session {p[0]}")
                    self._handle_chart_update(p[0], p[1])
                elif m_type in ["error", "critical_error"]:
                    logger.error(f"TV WSS Protocol Error: {p}")
            except Exception as e:
                logger.error(f"Error handling TV WSS message: {e}")

    def _handle_qsd(self, quote_data):
        symbol = quote_data["n"]
        clean_symbol = symbol[1:] if symbol.startswith('=') else symbol
        values = quote_data.get("v", {})
        if 'lp' in values: self.last_prices[clean_symbol] = values['lp']
        if 'lp_time' in values: self.last_times[clean_symbol] = values['lp_time']
        if 'volume' in values: self.last_volumes[clean_symbol] = float(values['volume'])
        hrn = symbol_mapper.get_hrn(clean_symbol)
        price = self.last_prices.get(clean_symbol)
        if price is not None:
            ts_ms = int(self.last_times.get(clean_symbol, time.time()) * 1000)
            feed_msg = {'type': 'live_feed', 'feeds': {hrn: {'last_price': float(price), 'ts_ms': ts_ms, 'tv_volume': self.last_volumes.get(clean_symbol), 'oi': float(values.get('open_interest', 0)), 'source': 'tradingview_wss'}}}
            self.callback(feed_msg)

    def _map_tv_plot_type(self, tv_type):
        """Maps TradingView plot type integers to generic chart types."""
        mapping = {
            0: "line",
            1: "histogram",
            2: "line", # step
            3: "line",
            4: "histogram",
            5: "line", # circles
            6: "line", # cross
            7: "area",
            8: "area"
        }
        return mapping.get(tv_type, "line")

    def _handle_chart_update(self, session_id, chart_data):
        logger.info(f"Chart data keys for {session_id}: {list(chart_data.keys())}")
        meta = self.chart_sessions.get(session_id)
        if not meta: return

        hrn = meta['hrn']
        interval = meta['interval']
        update_msg = {'type': 'chart_update', 'instrumentKey': hrn, 'interval': interval, 'data': {}}

        series_key = "sds_1" if "sds_1" in chart_data else "$prices" if "$prices" in chart_data else None
        if series_key:
            prices = chart_data[series_key].get("s", [])
            ohlcv = [item['v'] for item in prices]
            update_msg['data']['ohlcv'] = ohlcv
            hist_key = (hrn, interval)
            if len(ohlcv) > 10:
                if hist_key not in self.history: self.history[hist_key] = {}
                self.history[hist_key]['ohlcv'] = ohlcv

        if self.study_id in chart_data:
            study_val = chart_data[self.study_id]
            if "st" in study_val and study_val["st"]:
                plots_rows = [item["v"] for item in study_val["st"]]
                from config import TV_STUDY_ID
                meta_info = self.indicator_metadata.get(TV_STUDY_ID)

                if meta_info and meta_info.get("plots"):
                    plot_defs = list(meta_info["plots"].values())
                    indicator_series = {}
                    for p_def in plot_defs:
                        p_id = p_def["id"]
                        indicator_series[p_id] = {
                            "id": p_id,
                            "title": p_def["title"],
                            "type": self._map_tv_plot_type(p_def.get("type")),
                            "style": {
                                "color": p_def.get("color"),
                                "lineWidth": p_def.get("linewidth", 1),
                                "lineStyle": p_def.get("linestyle", 0)
                            },
                            "data": []
                        }

                    is_interleaved = len(plots_rows[0]) >= (1 + 2 * len(plot_defs)) if plots_rows else False
                    for row in plots_rows:
                        timestamp = row[0]
                        for p_def in plot_defs:
                            p_idx = p_def["index"]
                            val_idx = 1 + (2 * p_idx if is_interleaved else p_idx)
                            if val_idx < len(row):
                                val = row[val_idx]
                                if val is not None:
                                    dp = {"time": timestamp, "value": val}
                                    if is_interleaved and (val_idx + 1) < len(row):
                                        dp["color"] = row[val_idx + 1]
                                    indicator_series[p_def["id"]]["data"].append(dp)

                    final_indicators = list(indicator_series.values())
                    update_msg['data']['indicators'] = final_indicators

                    # Bar coloring
                    if "ba" in study_val and study_val["ba"]:
                        bar_colors = []
                        for ba_item in study_val["ba"]:
                            v = ba_item.get("v")
                            if isinstance(v, list) and len(v) > 1:
                                idx = v[0]
                                color = v[1]
                                if 0 <= idx < len(plots_rows):
                                    bar_colors.append({"time": plots_rows[idx][0], "color": color})
                        update_msg['data']['bar_colors'] = bar_colors

                    hist_key = (hrn, interval)
                    if len(plots_rows) > 10:
                        if hist_key not in self.history: self.history[hist_key] = {}
                        self.history[hist_key]['indicators'] = final_indicators
                        if "bar_colors" in update_msg['data']:
                            self.history[hist_key]['bar_colors'] = update_msg['data']['bar_colors']

        if update_msg['data']:
            self.callback(update_msg)

    def start(self):
        self.stop_event.clear()
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Origin": "https://www.tradingview.com"}
        self.ws = websocket.WebSocketApp("wss://data.tradingview.com/socket.io/websocket?type=chart", header=headers, on_open=self.on_open, on_message=self.on_message, on_error=lambda ws,e: logger.error(f"TV WSS Error: {e}"), on_close=lambda ws,sc,msg: logger.info(f"TV WSS Closed: {sc} {msg}"))
        self.thread = threading.Thread(target=self.ws.run_forever, kwargs={"skip_utf8_validation": True, "ping_interval": 20, "ping_timeout": 10}, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.ws: self.ws.close()

tv_wss = None
def start_tv_wss(on_message_callback, symbols=None):
    global tv_wss
    if tv_wss is None:
        tv_wss = TradingViewWSS(on_message_callback)
        if symbols: tv_wss.subscribe(symbols)
        tv_wss.start()
    return tv_wss
def get_tv_wss(): return tv_wss
