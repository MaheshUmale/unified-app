# Application Analysis Summary

## Backend Application (`scratchpad-main`)
**Purpose:** An autonomous AI Agent and algorithmic trading platform for intraday Option Buying on Indian Derivatives (NSE). It focuses on PCR/OI analysis and order flow patterns.

**Core Functionality:**
- Real-time data ingestion from Upstox API V3 (Protobuf/WebSocket).
- PCR and OI Calculation Engine for market sentiment analysis.
- Strategy Execution (Failed Auction, Absorption, Candle Cross).
- Risk Management and Order Execution.
- Historical data replay and backtesting capabilities.
- MongoDB integration for tick data and signal storage.
- Flask-based dashboard (Legacy) and SocketIO server for real-time updates.

**Key Files:**
- `main_platform.py`: Server entry point, API routes, and SocketIO events.
- `data_engine.py`: Manages real-time data streams and strategy dispatching.
- `option_chain_fetcher.py`: PCR/OI logic.
- `strategies/`: Contains trading signal logic.
- `database.py`: MongoDB utility functions.

---

## Frontend Application (`UI.zip`)
**Purpose:** A modern, high-performance trading dashboard for monitoring market data, sentiment, and flow in real-time.

**Core Functionality:**
- Real-time visualization of Index and Option premiums using ECharts.
- Sentiment analysis display (PCR, Resistance/Support levels).
- Institutional Tape Flow monitor (Futures and Options buildup).
- Tabbed interface (Terminal, Analytics, Flow).
- Direct integration with Upstox API for historical candles and option chain.
- SocketIO integration for low-latency market updates.

**Key Files:**
- `App.tsx`: Main application component and state management.
- `components/`: UI components (MarketChart, BuildupPanel, SentimentAnalysis).
- `services/`: API and SocketIO service layers.
- `vite.config.ts`: Build and development configuration.
- `package.json`: Dependency and script definitions.

---

## Integration Goal
Merge both applications into a single, deployable unit where the Python backend serves the built React frontend and provides all necessary real-time data via SocketIO.
