# Algorithmic Trading Platform - "Scratchpad"

## Overview
This project is an advanced algorithmic trading platform designed for Order Flow analysis and automated trading on NSE Equities. It focuses on identifying high-probability reversals using "Failed Auctions" and "Absorption" patterns, confirmed by Order Book Imbalance (OBI) and Candlestick patterns.

## Core Strategy: `CombinedSignalEngine`
The primary strategy (`strategies/combined_signal_engine.py`) integrates multiple concepts to filter noise and capture quality moves:

### 1. Failed Auction (The Trap)
- **Logic**: Identifies "Walls" (large limit orders) in the Order Book.
- **Signal**: When a Wall is broken but price fails to sustain and "Reclaims" the level, it signals a Trap (Failed Auction).
- **Entry**:
    - **Long**: Price breaks Support, then reclaims it (Bull Trap).
    - **Short**: Price breaks Resistance, then falls back below it (Bear Trap).

### 2. Confirmations (Confluence)
- **Order Book Imbalance (OBI)**:
    - **Buy**: Requires OBI > 1.2 (Buying pressure).
    - **Sell**: Requires OBI < 0.8 (Selling pressure).
- **Candlestick Patterns (1-min)**:
    - **Long**: Requires **Bullish Engulfing** or **Hammer** on the signal candle.
    - **Short**: Requires **Bearish Engulfing** or **Shooting Star** on the signal candle.

### 3. Dynamic Filters
- **Regime Filter**: Uses 20 EMA and Bollinger Bands (2.5 SD) to classify market mode:
    - **Trend**: Price near EMA (+/- 0.5 SD). Normal trading.
    - **Reversion**: Price outside +/- 2.5 SD. Only trades counter-trend (Reversion).
    - **No-Trade Zone**: Between 0.5 SD and 2.5 SD (Choppy/Noise). Signals are skipped.
- **VWAP Filter**:
    - Longs must be below VWAP (Value Buying).
    - Shorts must be above VWAP (Value Selling).
- **Time Filters**:
    - **No Entry**: After 15:00.
    - **Square-off**: Strict exit at 15:15.
    - **Gap Protection**: Immediate exit if position carries over to a new date (Data gap safety).

## Project Structure
- `main_platform.py`: Entry point for the real-time Dashboard/UI.
- `run_backtest_combined.py`: Script to run backtests using the `CombinedSignalEngine`.
- `strategies/`: Contains strategy logic.
    - `combined_signal_engine.py`: The main strategy class.
- `tape_reading_engine_v2.py`: Base class for Order Flow analysis (Walls, Speed, Aggression).
- `data_engine.py`: Manages data fetching and storage (MongoDB).
- `backtest_reports/`: Contains HTML reports and CSV logs from backtests.
- `backtest_logs/`: Detailed execution logs.
- `archive/`: Legacy scripts and old test files.

## Setup & Usage

### Prerequisites
- Python 3.12+
- MongoDB (running locally)
- Dependencies: `pip install -r requirements.txt`

### Running Backtests
```bash
python run_backtest_combined.py
```
Results will be saved to `backtest_reports/` and `backtest_logs/`.

### Running the Dashboard
```bash
python main_platform.py
```
Access the dashboard at `http://localhost:5000`.

## Key Configuration
- **Instruments**: Defined in `list_instruments.py` or fetched from DB.
- **Parameters**: Adjustable in `CombinedSignalEngine.__init__` (e.g., `obi_buy_threshold`, `min_hold_time_sec`).
