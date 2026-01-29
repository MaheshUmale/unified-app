# ProTrade Integrated Options Desk

This repository contains a unified application merging a high-performance FastAPI backend with a modern Angular frontend for real-time options trading analysis and execution on the NSE (Nifty/BankNifty).

## 🚀 Overview

The application provides a comprehensive trading dashboard that combines:
- **Live Market Data Feed**: Low-latency streaming via Upstox API V3 and SocketIO (Asynchronous).
- **PCR & OI Engine**: Real-time calculation of Put-Call Ratio and sentiment analysis based on OI buildup.
- **Trendlyne Integration**: Backend service to backfill historical OI data using Trendlyne SmartOptions API.
- **Institutional Tape Flow**: Monitoring futures and options buildup to identify high-probability reversal setups.
- **Automated Strategies**: Integrated trading agents including `CombinedSignalEngine` and `CandleCrossStrategy`.
- **Modern UI**: Angular v19+ based dashboard utilizing RxJS for high-performance data streaming.

## 📂 Project Structure

- **`backend/`**: Primary FastAPI application containing the API server, data engine, and trading strategies.
- **`backend/services/`**: Modular services for PCR/OI calculations and Trendlyne integration.
- **`backend/strategies/`**: Core trading logic (e.g., Combined Signal, Candle Cross).
- **`frontend/angular-ui/`**: Modern Angular frontend project.

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

### 2. Frontend Build
```bash
cd frontend/angular-ui
npm install
npm run build
```
The build artifacts will be placed in `frontend/dist` and served by the backend.

## 🔑 Configuration & Security

For security, sensitive tokens must be provided via environment variables.

### Backend Environment Variables
Set the following variables in your terminal or a `.env` file in the `backend/` directory:
- `UPSTOX_ACCESS_TOKEN`: Your Upstox V3 Access Token.
- `MONGO_URI`: (Optional) Your MongoDB connection string.

### Frontend Environment Variables (Build time)
If you need to provide tokens directly to the built frontend (e.g. for Trendlyne), set these before running `npm run build`:
- `VITE_UPSTOX_TOKEN`: Upstox token for direct frontend calls.
- `VITE_TRENDLYNE_CSRF`: CSRF token for Trendlyne integration.

## 🏃 Running the Application

Start the FastAPI server using Uvicorn:

```bash
cd backend
python -m uvicorn api_server:app --port 5051 --reload
```

Alternatively, run the script directly:
```bash
cd backend
python api_server.py
```

The application will be accessible at **`http://localhost:5051`**.

## 📊 Key Features

- **Terminal Tab**: Real-time OHLCV charts for Index and ATM Option premiums.
- **Analytics Tab**: Market sentiment analysis, PCR trends, and system health monitoring.
- **Flow Tab**: Live monitor for Institutional Tape Flow and Buildup patterns.
- **Replay Mode**: Historical tick data replay for strategy validation.

## 🔒 Security & Compliance
- **Redacted Secrets**: No sensitive tokens are committed to source control.
- Designed to comply with algorithmic trading guidelines where applicable.
