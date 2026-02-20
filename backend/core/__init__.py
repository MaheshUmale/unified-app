"""
Core module for ProTrade Enhanced Options Trading Platform.
Uses lazy loading to prevent circular dependencies.
"""
from typing import Any

def __getattr__(name: str) -> Any:
    if name == 'options_manager':
        from core.options_manager import options_manager
        return options_manager
    if name == 'data_engine':
        from core import data_engine
        return data_engine
    if name == 'symbol_mapper':
        from core.symbol_mapper import symbol_mapper
        return symbol_mapper
    if name == 'greeks_calculator':
        from core.greeks_calculator import greeks_calculator
        return greeks_calculator
    if name == 'iv_analyzer':
        from core.iv_analyzer import iv_analyzer
        return iv_analyzer
    if name == 'oi_buildup_analyzer':
        from core.oi_buildup_analyzer import oi_buildup_analyzer
        return oi_buildup_analyzer
    if name == 'strategy_builder':
        from core.strategy_builder import strategy_builder
        return strategy_builder
    if name == 'alert_system':
        from core.alert_system import alert_system
        return alert_system

    # Check if it's a module in core
    import importlib
    try:
        return importlib.import_module(f"core.{name}")
    except ImportError:
        raise AttributeError(f"module {__name__} has no attribute {name}")

__all__ = [
    'options_manager',
    'data_engine',
    'symbol_mapper',
    'greeks_calculator',
    'iv_analyzer',
    'oi_buildup_analyzer',
    'strategy_builder',
    'alert_system'
]
