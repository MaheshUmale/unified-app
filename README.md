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
- **`frontend/`**: Unified React + Vite frontend optimized for high-density data visualization.

## 🛠️ Setup & Installation

### Prerequisites
- **Python**: 3.12+
- **Node.js**: v20+
- **MongoDB**: Active on `localhost:27017`

### 1. Backend Configuration
Set environment variables in a `.env` file in `backend/`:
- `UPSTOX_ACCESS_TOKEN`: Valid Upstox API V3 token.
- `MONGO_URI`: MongoDB connection string (default: `mongodb://localhost:27017/`).
- `DB_NAME`: Database name (default: `upstox_strategy_db_new`).

```bash
cd backend
pip install -r requirements.txt
```

### 2. Frontend Setup
```bash
cd frontend
npm install
npm run build
```

### 3. Execution
The FastAPI server serves the React build from `frontend/dist`.
```bash
# Start the integrated server
python -m uvicorn api_server:app --app-dir backend --port 5051
```
Access at **`http://localhost:5051`**.

## 🏃 Architecture & Data Flow

### Temporal Replay System
The platform features a high-fidelity **Replay Mode** for strategy validation:
- **Simulation Clock**: Synchronizes the system time with historical tick timestamps.
- **Metric Buffering**: Maintains an in-memory rolling buffer of historical Greeks, IV, and OI during playback to enable strategy lookbacks (e.g., "15 mins ago" state) without polluting the production database.
- **Date-Aware Charts**: Automatically fetches and renders historical OHLCV data for the replayed date.

### Data Integration
- **Upstox API V3**: Primary source for real-time WebSocket feeds and historical intraday candles.
- **Trendlyne SmartOptions**: Backend service for expiry discovery and snapshot-based PCR history calculation.
- **Symbol Standardization**: Trade suggestions use the specific format: `NIFTY 50 DD MMM YYYY CALL/PUT STRIKE` (e.g., `NIFTY 50 03 FEB 2026 CALL 25300`).

## 📊 Key UI Components

- **Strategy Dashboard**: Real-time edge scores (0-100), detailed 'Trade Execution Blueprints' (Suggested Strike, Entry, SL/TP), and predictive regime shift probabilities (30-90m window).
- **Terminal View**: Synced OHLCV and Footprint charts for the Index and ATM Option premiums.
- **Flow & Data**: Consolidated sentiment analysis, PCR trends, and institutional buildup panels.

## 🔒 Security
- Sensitive credentials managed via environment variables.
- Production-grade database guards prevent simulation data from corrupting live trading records.
