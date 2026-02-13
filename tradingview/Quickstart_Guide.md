# TradingView API Client Quickstart Guide

## Prerequisites

- Python 3.7+
- Dependencies: `pip install websockets requests`

## Step 1: Authentication

1. Log in to [TradingView](https://www.tradingview.com/).
2. Open Browser DevTools (F12).
3. Run in Console:
   ```javascript
   console.log(JSON.stringify({
     session: window.initData.user.session_token,
     signature: window.initData.user.auth_token
   }));
   ```
4. Set environment variables:
   ```bash
   export TV_SESSION=your_session
   export TV_SIGNATURE=your_signature
   ```

## Step 2: Basic Example

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

    chart = client.Session.Chart()
    chart.set_market('BINANCE:BTCUSDT', {'timeframe': '1D'})

    def on_update():
        if chart.periods:
            print(f"Latest Price: {chart.periods[0].close}")

    chart.on_update(on_update)
    await asyncio.sleep(10)
    await client.end()

if __name__ == '__main__':
    asyncio.run(main())
```

## Step 3: Getting Historical Data

Use the `range` parameter in `set_market`:
```python
chart.set_market('BINANCE:BTCUSDT', {
    'timeframe': '60',
    'range': 200 # Get last 200 hours
})
```

## Step 4: Using Indicators (EMA)

```python
from tradingview import get_indicator

ema_ind = await get_indicator('STD;EMA')
ema_ind.set_option('Length', 20)
ema_study = chart.Study(ema_ind)

def on_ind_update():
    if ema_study.periods:
        print(f"EMA Value: {ema_study.periods[0].plot_0}")

ema_study.on_update(on_ind_update)
```
