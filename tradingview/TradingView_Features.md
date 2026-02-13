# TradingView API Client Features Document

## 1. Project Overview

This Python library is an unofficial TradingView API client, allowing users to interact with the TradingView platform through code. Key features include fetching real-time and historical market data, using built-in or Pine indicators for technical analysis, accessing chart drawings, and more.

### 1.1 Key Features

- Connect to TradingView WebSocket servers.
- Fetch real-time and historical K-line data.
- Technical analysis using built-in and custom Pine indicators.
- Access chart drawings and markers.
- History data analysis using Replay mode.
- Search markets and indicators.
- Manage Pine indicator permissions.

## 2. Core Concepts & Components

### 2.1 Main Components

- `Client`: Core client, handles WebSocket connection management.
- `ChartSession`: Chart session, processes K-line data and chart operations.
- `Study`: Indicator study, used to add and fetch technical indicator data.
- `BuiltInIndicator`: Built-in indicator class.
- `PineIndicator`: Pine script indicator class.
- `QuoteSession`: Quote session, handles real-time price quotes.

## 3. Basic Usage

### 3.1 Creating Client and Connecting

```python
import asyncio
import os
from tradingview import Client

async def main():
    client = Client(
        token=os.environ.get('TV_SESSION'),
        signature=os.environ.get('TV_SIGNATURE')
    )
    await client.connect()
    # ... use client ...
    await client.end()
```

### 3.2 Fetching Historical Data

```python
chart = client.Session.Chart()
chart.set_market('BINANCE:BTCUSDT', {
    'timeframe': '60',
    'range': 500,
})

def on_update():
    klines = chart.periods
    print(f"Retrieved {len(klines)} K-lines")

chart.on_update(on_update)
```

### 3.3 Using Indicators

```python
from tradingview import get_indicator

ema = await get_indicator('STD;EMA')
ema.set_option('Length', 14)
ema_study = chart.Study(ema)

def on_ema_update():
    for period in ema_study.periods:
        print(f"Time: {period.time}, EMA: {period.plot_0}")

ema_study.on_update(on_ema_update)
```

## 4. Advanced Usage

- **Pine Indicators**: Access custom scripts using indicator IDs.
- **Replay Mode**: Simulate historical data loading step-by-step.
- **Multi-Chart Sync**: Manage multiple `ChartSession` instances simultaneously.
- **Data Export**: Save retrieved K-lines to JSON or CSV.
