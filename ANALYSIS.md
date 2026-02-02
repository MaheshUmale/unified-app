# Application Analysis Summary

## Backend Application (FastAPI Migration)
**Purpose:** An autonomous AI Agent and algorithmic trading platform for intraday Option Buying on Indian Derivatives (NSE). It focuses on PCR/OI analysis and order flow patterns.

**Core Functionality:**
- Real-time data ingestion from Upstox API V3 (Protobuf/WebSocket).
- PCR/OI Engine Service for market sentiment analysis.
- Trendlyne Service for historical OI data backfilling.
- Strategy Execution (Failed Auction, Absorption, Candle Cross).
- Risk Management and Order Execution.
- Historical data replay and backfilling.
- MongoDB integration for tick data and signal storage.
- FastAPI-based API and Asynchronous SocketIO server.

**Key Files:**
- `api_server.py`: Primary FastAPI server entry point and SocketIO event handlers.
- `db/mongodb.py`: Centralized DB Access Module using singleton pattern.
- `external/`: External API Access Module (Upstox, Trendlyne).
- `core/`: Brain/Logic Module (Strategies in `core/strategies`, PCR Engine in `core/pcr_logic.py`, Data Orchestration in `core/data_engine.py`).

---

## Frontend Application (React)
**Purpose:** High-performance trading dashboards for monitoring market data and strategy execution in real-time.

**Core Functionality:**
- **Simplified Terminal**: Focused view for ATM Option Buying strategy.
- **Data Source Agnostic**: UI only uses Human Readable Names (HRN), abstracting away technical identifiers.
- **Unified Stream**: Transparent Live/Replay modes with a shared data interface.
- **Real-time Visualization**: Synchronized OHLC and Footprint charts for Spot and ATM Premiums.

**Key Files (React - frontend/):**
- `App.tsx`: Unified Strategy Terminal entry point.
- `components/StrategyDashboard.tsx`: Quantitative strategy analysis display.
- `components/MarketChart.tsx`: High-density ECharts implementation.

---

## Integration Status
Unified FastAPI backend with a React frontend. All data sources (Upstox, Trendlyne) are normalized into a Human-Readable format before being persisted in the `PRO_TRADE_DATABASE` and streamed via Socket.IO.
