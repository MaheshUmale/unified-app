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

### 2. Frontend Setup
The project contains two frontend implementations: a primary React-based dashboard and an Angular-based UI.

#### Option A: React Dashboard (Recommended)
This is the primary UI located in the `frontend/` directory.

**Production Build:**
```bash
cd frontend
npm install
npm run build
```
Build artifacts will be in `frontend/dist`.

**Development Mode:**
```bash
cd frontend
npm run dev
```

#### Option B: Angular UI
Located in `frontend/angular-ui/`.

**Production Build:**
```bash
cd frontend/angular-ui
npm install
npm run build
```
Build artifacts will be in `frontend/angular-ui/dist`.

> **Note:** The FastAPI backend is configured to serve the Angular build by default if present, otherwise it serves the React build from `frontend/dist`.

#### Serving Frontend via Backend
Once you have built the frontend (React or Angular), you can run the backend server, and it will automatically serve the UI at `http://localhost:5051`.

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

## 🔑 Configuration & Security

For security, sensitive tokens must be provided via environment variables.

### Backend Environment Variables
Set the following variables in your terminal or a `.env` file in the `backend/` directory:
- `UPSTOX_ACCESS_TOKEN`: Your Upstox V3 Access Token.
- `MONGO_URI`: (Optional) Your MongoDB connection string.

### Frontend Environment Variables (Build time)
The frontend no longer requires external API tokens as all requests are proxied through the backend. The following are optional for specific features:
- `GEMINI_API_KEY`: For AI-assisted market analysis (if enabled).

## 🏃 Architecture & Data Flow

The application follows a secure proxy architecture to ensure modularity and separation of responsibilities:
- **Frontend**: Handles only UI rendering and user interactions. It consumes internal API endpoints (`/api/upstox/*`, `/api/trendlyne/*`).
- **Backend (FastAPI)**: Acts as a secure proxy and data orchestrator. It manages sessions for external services (Trendlyne), resolves instrument keys, and interacts with the Upstox V3 API.
- **Caching**: Trendlyne buildup data is cached in MongoDB to optimize performance and reduce external API dependency.

## 🏃 Running the Application

Start the FastAPI server using Uvicorn:

```bash
# Recommended: Run from root
python -m uvicorn api_server:app --app-dir backend --port 5051

# Alternatively: cd into backend
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
