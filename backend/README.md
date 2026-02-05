# ProTrade Algorithmic Trading Backend

## Overview
This is the core backend for the ProTrade platform, a high-performance algorithmic trading system optimized for Indian Derivatives (NSE). The backend is built with FastAPI and handles real-time data ingestion, strategy execution, and risk management. It is completely decoupled from traditional brokers and uses TradingView for live data and DuckDB for optimized local storage.

## Modular Architecture
The project is reorganized into four main functional modules:

### 1. External API Access Module (`external/`)
Handles all communication with third-party APIs and data providers.
- **`tv_feed.py`**: Manages the polling-based live feed for indices and options from TradingView.
- **`tv_api.py`**: Client for TradingView historical data (using `tvdatafeed` and `tradingview-scraper`).
- **`tv_mcp.py`**: Advanced TradingView utilities including Option Chain Scanner and Spot Price lookup.
- **`trendlyne_api.py`**: Service for fetching expiry dates, buildup data, and Golden PCR. Now uses uniform HRN naming for all stored data.

### 2. DB Access Module (`db/`)
Centralized database interaction layer using DuckDB.
- **`local_db.py`**: Handles DuckDB connection and optimized local storage in `pro_trade.db`. Optimized for high-frequency tick data and session replay.

### 3. Brain/Logic Module (`core/`)
The decision-making heart of the platform.
- **`data_engine.py`**: Orchestrates data flow, bar building, and strategy dispatching.
- **`pcr_logic.py`**: Core engine for PCR calculation and market sentiment analysis.
- **`strategies/`**: Contains quantitative trading strategies like `CandleCrossStrategy` and `ATMOptionBuyingStrategy`.
- **`replay_engine.py`**: Synchronized historical data replayer for strategy simulation.

### 4. UI/API Layer (`api_server.py`)
Serves as the entry point for the integrated terminal.
- **FastAPI**: Provides REST endpoints for instruments, P&L, data triggers, and analytics. Serves the integrated terminal via Jinja2 templates.
- **Socket.io**: Streams real-time ticks and analytics updates to the terminal UI.

## Setup & Installation

### Prerequisites
- Python 3.12+
- No external database required (uses local DuckDB)

### Quick Start
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure environment (Optional):
   Set `TV_USERNAME`, `TV_PASSWORD`, and `TV_COOKIE` for authenticated TradingView access.
3. Run the server:
   ```bash
   python api_server.py
   ```

## Development
- **Tests**: Run unit tests using `pytest tests/`.
- **Database**: The system uses a local `pro_trade.db` file managed by DuckDB.
- **Conventions**: All market data is stored using Human Readable Names (HRN) to ensure consistency across providers (TradingView, Trendlyne).
