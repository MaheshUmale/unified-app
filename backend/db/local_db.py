"""
DuckDB-based Local Database implementation.
Provides an optimized columnar data store for high-frequency tick data.
"""
import duckdb
import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
import threading
import pandas as pd

logger = logging.getLogger(__name__)

class LocalDBJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime): return obj.isoformat()
        return super().default(obj)

DB_PATH = os.getenv('DUCKDB_PATH', 'pro_trade.duckdb')

class LocalDB:
    _instance = None
    _singleton_lock = threading.Lock()
    _execute_lock = threading.Lock()
    _batch_count = 0

    def __new__(cls):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(LocalDB, cls).__new__(cls)
                cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        self.conn = duckdb.connect(DB_PATH)
        self.conn.execute("SET memory_limit = '1GB'")
        self.conn.execute("SET threads = 4")
        self.conn.execute("SET TimeZone='UTC'")

        # Check and load extensions to avoid slow INSTALL calls on every boot
        try:
            ext_info = self.conn.execute("SELECT extension_name, installed FROM duckdb_extensions() WHERE extension_name IN ('json', 'icu')").fetchall()
            ext_map = {name: installed for name, installed in ext_info}

            if not ext_map.get('json'):
                logger.info("Installing json extension...")
                self.conn.execute("INSTALL json")
            self.conn.execute("LOAD json")

            if not ext_map.get('icu'):
                logger.info("Installing icu extension...")
                self.conn.execute("INSTALL icu")
            self.conn.execute("LOAD icu")
        except Exception as e:
            logger.warning(f"Error loading extensions: {e}. Attempting direct LOAD...")
            try:
                self.conn.execute("LOAD json")
                self.conn.execute("LOAD icu")
            except:
                logger.error("Failed to load extensions.")

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
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_ticks_key_ts ON ticks (instrumentKey, ts_ms)")

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS metadata (
                instrument_key VARCHAR PRIMARY KEY,
                hrn VARCHAR,
                meta JSON,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Options data for analysis
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS options_snapshots (
                timestamp TIMESTAMP,
                underlying VARCHAR,
                symbol VARCHAR,
                expiry DATE,
                strike DOUBLE,
                option_type VARCHAR,
                oi BIGINT,
                oi_change BIGINT,
                volume BIGINT,
                ltp DOUBLE,
                iv DOUBLE,
                delta DOUBLE,
                gamma DOUBLE,
                theta DOUBLE,
                vega DOUBLE,
                intrinsic_value DOUBLE,
                time_value DOUBLE,
                source VARCHAR
            )
        """)
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_opt_snap_ts ON options_snapshots (timestamp, underlying)")

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS pcr_history (
                timestamp TIMESTAMP,
                underlying VARCHAR,
                pcr_oi DOUBLE,
                pcr_vol DOUBLE,
                pcr_oi_change DOUBLE,
                underlying_price DOUBLE,
                max_pain DOUBLE,
                spot_price DOUBLE,
                total_oi BIGINT,
                total_oi_change BIGINT
            )
        """)

        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_pcr_hist_ts ON pcr_history (timestamp, underlying)")

        self._migrate_db()
        logger.info(f"Local DuckDB initialized at {DB_PATH}")

    def _migrate_db(self):
        """Add missing columns to existing tables."""
        # 1. options_snapshots
        try:
            cols = [c['column_name'] for c in self.get_table_schema('options_snapshots')]
            missing_snapshot_cols = {
                'delta': 'DOUBLE',
                'gamma': 'DOUBLE',
                'theta': 'DOUBLE',
                'vega': 'DOUBLE',
                'intrinsic_value': 'DOUBLE',
                'time_value': 'DOUBLE',
                'source': 'VARCHAR'
            }
            for col, dtype in missing_snapshot_cols.items():
                if col not in cols:
                    logger.info(f"Migrating: Adding {col} to options_snapshots")
                    self.conn.execute(f"ALTER TABLE options_snapshots ADD COLUMN {col} {dtype}")
        except Exception as e:
            logger.error(f"Error migrating options_snapshots: {e}")

        # 2. pcr_history
        try:
            cols = [c['column_name'] for c in self.get_table_schema('pcr_history')]
            missing_pcr_cols = {
                'pcr_oi_change': 'DOUBLE',
                'underlying_price': 'DOUBLE',
                'spot_price': 'DOUBLE',
                'total_oi': 'BIGINT',
                'total_oi_change': 'BIGINT'
            }
            for col, dtype in missing_pcr_cols.items():
                if col not in cols:
                    logger.info(f"Migrating: Adding {col} to pcr_history")
                    self.conn.execute(f"ALTER TABLE pcr_history ADD COLUMN {col} {dtype}")
        except Exception as e:
            logger.error(f"Error migrating pcr_history: {e}")

    def insert_ticks(self, ticks: List[Dict[str, Any]]):
        if not ticks: return
        data = []
        for t in ticks:
            price = t.get('last_price', 0)
            qty = t.get('ltq', 0)
            data.append({
                'date': t.get('date', datetime.now().strftime('%Y-%m-%d')),
                'instrumentKey': t.get('instrumentKey'),
                'ts_ms': int(t.get('ts_ms', 0)),
                'price': float(price),
                'qty': int(qty),
                'source': t.get('source', 'live'),
                'full_feed': json.dumps(t, cls=LocalDBJSONEncoder)
            })

        df = pd.DataFrame(data)
        with self._execute_lock:
            self.conn.execute("INSERT INTO ticks SELECT * FROM df")
            self._batch_count += 1
            if self._batch_count >= 10:
                self.conn.execute("CHECKPOINT")
                self._batch_count = 0

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
        if res: return {'hrn': res[0], 'metadata': json.loads(res[1])}
        return None

    def execute(self, sql: str, params: tuple = ()):
        with self._execute_lock:
            self.conn.execute(sql, params)

    def query(self, sql: str, params: tuple = (), json_serialize: bool = False) -> List[Dict[str, Any]]:
        with self._execute_lock:
            df = self.conn.execute(sql, params).fetch_df()

        # Ensure all datetime columns are UTC-aware
        for col in df.select_dtypes(include=['datetime64']).columns:
            if df[col].dt.tz is None:
                df[col] = df[col].dt.tz_localize('UTC')
            else:
                df[col] = df[col].dt.tz_convert('UTC')

        if json_serialize:
            # Use pandas to_json to handle NaN/nulls correctly for API consumption
            return json.loads(df.to_json(orient='records', date_format='iso'))

        return df.to_dict('records')

    def get_tables(self) -> List[str]:
        with self._execute_lock:
            df = self.conn.execute("SHOW TABLES").fetch_df()
        return df['name'].tolist() if not df.empty else []

    def get_table_schema(self, table_name: str, json_serialize: bool = False) -> List[Dict[str, Any]]:
        with self._execute_lock:
            # DESCRIBE returns column_name, column_type, null, key, default, extra
            # Wrap table name in double quotes for safety
            df = self.conn.execute(f'DESCRIBE "{table_name}"').fetch_df()

        if json_serialize:
            # Use pandas to_json to handle NaN/nulls correctly for API consumption
            return json.loads(df.to_json(orient='records', date_format='iso'))

        return df.to_dict('records')

    def insert_options_snapshot(self, data: List[Dict[str, Any]]):
        if not data: return
        cols = [
            'timestamp', 'underlying', 'symbol', 'expiry', 'strike', 'option_type',
            'oi', 'oi_change', 'volume', 'ltp', 'iv', 'delta', 'gamma', 'theta',
            'vega', 'intrinsic_value', 'time_value', 'source'
        ]
        # Ensure all columns exist in data
        for item in data:
            for c in cols:
                if c not in item: item[c] = None

        df = pd.DataFrame(data)[cols]
        with self._execute_lock:
            self.conn.execute(f"INSERT INTO options_snapshots ({', '.join(cols)}) SELECT * FROM df")

    def insert_pcr_history(self, record: Dict[str, Any]):
        cols = ['timestamp', 'underlying', 'pcr_oi', 'pcr_vol', 'pcr_oi_change', 'underlying_price', 'max_pain', 'spot_price', 'total_oi', 'total_oi_change']
        # Ensure all columns exist in record
        for c in cols:
            if c not in record: record[c] = 0

        df = pd.DataFrame([record])[cols]
        with self._execute_lock:
            self.conn.execute(f"INSERT INTO pcr_history ({', '.join(cols)}) SELECT * FROM df")

db = LocalDB()
