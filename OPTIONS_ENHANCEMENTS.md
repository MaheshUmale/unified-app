# PRODESK Enhanced Options Trading Platform

## Overview

This document outlines the comprehensive enhancements made to the NSE Options Trading App, transforming it into a professional-grade options analysis and trading platform.

## New Features

### 1. Options Greeks Calculator (`core/greeks_calculator.py`)

**Features:**
- Real-time calculation of all major Greeks:
  - **Delta**: Measures rate of change of option price relative to underlying
  - **Gamma**: Rate of change of Delta
  - **Theta**: Time decay (daily)
  - **Vega**: Sensitivity to volatility changes
  - **Rho**: Sensitivity to interest rate changes
- Implied Volatility (IV) calculation using Newton-Raphson method
- Intrinsic and Time Value calculation
- ATM/ITM/OTM strike categorization
- Chain-wide Greeks calculation

**API Endpoints:**
- `GET /api/options/greeks/{underlying}` - Calculate Greeks for specific option
- `GET /api/options/chain/{underlying}/with-greeks` - Get chain with all Greeks

### 2. Implied Volatility Analyzer (`core/iv_analyzer.py`)

**Features:**
- **IV Rank**: Current IV relative to 52-week range (0-100 scale)
- **IV Percentile**: Percentage of days with IV below current level
- **IV Skew Analysis**: OTM put vs OTM call IV comparison
- **Term Structure Analysis**: IV across different expiries
- IV spike detection
- Trading signals based on IV levels

**API Endpoints:**
- `GET /api/options/iv-analysis/{underlying}` - Get comprehensive IV metrics

**Interpretation:**
- IV Rank > 70: Favorable for selling options (Iron Condors, Credit Spreads)
- IV Rank < 30: Favorable for buying options (Long Straddles, Debit Spreads)

### 3. OI Buildup Analyzer (`core/oi_buildup_analyzer.py`)

**Features:**
- Automatic detection of OI buildup patterns:
  - **Long Buildup**: OI increases + Price increases (Bullish)
  - **Short Buildup**: OI increases + Price decreases (Bearish)
  - **Long Unwinding**: OI decreases + Price decreases (Bearish)
  - **Short Covering**: OI decreases + Price increases (Bullish)
- Pattern strength classification (strong/moderate/weak)
- Support/Resistance levels based on OI concentration
- Overall market sentiment analysis

**API Endpoints:**
- `GET /api/options/oi-buildup/{underlying}` - Get buildup analysis
- `GET /api/options/support-resistance/{underlying}` - Get key levels

### 4. Strategy Builder (`core/strategy_builder.py`)

**Features:**
- Pre-built strategy templates:
  - Single Leg: Long/Short Calls and Puts
  - Vertical Spreads: Bull Call, Bear Put, Bull Put, Bear Call
  - Iron Condors and Iron Butterflies
  - Straddles and Strangles
  - Calendar Spreads
- Custom strategy builder
- P&L calculation at any underlying price
- Risk metrics: Max Profit, Max Loss, Breakeven points
- Net Greeks calculation for entire strategy
- Payoff chart data generation
- Strategy recommendations based on market view and IV

**API Endpoints:**
- `POST /api/strategy/build` - Build custom strategy
- `POST /api/strategy/bull-call-spread` - Create bull call spread
- `POST /api/strategy/iron-condor` - Create iron condor
- `POST /api/strategy/long-straddle` - Create long straddle
- `GET /api/strategy/{strategy_id}/analysis` - Get strategy analysis
- `GET /api/strategy/recommendations` - Get strategy recommendations

### 5. Alert System (`core/alert_system.py`)

**Features:**
- Multiple alert types:
  - Price above/below thresholds
  - Price change percentage
  - OI change percentage
  - PCR above/below thresholds
  - IV rank thresholds
  - Volume spikes
  - OI buildup patterns
  - Greeks thresholds
- Cooldown periods to prevent spam
- Multiple notification channels (WebSocket, extensible)
- Preset alerts for common scenarios

**API Endpoints:**
- `POST /api/alerts/create` - Create new alert
- `GET /api/alerts` - Get all alerts
- `DELETE /api/alerts/{alert_id}` - Delete alert
- `POST /api/alerts/{alert_id}/pause` - Pause alert
- `POST /api/alerts/{alert_id}/resume` - Resume alert

### 6. Enhanced Options Dashboard

