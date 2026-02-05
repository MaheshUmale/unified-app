# ProTrade Integrated Options Desk

A professional-grade unified trading platform merging a high-performance FastAPI backend with a native JS terminal UI, specialized for intraday **ATM Option Buying Strategy** on the NSE (Nifty/BankNifty).

## 🚀 Overview

The application provides a specialized dashboard for quantitative volatility trading. It leverages low-latency data streams from TradingView and automated technical filters to identify high-probability ATM buying opportunities.

### Key Strategy: ATM Option Buying
The core engine evaluates market conditions across five quantitative dimensions:
1.  **IV Velocity Filter**: Computes `ΔIV / 15min`. Passes if IV acceleration exceeds 60% of theta decay.
2.  **Straddle-Math Filter**: Compares expected move (derived from IV & momentum) against the ATM straddle price.
3.  **OI-Micro Filter**: Monitors intraday OI change rates and sudden volume spikes relative to daily ADV.
4.  **Gamma-Amplification Filter**: Identifies regimes where ATM Gamma is above its 5-day median, signaling potential dealer hedging acceleration.
5.  **Microstructure Filter**: Detects tightening bid-ask spreads at ATM strikes combined with volume momentum.

## 📂 Project Structure

- **`backend/`**: FastAPI application containing the API server, data engine, and strategy implementations.
- **`backend/core/strategies/`**: Quantitative logic for the ATM Buying strategy.
- **`backend/db/`**: Local storage implementation using DuckDB.
- **`backend/templates/`**: Native HTML/JS integrated terminal UI.

## 🛠️ Setup & Installation

### Prerequisites
- **Python**: 3.12+
- **DuckDB**: (Handled automatically via python package)

### 1. Backend Configuration
Set optional environment variables in a `.env` file in `backend/`:
- `TV_USERNAME`: TradingView username (optional).
- `TV_PASSWORD`: TradingView password (optional).
- `DUCKDB_PATH`: Path to the DuckDB file (default: `pro_trade.db`).

```bash
cd backend
pip install -r requirements.txt
```

### 2. Execution
The FastAPI server serves the UI directly via Jinja2 templates.
```bash
# Start the integrated server
python -m uvicorn api_server:app --app-dir backend --port 5051
```
Access at **`http://localhost:5051`**.

## 🏃 Architecture & Data Flow

### Direct Template UI
The platform uses a single-page UI served directly by FastAPI. It leverages **ECharts** for high-density visualization and **Socket.IO** for real-time data flow.

### Quantitative Indicators
The terminal features a sophisticated real-time indicator suite:
- **MTF S/R Dots**: Multi-timeframe support (1m, 5m, 15m) for dynamic support and resistance identification.
- **Volume Bubbles**: Scaling visualization of relative volume spikes.
- **Colored Candles**: Price bars color-coded by volume momentum (RVOL).
- **Dynamic Indicators**: Implementation of EVWMA and Dynamic Pivot lines.
- **Swing Detection**: Confirmation-lag based swing break detection.

### Unified Data Layer & Human Readable Names (HRN)
All data (Ticks, OI, Buildup) uses a uniform Human Readable Name convention (e.g., `NIFTY 03 FEB 2026 CALL 25300`), ensuring full decoupling from source-specific technical IDs.

### Data Integration
- **TradingView**: Background polling of Index prices and Option Chain Scanner for live Greeks, IV, and OI.
- **Trendlyne**: Backend service for automated expiry discovery and "Golden PCR" historical backfill.
- **DuckDB**: Columnar local database optimized for high-frequency tick archiving and historical session replay.

## 🔒 Security
- Sensitive credentials managed via environment variables.
- No broker dependencies (Upstox removed); uses public/scanner data sources.
