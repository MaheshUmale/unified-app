from typing import List, Dict, Union, Any, Optional

# Market Symbol Type
MarketSymbol = str  # 'BTCEUR' or 'KRAKEN:BTCEUR'

# Timezone Type
Timezone = str  # 'Etc/UTC', 'exchange', 'Europe/Moscow', etc.

# Timeframe Constants
VALID_TIMEFRAMES = [
    "1", "3", "5", "15", "30", "45", "60", "120", "180", "240",
    "1D", "1W", "1M", "D", "W", "M"
]

# Timeframe Type
TimeFrame = str  # Should be one of VALID_TIMEFRAMES

def is_valid_timeframe(tf: str) -> bool:
    """Validate if given timeframe is valid"""
    return tf in VALID_TIMEFRAMES

class TimeFrameEnum:
    """Timeframe enumeration type"""
    MIN_1 = "1"      # 1 minute
    MIN_3 = "3"      # 3 minutes
    MIN_5 = "5"      # 5 minutes
    MIN_15 = "15"    # 15 minutes
    MIN_30 = "30"    # 30 minutes
    MIN_45 = "45"    # 45 minutes
    MIN_60 = "60"    # 1 hour
    MIN_120 = "120"  # 2 hours
    MIN_180 = "180"  # 3 hours
    MIN_240 = "240"  # 4 hours
    DAY = "1D"       # Daily
    WEEK = "1W"      # Weekly
    MONTH = "1M"     # Monthly
    DAY_ALT = "D"    # Daily (alternative)
    WEEK_ALT = "W"   # Weekly (alternative)
    MONTH_ALT = "M"  # Monthly (alternative)

# Indicator Type
# Built-in Indicator Type
BuiltInIndicatorType = str  # 'Volume@tv-basicstudies-241', etc.

# Built-in Indicator Option
BuiltInIndicatorOption = str  # 'rowsLayout', 'rows', 'volume', etc.

# Graphics Extension Type
# Y-axis Positioning Type
# Label Style Type
LabelStyleValue = str  # 'none', 'xcross', 'cross', etc.

# Line Style Type
LineStyleValue = str  # 'solid', 'dotted', 'dashed', etc.

# Box Style Type
# Size Value Type
# Vertical Alignment Type
# Horizontal Alignment Type
# Text Wrapping Type
# Table Position Type
TablePositionValue = str  # 'top_left', 'top_center', etc.

# Event Types
ClientEvent = str  # 'connected', 'disconnected', etc.

# Market Event Types
# Update Change Types
UpdateChangeType = str  # 'plots', 'report.currency', etc.
