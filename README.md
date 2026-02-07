# PRODESK Simplified Terminal

A minimal, high-performance trading terminal featuring TradingView charting, real-time WebSocket data, and candle-by-candle replay.

## Features

- **Minimal UI**: Clean interface with only a search bar and a full-screen chart.
- **TradingView Charts**: Powered by TradingView Lightweight Charts (v4.1.1) for professional-grade charting with native zoom and pan.
- **Zoom Controls**: Dedicated (+), (-), and RESET buttons for easy timescale management.
- **Candle-by-Candle Replay**:
  - Enter Replay mode to analyze historical price action.
  - **Select Start**: Click anywhere on the chart to set the starting point for replay.
  - **Playback**: Use Play/Pause, Next, and Previous buttons to step through candles one by one.
- **Real-time Data Flow**:
  - Live quote streaming and indicator plot data via TradingView WebSocket (WSS) protocol.
  - **Indicator Integration**: Directly pulls plot data from Pine Script studies (Bubbles, S/R Dots, Pivot Lines, etc.).
  - **Room-based Broadcasting**: Uses Socket.IO rooms named after symbol HRNs to ensure efficient, targeted data delivery.
- **Multi-Chart Layouts**:
  - Toggle between **1, 2, or 4-chart** grids using the layout selector.
  - Each chart instance operates independently with its own symbol, interval, and indicator state.
  - Automatic grid resizing for optimal screen utilization.
- **Layout Persistence**:
  - Automatically saves your layout, symbols, intervals, and drawing tools to `localStorage`.
  - Restores your previous setup instantly on refresh.
- **Advanced Visualization**:
  - **Markers & Shapes**: Dynamic rendering of volume bubbles and S/R dots using Lightweight Charts markers.
  - **Bar Coloring**: Real-time candle color updates based on study-provided volume and trend metrics, with a built-in RVOL (Relative Volume) fallback for consistent trend analysis.
  - **Background Shading**: Highlighting of specific market conditions (e.g., breakout zones) via background colors.
  - **Smart Scaling**: Automatic Y-axis management to prevent low-value oscillators from compressing the price action.
- **Enhanced Search & Discovery**:
  - **Unified Search**: Search for indices (NIFTY, BANKNIFTY) or stocks (RELIANCE) and get instant results.
  - **Options Discovery**: Automatically merges results from the TradingView Options Scanner.
  - **Technical Search**: Search using exact technical strings (e.g., `NIFTY260210C25600`) for precise contract selection.
- **Efficient Backend**: Built with FastAPI and DuckDB for low-latency data handling and persistence.

## Architecture

- **Frontend**: SPA built with Tailwind CSS. Utilizes `lightweight-charts` for rendering and `socket.io-client` for real-time synchronization.
- **Backend**:
  - `FastAPI`: Serves the UI and provides REST endpoints for symbol search and historical candle aggregation.
  - `TradingViewWSS`: A robust WebSocket client that manages 'quote' and 'chart' sessions, handling interleaved study data and protocol heartbeats.
  - `Data Engine`: The central hub for processing raw ticks, calculating volume deltas, and routing chart updates to the correct Socket.IO rooms.
  - `DuckDB`: A local, high-performance analytical database for storing tick history and symbol metadata.

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

Set TradingView credentials or session cookies in `config.py` (or via environment variables) to access private indicators and higher-granularity data.

### Running the Server

Start the application from the project root:

```bash
python3 backend/api_server.py
```

The terminal will be available at `http://localhost:5051`.

## Development & Customization

- **Indicator Mapping**: Indicator plots are mapped in `backend/static/app.js` using the `indicatorSeries` registry. Titles containing "Bubble", "Dot", or "TF" are automatically converted to chart markers.
- **Symbol Normalization**: Symbols are standardized using `backend/core/symbol_mapper.py` to ensure consistency between technical keys (e.g., `NSE:NIFTY`) and human-readable names (`NIFTY`).

## Searching for Options

To find specific option contracts:
1. **Index Search**: Type an index name like `NIFTY` or `BANKNIFTY`. The search results will automatically show the underlying index followed by available option contracts.
2. **Filtered Search**: Type an index name and a partial date or strike, e.g., `NIFTY 2602` or `NIFTY 25000`.
3. **Exact Technical String**: For power users, you can search for the exact TradingView technical symbol, such as `NIFTY260210C25600`.
