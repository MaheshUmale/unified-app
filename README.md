# ProTrade Integrated Options Desk

This repository contains a unified application merging a high-performance FastAPI backend with a modern React frontend for real-time options trading analysis and execution on the NSE (Nifty/BankNifty).

## 🚀 Overview

The application provides a professional trading dashboard specialized in **ATM Option Buying Strategy** for Nifty 50. It features:
- **Live Market Data Feed**: Low-latency streaming via Upstox API V3 and SocketIO.
- **ATM Strategy Engine**: Quantitative analysis using 5 technical filters (IV Velocity, Straddle-Math, OI-Micro, Gamma-Amplification, Microstructure).
- **Temporal Replay System**: Full historical playback support with a synchronized simulation clock for backtesting.
- **Institutional Tape Flow**: Real-time monitoring of futures and options buildup.
- **Unified React UI**: A consolidated dashboard optimized for actionable trade signals and high-performance data visualization.

## 📂 Project Structure

- **`backend/`**: Primary FastAPI application containing the API server, data engine, and trading strategies.
- **`backend/core/strategies/`**: Implementation of technical trading logic.
- **`frontend/`**: React + Vite frontend project (The unified UI).

## 🛠️ Setup & Installation

### Prerequisites
- **Python**: 3.12 or higher.
- **Node.js**: v20 or higher.
- **MongoDB**: Must be running on `localhost:27017` (default) or configured via environment variables.

### 1. Backend Configuration
Create a `.env` file in the `backend/` directory or set the following environment variables:
- `UPSTOX_ACCESS_TOKEN`: Your valid Upstox API V3 token.
- `MONGO_URI`: (Optional) Custom MongoDB URI.
- `DB_NAME`: (Optional) Defaults to `upstox_strategy_db_new`.

Install dependencies:
```bash
cd backend
pip install -r requirements.txt
```

### 2. Frontend Setup
The project uses a unified React frontend.

**Production Build:**
```bash
cd frontend
npm install
npm run build
```
Build artifacts will be generated in `frontend/dist`.

**Development Mode:**
```bash
cd frontend
npm run dev -- --port 5000
```

### 3. Serving Frontend via Backend
The FastAPI backend serves the React build from `frontend/dist`. Ensure you have built the frontend before starting the production server.

1. Build the UI:
   ```bash
   cd frontend
   npm run build
   ```
2. Start the Backend:
   ```bash
   cd ../backend
   python api_server.py
   ```
3. Access the app at `http://localhost:5051`.

## 🏃 Architecture & Data Flow

The application follows a secure proxy architecture:
- **Frontend**: React-based UI consuming internal API endpoints. Filters PCR and strategy data by symbol to prevent UI flickering.
- **Backend (FastAPI)**: Acts as a data orchestrator and strategy engine. Manages WebSocket connections and MongoDB persistence.
- **Replay Mode**: When active, the system clock is synchronized with historical tick timestamps, enabling strategies to evaluate historical states as if they were live.

## 📊 Key Features

- **Strategy Dashboard**: Real-time edge scores, expectancy tables, and regime shift probabilities.
- **Terminal View**: High-fidelity OHLCV and Footprint charts for the selected index and ATM options.
- **Flow & Data**: Consolidated view for buildup analysis and market sentiment.
- **Replay Controls**: Fine-grained playback controls (speed, seek, pause) for historical data validation.

## 🔒 Security & Compliance
- Sensitive tokens are managed via environment variables.
- Designed for low-latency intraday quantitative analysis.
