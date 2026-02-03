# ProTrade Algorithmic Trading Backend

## Overview
This is the core backend for the ProTrade platform, a high-performance algorithmic trading system optimized for Indian Derivatives (NSE). The backend is built with FastAPI and handles real-time data ingestion, strategy execution, and risk management.

## Modular Architecture
The project is reorganized into four main functional modules:

### 1. External API Access Module (`external/`)
Handles all communication with third-party APIs and data providers.
- **`upstox_feed.py`**: Manages the persistent WebSocket connection to Upstox Market Data Feed V3.
- **`upstox_api.py`**: REST client for Upstox V3 (historical/intraday candles) and V2 (option chain).
- **`upstox_helper.py`**: Utilities for instrument key resolution and NSE master data caching.
- **`trendlyne_api.py`**: Service for fetching expiry dates, buildup data, and backfilling OI. Implements `TrendlyneSession` for CSRF/cookie management. Now uses uniform HRN naming for all stored data.

### 2. DB Access Module (`db/`)
Centralized database interaction layer using MongoDB.
- **`mongodb.py`**: Handles connection pooling, collection access, and indexing for `PRO_TRADE_DATABASE`.

### 3. Brain/Logic Module (`core/`)
The decision-making heart of the platform.
- **`data_engine.py`**: Orchestrates data flow, bar building, and strategy dispatching.
- **`pcr_logic.py`**: Core engine for PCR calculation and market sentiment analysis.
- **`strategies/`**: Contains quantitative trading strategies like `CombinedSignalEngine` and `CandleCrossStrategy`.
- **`risk_controller.py`**: Enforces position limits and daily drawdown protection.
- **`position_manager.py`**: Tracks live P&L and active positions.

### 4. UI/API Layer (`api_server.py`)
Serves as the entry point for the integrated terminal.
- **FastAPI**: Provides REST endpoints for instruments, P&L, data triggers, and proxies for Upstox/Trendlyne data. Serves the integrated terminal via Jinja2 templates.
- **Socket.io**: Streams real-time ticks and analytics updates to the terminal UI.

## Setup & Installation

### Prerequisites
- Python 3.12+
- MongoDB 6.0+ (Running on `localhost:27017` or configured via `MONGO_URI`)

### Quick Start
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure environment:
   Set `UPSTOX_ACCESS_TOKEN` in your environment or `.env` file.
3. Run the server:
   ```bash
   python api_server.py
   ```

## Development
- **Tests**: Run unit tests using `pytest tests/`.
- **Database**: The system defaults to using the `PRO_TRADE_DATABASE` database.
- **Conventions**: All market data is stored using Human Readable Names (HRN) to ensure consistency across providers (Upstox, Trendlyne).
