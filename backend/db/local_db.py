"""
DuckDB-based Local Database implementation.
Provides an optimized columnar data store for high-frequency tick data and replay.
"""
import duckdb
import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import threading
import json

logger = logging.getLogger(__name__)

class LocalDBJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

DB_PATH = os.getenv('DUCKDB_PATH', 'pro_trade.db')

class LocalDB:
    _instance = None
    _singleton_lock = threading.Lock()
    _execute_lock = threading.Lock()

    def __new__(cls):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(LocalDB, cls).__new__(cls)
                cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        """Initializes the DuckDB connection and creates tables if they don't exist."""
        # Note: We use the main connection for DDL.
        # For actual usage, we could use cursors or just lock.
        self.conn = duckdb.connect(DB_PATH)

        # Enable JSON extension
        self.conn.execute("INSTALL json; LOAD json;")

        # 1. Ticks table (optimized for replay)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                date DATE,
                instrumentKey VARCHAR,
                ts_ms BIGINT,
                price DOUBLE,
                qty BIGINT,
                source VARCHAR,
                full_feed JSON
            )
        """)
        # We don't necessarily need a traditional index in DuckDB for replay if we sort on disk,
        # but partitions or sorting helps. For now, simple tables.

        # 2. OI Data table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS oi_data (
                date DATE,
                symbol VARCHAR,
                timestamp VARCHAR,
                call_oi DOUBLE,
                put_oi DOUBLE,
                price DOUBLE,
                source VARCHAR,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. Metadata table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                instrument_key VARCHAR PRIMARY KEY,
                hrn VARCHAR,
                meta JSON,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. Trade Signals table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trade_signals (
                timestamp BIGINT,
                trade_id VARCHAR,
                instrumentKey VARCHAR,
                type VARCHAR,
                signal VARCHAR,
                ltp DOUBLE,
                quantity BIGINT,
                pnl DOUBLE,
                sl_price DOUBLE,
                tp_price DOUBLE,
                strategy VARCHAR,
                reason_code VARCHAR,
                meta JSON
            )
        """)

        # 5. VIX Data table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS vix_data (
                date DATE,
                symbol VARCHAR,
                timestamp VARCHAR,
                value DOUBLE,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 6. Strike OI Data (Metrics)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS strike_oi_data (
                instrument_key VARCHAR,
                date DATE,
                timestamp VARCHAR,
                oi DOUBLE,
                price DOUBLE,
                iv DOUBLE,
                gamma DOUBLE,
                theta DOUBLE,
                delta DOUBLE,
                spread DOUBLE,
                updated_at TIMESTAMP
            )
        """)

        logger.info(f"Local DuckDB initialized at {DB_PATH}")

    def insert_ticks(self, ticks: List[Dict[str, Any]]):
        """Batch inserts tick data."""
        if not ticks: return

        # Prepare data for DuckDB append/insert
        data = []
        for t in ticks:
            # Extract basic OHLC info from fullFeed if possible, or use last_price
            price = t.get('last_price', 0)
            qty = t.get('ltq', 0)

            # If price is missing, try extracting from fullFeed
            if not price:
                ff = t.get('fullFeed', {})
                ltpc = ff.get('marketFF', {}).get('ltpc') or ff.get('indexFF', {}).get('ltpc')
                if ltpc:
                    price = float(ltpc.get('ltp', 0))
                    qty = int(ltpc.get('ltq', 0))

            data.append({
                'date': t.get('date', datetime.now().strftime('%Y-%m-%d')),
                'instrumentKey': t.get('instrumentKey'),
                'ts_ms': int(t.get('ts_ms', 0)),
                'price': float(price),
                'qty': int(qty),
                'source': t.get('source', 'live'),
                'full_feed': json.dumps(t, cls=LocalDBJSONEncoder)
            })

        import pandas as pd
        df = pd.DataFrame(data)
        with self._execute_lock:
            self.conn.execute("INSERT INTO ticks SELECT * FROM df")

    def insert_oi(self, symbol: str, date: str, timestamp: str, call_oi: float, put_oi: float, price: float, source: str):
        with self._execute_lock:
            self.conn.execute("""
                INSERT INTO oi_data (date, symbol, timestamp, call_oi, put_oi, price, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (date, symbol, timestamp, call_oi, put_oi, price, source))

    def update_metadata(self, instrument_key: str, hrn: str, meta: Dict[str, Any]):
        meta_json = json.dumps(meta)
        with self._execute_lock:
            self.conn.execute("""
                INSERT OR REPLACE INTO metadata (instrument_key, hrn, meta, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (instrument_key, hrn, meta_json))

    def get_metadata(self, instrument_key: str) -> Optional[Dict[str, Any]]:
        with self._execute_lock:
            res = self.conn.execute("SELECT hrn, meta FROM metadata WHERE instrument_key = ?", (instrument_key,)).fetchone()
        if res:
            return {'hrn': res[0], 'metadata': json.loads(res[1])}
        return None

    def get_all_hrns(self) -> List[str]:
        with self._execute_lock:
            res = self.conn.execute("SELECT DISTINCT hrn FROM metadata").fetchall()
        return [r[0] for r in res]

    def insert_signal(self, signal_doc: Dict[str, Any]):
        meta = signal_doc.get('metadata', {})
        with self._execute_lock:
            self.conn.execute("""
                INSERT INTO trade_signals (
                    timestamp, trade_id, instrumentKey, type, signal, ltp,
                    quantity, pnl, sl_price, tp_price, strategy, reason_code, meta
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                int(signal_doc.get('timestamp', 0)),
                signal_doc.get('trade_id'),
                signal_doc.get('instrumentKey'),
                signal_doc.get('type'),
                signal_doc.get('signal'),
                float(signal_doc.get('ltp', 0)),
                int(signal_doc.get('quantity', 0)),
                float(signal_doc.get('pnl', 0)),
                float(signal_doc.get('sl_price', 0)),
                float(signal_doc.get('tp_price', 0)),
                signal_doc.get('strategy'),
                signal_doc.get('reason_code'),
                json.dumps(meta)
            ))

    def insert_vix(self, date: str, symbol: str, timestamp: str, value: float):
        with self._execute_lock:
            self.conn.execute("""
                INSERT INTO vix_data (date, symbol, timestamp, value)
                VALUES (?, ?, ?, ?)
            """, (date, symbol, timestamp, value))

    def insert_strike_metric(self, doc: Dict[str, Any]):
        with self._execute_lock:
            self.conn.execute("""
                INSERT INTO strike_oi_data (
                    instrument_key, date, timestamp, oi, price, iv,
                    gamma, theta, delta, spread, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc['instrument_key'],
                doc['date'],
                doc['timestamp'],
                float(doc['oi']),
                float(doc['price']),
                float(doc['iv']),
                float(doc['gamma']),
                float(doc['theta']),
                float(doc['delta']),
                float(doc['spread']),
                doc['updated_at']
            ))

    def query(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Generic query method that returns list of dicts."""
        with self._execute_lock:
            df = self.conn.execute(sql, params).fetch_df()
        return df.to_dict('records')

db = LocalDB()
