# PRODESK Simplified Terminal

A minimal, high-performance trading terminal featuring TradingView charting and real-time WebSocket data.

## Features

- **Minimal UI**: Clean interface with only a search bar and a full-screen chart.
- **TradingView Charts**: Powered by TradingView Lightweight Charts (v4.1.1) for professional-grade charting with native zoom and pan.
- **Real-time Data**: Live quote streaming via TradingView WebSocket (WSS) protocol.
- **Universal Search**: Search for any symbol across exchanges supported by TradingView.
- **Efficient Backend**: Built with FastAPI and Socket.IO for low-latency data delivery.
- **Local Persistence**: DuckDB for efficient storage of market metadata and ticks.

## Architecture

- **Frontend**: Single Page Application (SPA) using Tailwind CSS, Socket.IO client, and TradingView Lightweight Charts.
- **Backend**:
  - `FastAPI`: REST API for symbol search and historical data.
  - `Socket.IO`: Real-time bi-directional communication.
  - `TradingViewWSS`: Custom implementation of the TradingView WebSocket protocol for live feeds.
  - `Data Engine`: Aggregates and broadcasts market data to connected clients.
- **Database**: `DuckDB` used for local storage of tick data and instrument metadata.

## Setup & Running

### Prerequisites

- Python 3.10+
- Dependencies listed in `requirements.txt`

### Installation

1. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

Optional: Set TradingView credentials in environment variables for authenticated access (allows more symbols/higher limits):
```bash
export TV_USERNAME='your_username'
export TV_PASSWORD='your_password'
```

### Running the Server

Start the application from the project root:

```bash
python3 backend/api_server.py
```

The terminal will be available at `http://localhost:5051`.

## Usage

1. **Search**: Use the centered search bar at the top to find any symbol (e.g., `NSE:RELIANCE`, `NIFTY`, `COINBASE:BTCUSD`).
2. **Chart**: The chart will automatically load historical data and begin receiving live updates via WebSocket.
3. **Controls**: Use the mouse wheel to zoom and click-drag the time scale to move back/forward in time.
