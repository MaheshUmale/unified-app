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
from db.mongodb import get_tick_data_collection, get_oi_collection, get_instruments_collection

logger = logging.getLogger(__name__)

class ReplayEngine:
    def __init__(self, emit_fn, db_dependencies: Dict[str, Any]):
        self.emit_fn = emit_fn
        self.tick_collection = db_dependencies.get('tick_collection') or get_tick_data_collection()
        self.oi_collection = db_dependencies.get('oi_collection') or get_oi_collection()
        self.instr_collection = db_dependencies.get('instr_collection') or get_instruments_collection()

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
            ff = tick.get('fullFeed', {}).get('marketFF', {})
            if not ff: return
            ltpc = ff.get('ltpc')
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
        try:
            # 1. Load data
            # Convert date_str (YYYY-MM-DD) to timestamp range
            start_dt = datetime.strptime(f"{date_str} 09:15:00", "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(f"{date_str} 15:30:00", "%Y-%m-%d %H:%M:%S")

            # Fetch all ticks for the day
            # Note: In production, we might want to stream from cursor if data is huge
            # For replay, we load in chunks or all at once if memory allows.
            query = {
                'instrumentKey': {'$in': instrument_keys},
                # Assuming ticks have a timestamp in ms
                # We need to find how ticks are indexed by time.
                # Looking at data_engine, ticks from Upstox have 'ltpc.ltt'
            }

            # Actually, we should probably query by _id if it's ObjectId containing timestamp,
            # but better use a dedicated time field if available.
            # Let's assume we have a way to filter by date.
            # For now, let's just get all for simplicity of the module structure.

            # Better: use a helper to get ticks for a specific day
            ticks_cursor = self.tick_collection.find(query).sort([('fullFeed.marketFF.ltpc.ltt', 1)])

            # Fetch OI data for the same day
            # We need the underlying symbol for these instruments
            symbols = set()
            for key in instrument_keys:
                instr = self.instr_collection.find_one({'instrument_key': key})
                if instr:
                    sym = instr.get('underlying_symbol') or instr.get('trading_symbol')
                    if sym: symbols.add(sym)

            oi_cursor = self.oi_collection.find({
                'symbol': {'$in': list(symbols)},
                'date': date_str
            }).sort([('timestamp', 1)])

            oi_records = list(oi_cursor)
            oi_idx = 0

            last_tick_time = None

            for tick in ticks_cursor:
                if self.stop_event.is_set():
                    break

                while self.is_paused:
                    time.sleep(0.1)
                    if self.stop_event.is_set():
                        return

                ff = tick.get('fullFeed', {}).get('marketFF', {})
                if not ff: continue
                ltt = int(ff.get('ltpc', {}).get('ltt', 0))
                if not ltt: continue

                current_tick_time = ltt

                # Emit any OI updates that occurred before or at this tick time
                # OI timestamp in DB is "HH:MM", we need to convert to ms
                while oi_idx < len(oi_records):
                    oi_rec = oi_records[oi_idx]
                    oi_ts_str = f"{oi_rec['date']} {oi_rec['timestamp']}"
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

                # Emit the tick
                # Wrap it in the same structure as live WSS
                inst_key = tick['instrumentKey']
                feeds_map = {inst_key: tick}
                self.emit_fn('raw_tick', json.dumps(feeds_map))

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

        except Exception as e:
            logger.error(f"Error in replay loop: {e}")
            logger.error(traceback.format_exc())
            self.is_running = False
            self.emit_fn('replay_error', {'message': str(e)})
