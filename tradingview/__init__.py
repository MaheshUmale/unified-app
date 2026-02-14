"""
TradingView API Client Main Module

This module provides access to the TradingView API for market data, chart data, and technical indicators.
"""

# Client core
from .client import Client

# Chart modules
from .chart import ChartSession, Study

# Quote modules
from .quote import QuoteSession, QuoteMarket

# Indicators and technical analysis
from .classes.builtin_indicator import BuiltInIndicator
from .classes.pine_indicator import PineIndicator
from .classes.pine_perm_manager import PinePermManager

# Tools and helper functions
from .misc_requests import (
    fetch_scan_data,
    get_ta,
    search_market,
    search_market_v3,
    search_indicator,
    get_indicator,
    login_user,
    get_private_indicators,
    get_chart_token,
    get_drawings
)

# Utility modules
from . import utils
from . import protocol
from . import tradingview_types as types

# Version info
__version__ = '1.0.0'

__all__ = [
    'Client',
    'ChartSession', 'Study',
    'QuoteSession', 'QuoteMarket',
    'BuiltInIndicator', 'PineIndicator', 'PinePermManager',
    'fetch_scan_data', 'get_ta', 'search_market', 'search_market_v3',
    'search_indicator', 'get_indicator', 'login_user',
    'get_private_indicators', 'get_chart_token', 'get_drawings',
    'utils', 'protocol', 'types'
]
