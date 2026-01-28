# ProTrade Integrated Options Desk

This repository contains a unified application merging a high-performance Python backend with a modern React frontend for real-time options trading analysis and execution on the NSE (Nifty/BankNifty).

## 🚀 Overview

The application provides a comprehensive trading dashboard that combines:
- **Live Market Data Feed**: Low-latency streaming via Upstox API V3 and SocketIO.
- **PCR & OI Analysis**: Real-time calculation of Put-Call Ratio and Open Interest buildup across strikes.
- **Institutional Tape Flow**: Monitoring futures and options buildup to identify high-probability reversal setups (Failed Auctions, Absorption).
- **Automated Strategies**: Integrated trading agents including `CombinedSignalEngine` and `CandleCrossStrategy`.
- **Integrated Terminal**: A responsive React-based dashboard for monitoring and manual execution.

## 📂 Project Structure

- **`backend/`**: Standalone Python application (FastAPI/Flask) responsible for data ingestion, strategy execution, and serving the frontend.
- **`frontend/`**: React application (TypeScript/Vite/ECharts) providing the trading dashboard.
- **`backend/strategies/`**: Trading logic and signal generation engines.

## 🛠️ Setup & Installation

### Prerequisites
- Python 3.12+
- Node.js & npm
- MongoDB (running locally)

### 1. Backend Setup
```bash
cd backend
pip install -r requirements.txt
```

### 2. Frontend Setup (Build)
```bash
cd frontend
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

Start the Python server:

```bash
cd backend
python main_platform.py
```

The application will be accessible at **`http://localhost:5050`**.

## 📊 Key Features

- **Terminal Tab**: Real-time OHLCV charts for Index and ATM Option premiums.
- **Analytics Tab**: Market sentiment analysis, PCR trends, and system health monitoring.
- **Flow Tab**: Live monitor for Institutional Tape Flow and Buildup patterns.
- **Replay Mode**: Historical tick data replay for strategy validation.

## 🔒 Security & Compliance
- **Redacted Secrets**: No sensitive tokens are committed to source control.
- Designed to comply with algorithmic trading guidelines where applicable.
