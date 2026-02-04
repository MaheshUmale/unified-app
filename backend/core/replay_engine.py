"""
ProTrade Replay Engine
Module for replaying historical market data from MongoDB as a synchronized stream.
"""
import asyncio
import logging
import threading
import time
import json
import traceback
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set
from db.local_db import db, LocalDBJSONEncoder
from core import data_engine
from core.symbol_mapper import symbol_mapper

logger = logging.getLogger(__name__)


class ReplayEngine:
    def __init__(self, emit_fn, db_dependencies: Dict[str, Any]):
        self.emit_fn = emit_fn
        self.is_running = False
        self.is_paused = False
        self.playback_speed = 1.0
        self.current_sim_time = None
        self.stop_event = threading.Event()
        self.replay_thread = None
        self.active_bars = {}

    def start_replay(self, date_str: str, instrument_keys: List[str], speed: float = 1.0):
        """Starts the replay process in a background thread."""
        if self.is_running:
            self.stop_replay()

        # Enable replay mode in data engine
        data_engine.replay_mode = True

        self.stop_event.clear()
        self.is_running = True
        self.is_paused = False
        self.playback_speed = speed

        self.replay_thread = threading.Thread(
            target=self._replay_loop,
            args=(date_str, instrument_keys),
            daemon=True
        )
        self.replay_thread.start()
        self.emit_fn('replay_status', {'active': True, 'date': date_str, 'paused': False, 'speed': speed, 'is_new': True})
        logger.info(f"Replay started for {date_str} with keys {instrument_keys} at speed {speed}x")

    def stop_replay(self):
        self.is_running = False
        data_engine.replay_mode = False
        data_engine.sim_time = None
        self.stop_event.set()
        if self.replay_thread:
            self.replay_thread.join(timeout=2)
        self.emit_fn('replay_status', {'active': False})
        logger.info("Replay stopped")

    def pause_replay(self):
        self.is_paused = True
        self.emit_fn('replay_status', {'active': True, 'paused': True})
        logger.info("Replay paused")

    def resume_replay(self):
        self.is_paused = False
        self.emit_fn('replay_status', {'active': True, 'paused': False})
        logger.info("Replay resumed")

    def set_speed(self, speed: float):
        self.playback_speed = speed
        self.emit_fn('replay_status', {'active': self.is_running, 'paused': self.is_paused, 'speed': speed})
        logger.info(f"Replay speed set to {speed}x")

    def _process_footprint(self, instrument_key: str, tick: Dict[str, Any]):
        try:
            ff = tick.get('fullFeed', {})
            # Support both Market and Index feed structures
            ltpc = ff.get('marketFF', {}).get('ltpc') or ff.get('indexFF', {}).get('ltpc')

            if not ltpc or not ltpc.get('ltp'): return

            raw_ltt = int(ltpc['ltt'])
            current_bar_ts = (raw_ltt // 60000) * 60000
            price = float(ltpc['ltp'])
            qty = int(ltpc.get('ltq', 0))

            if instrument_key not in self.active_bars:
                self.active_bars[instrument_key] = None

            bar = self.active_bars[instrument_key]

            if bar and current_bar_ts > bar['ts']:
                self.emit_fn('footprint_update', bar)
                self.active_bars[instrument_key] = None
                bar = None

            if not bar:
                bar = {
                    'ts': current_bar_ts,
                    'open': price, 'high': price, 'low': price, 'close': price,
                    'volume': 0, 'buy_volume': 0, 'sell_volume': 0,
                    'footprint': {}, 'instrument_token': instrument_key
                }
                self.active_bars[instrument_key] = bar

            bar['high'] = max(bar['high'], price)
            bar['low'] = min(bar['low'], price)
            bar['close'] = price
            bar['volume'] += qty

            bid_ask = ff.get('marketLevel', {}).get('bidAskQuote', [])
            side = 'buy' if any(price >= float(q.get('askP', 0)) for q in bid_ask) else \
                   'sell' if any(price <= float(q.get('bidP', 0)) for q in bid_ask) else 'unknown'

            p_str = f"{price:.2f}"
            if p_str not in bar['footprint']: bar['footprint'][p_str] = {'buy': 0, 'sell': 0}
            if side in ['buy', 'sell']:
                bar['footprint'][p_str][side] += qty
                bar[f"{side}_volume"] += qty

            self.emit_fn('footprint_update', bar)
        except Exception as e:
            logger.error(f"Error in replay footprint: {e}")

    def _replay_loop(self, date_str: str, instrument_keys: List[str]):
        """
        Replay loop. instrument_keys can be HRNs or raw keys.
        """
        try:
            # 1. Load data
            import pytz
            ist = pytz.timezone('Asia/Kolkata')
            start_dt = ist.localize(datetime.strptime(f"{date_str} 09:15:00", "%Y-%m-%d %H:%M:%S"))
            end_dt = ist.localize(datetime.strptime(f"{date_str} 15:30:00", "%Y-%m-%d %H:%M:%S"))
            start_ms = int(start_dt.timestamp() * 1000)
            end_ms = int(end_dt.timestamp() * 1000)

            logger.info(f"Replay Query: Range {start_ms} to {end_ms} for {instrument_keys}")

            search_keys = set(instrument_keys)
            for k in instrument_keys:
                raw = symbol_mapper.resolve_to_key(k)
                if raw: search_keys.add(raw)

            keys_str = ", ".join([f"'{k}'" for k in search_keys])

            # Optimized synchronized query for all instruments
            sql = f"""
                SELECT full_feed FROM ticks
                WHERE instrumentKey IN ({keys_str})
                AND ts_ms >= {start_ms} AND ts_ms <= {end_ms}
                ORDER BY ts_ms ASC
            """

            ticks_rows = db.query(sql)
            if not ticks_rows:
                logger.warning(f"No replay data found for {date_str}")
                self.emit_fn('replay_error', {'message': f"No data found for {date_str}"})
                self.emit_fn('replay_finished', {'date': date_str})
                self.is_running = False
                return

            logger.info(f"Streaming {len(ticks_rows)} ticks for replay")

            # Fetch OI data for the same day
            symbols = set()
            for key in instrument_keys:
                sym = symbol_mapper.get_symbol(key)
                if sym != "UNKNOWN": symbols.add(sym)

            syms_str = ", ".join([f"'{s}'" for s in symbols])
            oi_sql = f"SELECT CAST(date AS VARCHAR) as date_str, * FROM oi_data WHERE symbol IN ({syms_str}) AND date = '{date_str}' ORDER BY timestamp ASC"
            oi_records = db.query(oi_sql)
            oi_idx = 0

            last_tick_time = None

            for row in ticks_rows:
                tick = json.loads(row['full_feed'])
                if self.stop_event.is_set():
                    break

                while self.is_paused:
                    time.sleep(0.1)
                    if self.stop_event.is_set():
                        return

                ff = tick.get('fullFeed', {})
                ltpc = ff.get('marketFF', {}).get('ltpc') or ff.get('indexFF', {}).get('ltpc')

                if not ltpc: continue
                ltt = int(ltpc.get('ltt', 0))
                if not ltt: continue

                current_tick_time = ltt
                # Sync sim_time for strategy analysis
                data_engine.sim_time = datetime.fromtimestamp(ltt / 1000)

                # Sync with data_engine for strategy analysis
                inst_key = tick['instrumentKey'] # This is likely HRN in new DB
                raw_key = tick.get('raw_key', inst_key)
                ff = tick.get('fullFeed', {})
                market_ff = ff.get('marketFF', {})
                index_ff = ff.get('indexFF', {})
                ltpc = market_ff.get('ltpc') or index_ff.get('ltpc')

                if ltpc and ltpc.get('ltp'):
                    data_engine.latest_prices[raw_key] = float(ltpc['ltp'])
                    if "INDIA VIX" in inst_key.upper() or "India VIX" in raw_key:
                        data_engine.latest_vix['value'] = float(ltpc['ltp'])

                if 'oi' in market_ff:
                    data_engine.latest_oi[raw_key] = float(market_ff['oi'])

                if 'vtt' in market_ff:
                    data_engine.latest_vtt[raw_key] = float(market_ff['vtt'])

                market_levels = market_ff.get('marketLevel', {}).get('bidAskQuote', [])
                if market_levels:
                    top = market_levels[0]
                    data_engine.latest_bid_ask[raw_key] = {
                        'bid': float(top.get('bidP', 0)),
                        'ask': float(top.get('askP', 0))
                    }

                if 'iv' in market_ff:
                    data_engine.latest_iv[raw_key] = float(market_ff['iv'])

                if 'optionGreeks' in market_ff:
                    g = market_ff['optionGreeks']
                    data_engine.latest_greeks[raw_key] = {
                        'delta': float(g.get('delta', 0)),
                        'theta': float(g.get('theta', 0)),
                        'gamma': float(g.get('gamma', 0)),
                        'vega': float(g.get('vega', 0))
                    }

                # Populate sim_strike_data for strategy lookbacks during replay
                price = float(ltpc.get('ltp', 0))
                if price > 0:
                    oi = data_engine.latest_oi.get(raw_key, 0)
                    iv = data_engine.latest_iv.get(raw_key, 0)
                    greeks = data_engine.latest_greeks.get(raw_key, {})
                    data_engine.save_strike_metrics_to_db(inst_key, oi, price, iv, greeks)

                # Emit any OI updates that occurred before or at this tick time
                # OI timestamp in DB is "HH:MM", we need to convert to ms
                while oi_idx < len(oi_records):
                    oi_rec = oi_records[oi_idx]
                    oi_ts_str = f"{oi_rec['date_str']} {oi_rec['timestamp']}"
                    oi_dt = datetime.strptime(oi_ts_str, "%Y-%m-%d %H:%M")
                    oi_ms = int(oi_dt.timestamp() * 1000)

                    if oi_ms <= current_tick_time:
                        # Aligned OI update!
                        self.emit_fn('oi_update', {
                            'symbol': oi_rec['symbol'],
                            'call_oi': oi_rec.get('call_oi', 0),
                            'put_oi': oi_rec.get('put_oi', 0),
                            'pcr': round(oi_rec.get('put_oi', 0) / oi_rec.get('call_oi', 1), 2),
                            'timestamp': oi_rec['timestamp'],
                            'source': 'replay'
                        })
                        oi_idx += 1
                    else:
                        break

                # Emit the tick using HRN
                hrn = symbol_mapper.get_hrn(raw_key)
                feeds_map = {hrn: tick}
                self.emit_fn('raw_tick', json.dumps(feeds_map, cls=LocalDBJSONEncoder))

                # Aggregate and emit footprint update
                self._process_footprint(inst_key, tick)

                # Dynamic sleep to simulate real-time
                if last_tick_time:
                    delta_ms = current_tick_time - last_tick_time
                    if delta_ms > 0:
                        sleep_time = (delta_ms / 1000.0) / self.playback_speed
                        # Cap sleep time to avoid long gaps (e.g. market close to open)
                        time.sleep(min(sleep_time, 1.0 / self.playback_speed))

                last_tick_time = current_tick_time
                self.current_sim_time = current_tick_time

            self.emit_fn('replay_finished', {'date': date_str})
            self.is_running = False
            data_engine.replay_mode = False
            data_engine.sim_time = None

        except Exception as e:
            logger.error(f"Error in replay loop: {e}")
            logger.error(traceback.format_exc())
            self.is_running = False
            self.emit_fn('replay_error', {'message': str(e)})
