"""
Market Data Module
"""
import json
from typing import Dict, Any, Callable, List

from tradingview.utils import get_logger
logger = get_logger(__name__)

class QuoteMarket:
    """
    Represents a specific market symbol within a quote session.
    """
    def __init__(self, quote_session, symbol, session='regular'):
        """
        Initialize market data tracking.

        Args:
            quote_session: Parent quote session
            symbol: Trading symbol
            session: Market session type (e.g., 'regular')
        """
        self._symbol = symbol
        self._session = session
        self._symbol_key = f"={json.dumps({'session': session, 'symbol': symbol})}"

        self._symbol_listeners = quote_session.symbol_listeners
        self._quote_session = quote_session

        if self._symbol_key not in self._symbol_listeners:
            self._symbol_listeners[self._symbol_key] = []
            quote_session.send('quote_add_symbols', [
                quote_session.session_id,
                self._symbol_key
            ])

        self._symbol_listener_id = len(self._symbol_listeners[self._symbol_key])
        self._symbol_listeners[self._symbol_key].append(self._handle_data)

        self._last_data = {}
        self._callbacks = {
            'loaded': [],
            'data': [],
            'event': [],
            'error': []
        }

    def _handle_event(self, event, *data):
        """
        Dispatch an event to registered callbacks.

        Args:
            event: Event type
            data: Event payload
        """
        for callback in self._callbacks[event]:
            callback(*data)

        for callback in self._callbacks['event']:
            callback(event, *data)

    def _handle_error(self, *msgs):
        """
        Log and dispatch errors.

        Args:
            msgs: Error messages
        """
        if not self._callbacks['error']:
            error_msg = " ".join(str(msg) for msg in msgs)
            logger.error(f"ERROR: {error_msg}")
        else:
            self._handle_event('error', *msgs)

    def _handle_data(self, packet):
        """
        Process incoming data packets.

        Args:
            packet: Data packet
        """
        if packet['type'] == 'qsd' and packet['data'][1]['s'] == 'ok':
            self._last_data.update(packet['data'][1]['v'])
            self._handle_event('data', self._last_data)
            return

        if packet['type'] == 'quote_completed':
            self._handle_event('loaded')
            return

        if packet['type'] == 'qsd' and packet['data'][1]['s'] == 'error':
            self._handle_error('Market error', packet['data'])

    def on_loaded(self, callback):
        """Register a callback for when data is fully loaded."""
        self._callbacks['loaded'].append(callback)

    def on_data(self, callback):
        """Register a callback for each data update."""
        self._callbacks['data'].append(callback)

    def on_event(self, callback):
        """Register a generic event callback."""
        self._callbacks['event'].append(callback)

    def on_error(self, callback):
        """Register an error callback."""
        self._callbacks['error'].append(callback)

    def close(self):
        """Stop tracking this symbol and cleanup listeners."""
        if len(self._symbol_listeners[self._symbol_key]) <= 1:
            self._quote_session.send('quote_remove_symbols', [
                self._quote_session.session_id,
                self._symbol_key
            ])

        self._symbol_listeners[self._symbol_key][self._symbol_listener_id] = None
