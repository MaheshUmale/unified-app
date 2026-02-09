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
- **URL Parameters**:
  - Open a specific symbol and interval directly via the URL (e.g., `?symbol=NSE:RELIANCE&interval=5`).
  - This mode automatically sets the layout to 1 chart.
- **Maximize Chart**:
  - Use the **MAXIMIZE** button to open the currently active chart in a new browser tab for focused, full-screen analysis.
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
- **DuckDB Viewer**: A dedicated SQL-based viewer at `/db-viewer` that shares the application's database connection, allowing real-time table inspection and custom queries without file-locking issues.
- **Options Analysis Dashboard**:
  - A specialized dashboard at `/options` for deep-dive options analysis.
  - **Real-time Option Chain**: Live streaming of LTP, Volume, Bid, and Ask data.
  - **OI Analysis**: Visual distribution of Call/Put Open Interest and OI Change across all strikes (using Chart.js).
  - **PCR & Max Pain Trends**: Historical tracking of Put-Call Ratio (OI & Volume), Max Pain, and Underlying Spot Price.
  - **Automated Data Management**: Background backfilling and periodic snapshots (every 5 minutes) using Trendlyne and TradingView data sources.

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

- **Main Terminal**: `http://localhost:5051/`
- **Options Dashboard**: `http://localhost:5051/options`
- **DB Viewer**: `http://localhost:5051/db-viewer`

## User Guide

### 1. Multi-Chart Layouts
- **Switching Layouts**: Use the grid icons in the header to toggle between **1, 2, or 4 charts**.
- **Active Chart**: Click anywhere on a chart to make it "Active". The active chart is highlighted with a blue border.
- **Independent Controls**: Symbol search, timeframe selection, and indicator toggles apply only to the **currently active chart**. This allows you to monitor different symbols or timeframes side-by-side.

### 2. Symbol Search & Options
- **Discovery**: Type a symbol (e.g., `RELIANCE`) or index (e.g., `NIFTY`) in the search bar.
- **Options Discovery**: Searching for an index automatically fetches and displays associated option contracts from the TradingView Options Scanner.
- **Technical Symbols**: You can enter exact technical strings like `NSE:NIFTY260210C25600` for direct access to specific contracts.

### 3. Drawing Tools (HLINE)
- **Activation**: Click the **HLINE** button in the header (it will turn blue).
- **Placement**: Click anywhere on the active chart to place a horizontal price line.
- **Quick Shortcut**: Hold **Shift + Click** on the chart to place a horizontal line at any time, even if the HLINE tool is not toggled on.
- **Management**: Drawings are saved automatically and can be removed via the **Indicators** panel.

### 4. Indicator Management
- **Global Toggle**: Use **HIDE ALL / SHOW ALL** to quickly clear the chart of all indicator plots and markers.
- **Individual Control**: Click **INDICATORS** to open the management panel. From here, you can:
  - Toggle the visibility of specific indicator series (lines, areas, histograms).
  - **Customize Colors**: Change the color of any indicator or marker type (e.g., TRAPS) using the built-in color picker.
  - Toggles for markers and signals.
  - Remove individual drawings like horizontal lines.

### 5. Candle Replay
- **Enter Mode**: Click the **REPLAY** button.
- **Select Start**: Click on any historical candle to set the starting point.
- **Controls**: Use **Play/Pause**, **Next**, and **Previous** to step through the price action candle-by-candle.
- **Exit**: Click **EXIT** to return to the real-time feed.

### 6. Persistence
- Your layout configuration, selected symbols, timeframes, and drawings are automatically saved to your browser's local storage. They will be restored exactly as you left them when you return to the application.

## Development & Customization

- **Indicator Mapping**: Indicator plots are mapped in `backend/static/app.js` using the `indicatorSeries` registry. Titles containing "Bubble", "Dot", or "TF" are automatically converted to chart markers.
- **Symbol Normalization**: Symbols are standardized using `backend/core/symbol_mapper.py` to ensure consistency between technical keys (e.g., `NSE:NIFTY`) and human-readable names (`NIFTY`).
