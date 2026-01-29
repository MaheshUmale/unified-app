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
- `db/mongodb.py`: Centralized DB Access Module.
- `external/`: External API Access Module (Upstox, Trendlyne).
- `core/`: Brain/Logic Module (Strategies, PCR Engine, Data Orchestration).

---

## Frontend Application (Angular UI)
**Purpose:** A modern, high-performance trading dashboard for monitoring market data, sentiment, and flow in real-time.

**Core Functionality:**
- Real-time visualization of Index and Option premiums.
- Sentiment analysis display (PCR Trends).
- SocketIO integration for low-latency market updates via RxJS.
- Proxied API calls to the FastAPI backend.

**Key Files (frontend/angular-ui):**
- `src/app/services/data.service.ts`: RxJS-based data management.
- `src/app/components/`: Modular UI components.

---

## Integration Status
Migrated from Flask/React to FastAPI/Angular. Real-time data flow is unified through the backend WebSocket, eliminating direct Upstox calls from the frontend.
