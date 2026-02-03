# ProTrade Integrated Options Desk

A professional-grade unified trading platform merging a high-performance FastAPI backend with a modern React frontend, specialized for intraday **ATM Option Buying Strategy** on the NSE (Nifty/BankNifty).

## 🚀 Overview

The application provides a specialized dashboard for quantitative volatility trading. It leverages low-latency data streams and automated technical filters to identify high-probability ATM buying opportunities.

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
- **`backend/templates/`**: Native HTML/JS integrated terminal UI.

## 🛠️ Setup & Installation

### Prerequisites
- **Python**: 3.12+
- **MongoDB**: Active on `localhost:27017`

### 1. Backend Configuration
Set environment variables in a `.env` file in `backend/`:
- `UPSTOX_ACCESS_TOKEN`: Valid Upstox API V3 token.
- `MONGO_URI`: MongoDB connection string (default: `mongodb://localhost:27017/`).
- `DB_NAME`: Database name (default: `PRO_TRADE_DATABASE`).

```bash
cd backend
pip install -r requirements.txt
pip install jinja2
```

### 2. Execution
The FastAPI server serves the UI directly via Jinja2 templates. No Node build required.
```bash
# Start the integrated server
python -m uvicorn api_server:app --app-dir backend --port 5051
```
Access at **`http://localhost:5051`**.

## 🏃 Architecture & Data Flow

### Direct Template UI
The platform uses a radically simplified single-page UI served directly by FastAPI. It leverages **ECharts** for high-density visualization and **Socket.IO** for real-time data flow.

### Pine Script Implementation
A sophisticated Pine Script strategy has been translated to native Javascript, featuring:
- **MTF S/R Dots**: Multi-timeframe support (1m, 5m, 15m) for dynamic support and resistance identification.
- **Volume Bubbles**: Scaling visualization of relative volume spikes.
- **Colored Candles**: Price bars color-coded by volume momentum.
- **Dynamic Indicators**: Implementation of EVWMA and Dynamic Pivot lines.
- **Swing Detection**: Confirmation-lag based swing break background coloring.

### Unified Data Layer & Human Readable Names (HRN)
All data (Ticks, OI, Buildup) uses a uniform Human Readable Name convention (e.g., `NIFTY 03 OCT 2024 CALL 25000`), ensuring full decoupling from source-specific technical IDs.

### Data Integration
- **Upstox API V3**: Official SDK integration for real-time WebSocket feeds and historical intraday candles.
- **Trendlyne Proxy**: Backend service for automated expiry discovery and PCR analysis.

## 🔒 Security
- Sensitive credentials managed via environment variables.
- Production-grade database guards prevent simulation data from corrupting live trading records.
