"""
Quote Session Module
"""
from typing import List, Dict, Any, Optional, Callable, Union
from ..utils import gen_session_id
from .market import QuoteMarket

def get_quote_fields(fields_type='all'):
    """
    Get a list of quote fields.

    Args:
        fields_type: Type of fields to retrieve

    Returns:
        List[str]: List of field names
    """
    if fields_type == 'price':
        return ['lp']

    return [
        'base-currency-logoid', 'ch', 'chp', 'currency-logoid',
        'currency_code', 'current_session', 'description',
        'exchange', 'format', 'fractional', 'is_tradable',
        'language', 'local_description', 'logoid', 'lp',
        'lp_time', 'minmov', 'minmove2', 'original_name',
        'pricescale', 'pro_name', 'short_name', 'type',
        'update_mode', 'volume', 'ask', 'bid', 'fundamentals',
        'high_price', 'low_price', 'open_price', 'prev_close_price',
        'rch', 'rchp', 'rtc', 'rtc_time', 'status', 'industry',
        'basic_eps_net_income', 'beta_1_year', 'market_cap_basic',
        'earnings_per_share_basic_ttm', 'price_earnings_ttm',
        'sector', 'dividends_yield', 'timezone', 'country_code',
        'provider_id',
    ]

class QuoteSession:
    """
    Quote Session Class
    """
    def __init__(self, client, options=None):
        """
        Initialize the quote session.

        Args:
            client: Client instance
            options: Session options
        """
        if options is None:
            options = {}

        self._session_id = gen_session_id('qs')
        self._client = client
        self._symbol_listeners = {}

        # Register session
        self._client.sessions[self._session_id] = {
            'type': 'quote',
            'on_data': self._on_session_data
        }

        # Configure fields
        fields = (options.get('custom_fields', [])
                  if options.get('custom_fields')
                  else get_quote_fields(options.get('fields')))

        # Send creation requests
        self._client.send('quote_create_session', [self._session_id])
        self._client.send('quote_set_fields', [self._session_id, *fields])

        # Factory for Market instances
        self.Market = lambda symbol, session='regular': QuoteMarket(
            self,
            symbol,
            session
        )

    def _on_session_data(self, packet):
        """
        Handle session data.

        Args:
            packet: Received packet
        """
        if packet['type'] == 'quote_completed':
            symbol_key = packet['data'][1]
            if symbol_key not in self._symbol_listeners:
                self._client.send('quote_remove_symbols', [self._session_id, symbol_key])
                return

            for handler in self._symbol_listeners[symbol_key]:
                if handler:
                    handler(packet)

        elif packet['type'] == 'qsd':
            symbol_key = packet['data'][1]['n']
            if symbol_key not in self._symbol_listeners:
                self._client.send('quote_remove_symbols', [self._session_id, symbol_key])
                return

            for handler in self._symbol_listeners[symbol_key]:
                if handler:
                    handler(packet)

    @property
    def session_id(self):
        """Get session ID"""
        return self._session_id

    @property
    def symbol_listeners(self):
        """Get active symbol listeners"""
        return self._symbol_listeners

    def send(self, packet_type, packet_data):
        """
        Send a data packet.

        Args:
            packet_type: Packet type
            packet_data: Packet payload
        """
        self._client.send(packet_type, packet_data)

    def delete(self):
        """Delete the session"""
        self._client.send('quote_delete_session', [self._session_id])
        if self._session_id in self._client.sessions:
            del self._client.sessions[self._session_id]
