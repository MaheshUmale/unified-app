
import logging
import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Any
from db.mongodb import get_db

logger = logging.getLogger(__name__)

class SymbolMapper:
    _instance = None
    _mapping_cache: Dict[str, str] = {} # instrument_key -> HRN
    _reverse_cache: Dict[str, str] = {} # HRN -> instrument_key

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SymbolMapper, cls).__new__(cls)
        return cls._instance

    def get_hrn(self, instrument_key: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Converts an instrument key to a Human Readable Name.
        Format: NIFTY 03 OCT 2024 CALL 25000
        """
        if instrument_key in self._mapping_cache:
            return self._mapping_cache[instrument_key]

        # Try to find in metadata collection
        db = get_db()
        doc = db['metadata'].find_one({'instrument_key': instrument_key})
        if doc:
            hrn = doc['hrn']
            self._mapping_cache[instrument_key] = hrn
            self._reverse_cache[hrn] = instrument_key
            return hrn

        # If not found and metadata provided, generate and store
        if metadata:
            hrn = self._generate_hrn(instrument_key, metadata)
            if hrn:
                self._store_mapping(instrument_key, hrn, metadata)
                return hrn

        # Fallback to simple normalization if no metadata
        return instrument_key.replace('|', ' ').replace('NSE INDEX', '').strip()

    def _generate_hrn(self, instrument_key: str, meta: Dict[str, Any]) -> str:
        """
        Generates HRN from metadata.
        meta keys: symbol, type, strike, expiry
        """
        symbol = meta.get('symbol', '').upper()
        if "NIFTY 50" in symbol: symbol = "NIFTY"
        if "NIFTY BANK" in symbol: symbol = "BANKNIFTY"
        if "NIFTY FIN SERVICE" in symbol: symbol = "FINNIFTY"

        itype = meta.get('type', '')
        strike = meta.get('strike')
        expiry = meta.get('expiry') # YYYY-MM-DD

        if itype == 'INDEX':
            return symbol

        if itype == 'FUT':
            if expiry:
                dt = datetime.strptime(expiry, "%Y-%m-%d")
                return f"{symbol} {dt.strftime('%d %b %Y').upper()} FUT"
            return f"{symbol} FUT"

        if itype in ['CE', 'PE', 'CALL', 'PUT']:
            option_type = 'CALL' if itype in ['CE', 'CALL'] else 'PUT'
            if expiry:
                dt = datetime.strptime(expiry, "%Y-%m-%d")
                expiry_str = dt.strftime('%d %b %Y').upper()
                return f"{symbol} {expiry_str} {option_type} {int(strike) if strike else ''}".strip()
            return f"{symbol} {option_type} {int(strike) if strike else ''}".strip()

        return instrument_key

    def _store_mapping(self, instrument_key: str, hrn: str, metadata: Dict[str, Any]):
        db = get_db()
        db['metadata'].update_one(
            {'instrument_key': instrument_key},
            {'$set': {
                'hrn': hrn,
                'instrument_key': instrument_key,
                'metadata': metadata,
                'updated_at': datetime.now()
            }},
            upsert=True
        )
        self._mapping_cache[instrument_key] = hrn
        self._reverse_cache[hrn] = instrument_key

    def resolve_to_key(self, hrn: str) -> Optional[str]:
        """Resolves a Human Readable Name back to an instrument key."""
        if hrn in self._reverse_cache:
            return self._reverse_cache[hrn]

        db = get_db()
        doc = db['metadata'].find_one({'hrn': hrn})
        if doc:
            key = doc['instrument_key']
            self._mapping_cache[key] = hrn
            self._reverse_cache[hrn] = key
            return key
        return None

symbol_mapper = SymbolMapper()