**New UI Features:**
- Real-time Greeks display in option chain
- IV Rank card with trading signals
- Net Delta tracking
- Tabbed interface:
  - Option Chain (with Greeks)
  - OI Analysis (charts + support/resistance)
  - PCR Trend (historical chart)
  - Greeks (Delta & Theta distribution charts)
  - OI Buildup (pattern analysis)
  - Strategies (builder + analysis)

## Database Schema Updates

### Enhanced `options_snapshots` Table
```sql
-- New columns added:
- iv (Implied Volatility)
- delta
- gamma
- theta
- vega
- intrinsic_value
- time_value
```

## API Summary

### Options Endpoints
| Endpoint | Description |
|----------|-------------|
| `GET /api/options/chain/{underlying}` | Get option chain with Greeks |
| `GET /api/options/greeks/{underlying}` | Calculate Greeks for option |
| `GET /api/options/oi-buildup/{underlying}` | OI buildup analysis |
| `GET /api/options/iv-analysis/{underlying}` | IV analysis |
| `GET /api/options/support-resistance/{underlying}` | Key levels |
| `GET /api/options/pcr-trend/{underlying}` | PCR historical data |
| `GET /api/options/oi-analysis/{underlying}` | OI distribution |
| `POST /api/options/backfill` | Trigger backfill |

### Strategy Endpoints
| Endpoint | Description |
|----------|-------------|
| `POST /api/strategy/build` | Build custom strategy |
| `POST /api/strategy/bull-call-spread` | Bull call spread |
| `POST /api/strategy/iron-condor` | Iron condor |
| `POST /api/strategy/long-straddle` | Long straddle |
| `GET /api/strategy/{id}/analysis` | Strategy analysis |
| `GET /api/strategy/recommendations` | Get recommendations |

### Alert Endpoints
| Endpoint | Description |
|----------|-------------|
| `POST /api/alerts/create` | Create alert |
| `GET /api/alerts` | List alerts |
| `DELETE /api/alerts/{id}` | Delete alert |
| `POST /api/alerts/{id}/pause` | Pause alert |
| `POST /api/alerts/{id}/resume` | Resume alert |

## Usage Examples

### Calculate Greeks
```javascript
const response = await fetch('/api/options/greeks/NSE:NIFTY?strike=25000&option_type=call&spot_price=24800&option_price=150');
const greeks = await response.json();
// Returns: { delta, gamma, theta, vega, rho, implied_volatility, ... }
```

### Build Iron Condor
```javascript
const response = await fetch('/api/strategy/iron-condor', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        underlying: 'NSE:NIFTY',
        spot_price: 25000,
        put_sell_strike: 24800,
        put_buy_strike: 24600,
        call_sell_strike: 25200,
        call_buy_strike: 25400,
        premiums: { put_buy: 15, put_sell: 35, call_sell: 40, call_buy: 18 },
        expiry: '2024-02-29'
    })
});
```

### Create PCR Alert
```javascript
const response = await fetch('/api/alerts/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        name: 'NIFTY PCR High',
        alert_type: 'pcr_above',
        underlying: 'NSE:NIFTY',
        condition: { threshold: 1.5 },
        cooldown_minutes: 30
    })
});
```

## Trading Strategies Guide

### High IV Environment (IV Rank > 70)
- **Iron Condor**: Sell OTM call and put spreads
- **Credit Spreads**: Directional plays with premium collection
- **Short Strangle**: Sell OTM calls and puts

### Low IV Environment (IV Rank < 30)
- **Long Straddle**: Buy ATM call and put
- **Long Strangle**: Buy OTM call and put
- **Debit Spreads**: Directional plays with limited risk

### Bullish View
- **Bull Call Spread**: Buy ITM call, sell OTM call
- **Short Put**: Collect premium if bullish
- **Cash-Secured Put**: Acquire stock at discount

### Bearish View
- **Bear Put Spread**: Buy ITM put, sell OTM put
- **Short Call**: Collect premium if bearish
- **Protective Put**: Insurance for long stock

## Performance Considerations

- Greeks calculations use optimized Black-Scholes model
- IV history maintained for 252 trading days
- Alert cooldowns prevent notification spam
- WebSocket rooms for efficient real-time updates
- Database indexing on underlying and timestamp

## Future Enhancements

Potential features for future releases:
- Paper trading module
- Backtesting engine
- Machine learning for IV prediction
- Automated strategy execution
- Portfolio-level Greeks tracking
- Multi-leg order suggestions
- Historical strategy performance

## Credits

Enhanced by the ProDesk Development Team
Version 3.0 - February 2026
