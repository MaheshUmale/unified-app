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
- `DB_NAME`: Database name (default: `PRO_TRADE_DATABASE`).

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

### Unified Data Layer & Human Readable Names (HRN)
The platform utilizes a unified data layer where all instrument identifiers are converted into Human Readable Names (HRN) before storage and transmission.
- **Format**: `NIFTY 03 OCT 2024 CALL 25000`
- **Abstraction**: The UI is completely decoupled from technical data source identifiers (Upstox keys or Trendlyne IDs). It only operates on HRNs.
- **Database**: All data from Upstox (Ticks, OI) and Trendlyne (Buildup) is stored in the `PRO_TRADE_DATABASE` using these uniform names.

### Temporal Replay System
The platform features a high-fidelity **Replay Mode** for strategy validation:
- **Seamless Integration**: Switching to Replay mode is transparent to the UI. The user selects a date, and the backend handles data discovery and synchronization.
- **Simulation Clock**: Synchronizes the system time with historical tick timestamps.
- **Metric Buffering**: Maintains an in-memory rolling buffer of historical Greeks, IV, and OI during playback to enable strategy lookbacks without polluting the production database.

### Data Integration
- **Upstox API V3**: Primary source for real-time WebSocket feeds and historical intraday candles.
- **Trendlyne SmartOptions**: Backend service for expiry discovery and snapshot-based buildup analysis.

## 📊 Key UI Components

- **Strategy Dashboard**: Real-time edge scores (0-100), detailed 'Trade Execution Blueprints', and predictive regime shift probabilities.
- **Terminal View**: High-density synchronized charts for Spot Price, ATM CALL, and ATM PUT.

## 🔒 Security
- Sensitive credentials managed via environment variables.
- Production-grade database guards prevent simulation data from corrupting live trading records.
