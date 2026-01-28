from flask import Flask, render_template, render_template_string, jsonify, request
from pymongo import MongoClient
from datetime import datetime
import sys
from collections import defaultdict
import json
from flask import Flask, render_template_string, jsonify, request
from pymongo import MongoClient
from datetime import datetime
import sys
import json
from urllib.parse import unquote # For decoding the instrument key
from collections import defaultdict
import time

from datetime import datetime , timedelta

import os

import sys
import os
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
# Get the absolute path of the directory containing config.py
# Assuming config.py is in the parent directory of the current script
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

# Add the parent directory to sys.path
sys.path.append(parent_dir)

# Now you can import config
import config
ACCESS_TOKEN = config.ACCESS_TOKEN
# ACCESS_TOKEN = os.environ.get('UPSTOX_ACCESS_TOKEN', 'YOUR_DEFAULT_TOKEN')
# ACCESS_TOKEN = 'eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2OTMxMDQyODc0NTMwYTc3OGEwNTg1OGMiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc2NDgyMDAwOCwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzY0ODg1NjAwfQ.VaK5XMfbXo7_EJofSuFcJjxqykx4zXQTOULT_z7hqr8'
INSTRUMENTS_FILE_PATH = 'nse.json.gz'
# Use "full" mode to receive L5 Order Book data necessary for OBI Strategy
# --- Configuration (MUST MATCH strategy script) ---\
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "upstox_strategy_db"
SIGNAL_COLLECTION = "backtest_signals"
# ---------------------------------------------------
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
db = None

def init_db():
    """Initializes MongoDB connection for the Flask app."""
    global db
    try:
        client = MongoClient(MONGO_URI)
        client.admin.command('ismaster')
        db = client[MONGO_DB_NAME]
        print(f"Flask App connected to MongoDB database: {MONGO_DB_NAME}")
    except Exception as e:
        print(f"CRITICAL ERROR: Flask could not connect to MongoDB at {MONGO_URI}. Error: {e}", file=sys.stderr)
        db = None

import requests
import upstox_client

configuration = upstox_client.Configuration()
configuration.access_token = ACCESS_TOKEN
api_client = upstox_client.ApiClient(configuration)
history_api_instance = upstox_client.HistoryV3Api(api_client)
def generate_ohlc_data_for_lightweight_charts(instrument_key):
    """
    STUB: Generates a sample OHLC data array for Lightweight Charts.

    Lightweight Charts expects data in the format:
    [
        { time: 1642435200, open: 100, high: 105, low: 98, close: 103 },
        { time: 1642521600, open: 103, high: 106, low: 102, close: 104 },
        ...
    ]

    You MUST replace this with logic that fetches minute/5-minute/etc.,
    OHLC bars calculated from your raw tick data in the TICK_COLLECTION.
    """
    # Define the chart parameters
    INTERVAL = "1" # 5-minute intervals

    # The Upstox API expects the interval as 'minutes', 'hours', 'day', 'week', or 'month'
    # The v3 API uses enum values like MINUTE_5, DAY_1, etc.
    # However, the user's example used "minutes" and "5", which corresponds to the V2 documentation.
    # Based on the V3 example structure, we should use the v3 interval enum string:

    # NOTE: The documentation link provided suggests the V3 API signature.
    # We assume Upstox V3 uses string ENUMS like 'MINUTE_5' for the interval.
    # If this fails, the interval argument needs adjustment based on actual V3 client spec.

    # Calling the Upstox V3 APIinstrument_key
    print(f"Fetching OHLC data for {instrument_key} with interval {INTERVAL}...")
    response = history_api_instance.get_intra_day_candle_data(
        instrument_key=instrument_key, unit='minutes',
        interval=INTERVAL,
    )
    # history_api_instance.get_intra_day_candle_data("NSE_EQ|INE848E01016", "minutes", "1")


    # Response structure:
    # response.data = [{candles: [ [time, open, high, low, close, volume], ... ]}]

    if not response.data or not response.data.candles:
        return json.dumps([])

    ohlc_data = []
    for candle in response.data.candles:
        # Candle array structure: [time, open, high, low, close, volume]

        # The 'time' field is an ISO 8601 string (e.g., "2024-03-01T09:15:00+05:30")
        # 1. Parse the ISO 8601 string into a datetime object
        # 2. Convert to UTC Unix timestamp (seconds) for Lightweight Charts

        try:
            # Lightweight Charts requires the time in UTC Epoch seconds.
            # Use standard parsing (assumes the time string is compatible)
            dt_obj = datetime.strptime(candle[0], "%Y-%m-%dT%H:%M:%S%z")
            unix_time_seconds = int(dt_obj.timestamp())
        except ValueError:
            # Fallback parsing if the timezone format is simplified or missing
            try:
                dt_obj = datetime.strptime(candle[0].split('+')[0], "%Y-%m-%dT%H:%M:%S")
                # Assuming local time if no timezone info is explicitly handled by strptime
                unix_time_seconds = int(dt_obj.timestamp())
            except:
                    # Skip invalid candles
                    continue
        ist_offset_seconds = 18000 + 1800
        print(candle)
        ohlc_data.append({
            "time": unix_time_seconds+ist_offset_seconds,
            "open": candle[1],
            "high": candle[2],
            "low": candle[3],
            "close": candle[4],
            "volume": candle[5],
            # Volume is not strictly needed for Lightweight Charts OHLC
        })

    # The data is usually returned in reverse chronological order (newest first)
    # We must reverse it to be chronological (oldest first) for Lightweight Charts
    ohlc_data.reverse()

    if not ohlc_data:
        print(f"No OHLC data returned from Upstox API for {instrument_key}.")
        return json.dumps([])

    return json.dumps(ohlc_data)



def get_live_report_data():
    """
    Queries MongoDB for all trade signals today and calculates the running PnL metrics,
    separating completed trades and open positions.
    """
    if db is None:
        return {"error": "Database not connected."}, 500

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # 1. Fetch all entry and exit logs since midnight
    signals = list(db[SIGNAL_COLLECTION].find({
        "timestamp": {"$gte": today.timestamp()}
    }).sort("timestamp", 1))

    trades = defaultdict(lambda: {'status': 'OPEN', 'entry_time': None, 'instrument': None, 'pnl': 0, 'entry_price': 0, 'exit_price': 0, 'quantity': 0, 'side': ''})
    total_pnl = 0

    for signal in signals:
        trade_id = signal.get('trade_id')
        instrument = signal.get('instrumentKey')



        # print(f"Processing signal for trade_id: {trade_id}, instrument: {instrument}")
        if signal['type'] == 'ENTRY':
            trades[trade_id].update({
                'status': 'OPEN',
                'entry_time':  datetime.fromtimestamp(int(signal['timestamp'])).strftime(TIME_FORMAT),
                'instrument': instrument,
                'entry_price': signal.get('ltp', 0),
                'quantity': signal.get('quantity', 0),
                'side': signal.get('signal', 'UNKNOWN'),
            })

        elif signal['type'] == 'EXIT':
            pnl = signal.get('pnl', 0)
            trades[trade_id]['status'] = 'COMPLETED'
            #@FIXMWE: Check timestamp conversion accuracy in EXIT
            trades[trade_id]['exit_time'] =  datetime.fromtimestamp(int(signal['timestamp'])).strftime(TIME_FORMAT)
            trades[trade_id]['pnl'] = pnl
            trades[trade_id]['exit_price'] = signal.get('exit_price', signal.get('ltp', 0))
            trades[trade_id]['reason'] = signal.get('reason_code', 'EXIT')
            trades[trade_id]['instrument'] = instrument
            trades[trade_id]['side'] = signal.get('signal', 'UNKNOWN')
            total_pnl += pnl

    open_positions = []
    completed_trades = []

    for trade_id, trade_data in trades.items():
        print(f"Trade ID: {trade_id}, Instrument: {trade_data['instrument']}, Status: {trade_data['status']}")
        if trade_data['instrument'] is None:
            print(f"Skipping trade_id {trade_id} due to missing instrumentKey.")
            continue
        if trade_data['status'] == 'OPEN':
            open_positions.append(trade_data)
        elif trade_data['status'] == 'COMPLETED':
            completed_trades.append({
                'id': trade_id,
                'instrument': trade_data['instrument'],
                'side': trade_data['side'],
                'entry_time': trade_data['entry_time'],
                'exit_time': trade_data['exit_time'],
                'entry_price': trade_data['entry_price'],
                'exit_price': trade_data['exit_price'],
                'reason': trade_data['reason'],
                'pnl': trade_data['pnl'],
            })

    # Calculate summary by instrument
    summary = defaultdict(lambda: {'trades': 0, 'pnl': 0})
    for trade in completed_trades:
        summary[trade['instrument']]['trades'] += 1
        summary[trade['instrument']]['pnl'] += trade['pnl']

    trade_summary = [{'instrument': k, 'trades': v['trades'], 'net_pnl': v['pnl']} for k, v in summary.items()]

    return {
        "timestamp": datetime.now().strftime(TIME_FORMAT),
        "total_pnl": round(total_pnl, 2),
        "open_positions": open_positions,
        "completed_trades": completed_trades,
        "trade_summary": trade_summary
    }


from datetime import datetime, timedelta
from collections import defaultdict
import time # Import time for better timestamp handling

# Assuming 'db' is the MongoDB connection and 'SIGNAL_COLLECTION' is defined globally.

from datetime import datetime, timedelta
from collections import defaultdict
import time # Import time for better timestamp handling

# Assuming 'db' is the MongoDB connection and 'SIGNAL_COLLECTION' is defined globally.

def get_live_report_data():
    """
    Queries MongoDB for all trade signals today, calculates the running PnL metrics,
    and separates completed trades and open positions efficiently.
    """
    # 1. Input Validation and Time Calculation
    if db is None:
        # Use a more appropriate Flask/FastAPI response structure if applicable (e.g., abort(500))
        # For a pure dictionary return, this is fine, but include a status key.
        return {"status": "error", "message": "Database not connected."}, 500

    # Calculate the start of the current day in UTC (or local time, depending on MongoDB's storage)
    # Using 'today' object is correct, but ensure consistency with how MongoDB stores 'timestamp'.
    # Assuming 'timestamp' in MongoDB is a UNIX timestamp (seconds since epoch).
    now = datetime.now()
    yestreday = now-timedelta(days=1)
    today_start_timestamp = yestreday.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    print(f"Fetching signals from timestamp: {today_start_timestamp}")
    # 2. Optimized MongoDB Query
    try:
        signals_cursor = db[SIGNAL_COLLECTION].find(
            {"timestamp": {"$gte": today_start_timestamp}}
        ).sort("timestamp", 1)

        # Convert cursor to list once
        signals = list(signals_cursor)
    except Exception as e:
        print(f"MongoDB query failed: {e}")
        return {"status": "error", "message": f"Database query error: {e}"}, 500


    # 3. Data Processing and Aggregation
    trades = {}
    total_pnl = 0

    # Pre-calculate string format for efficiency, if used many times


    for signal in signals:
        trade_id = signal.get('trade_id')
        instrument = signal.get('instrumentKey')

        if not trade_id or not instrument:
            # Skip signals missing critical identifiers
            continue

        if trade_id not in trades:
            # Initialize trade object efficiently
            trades[trade_id] = {
                'status': 'UNKNOWN',
                'instrument': instrument,
                'pnl': 0.0,
                'entry_time': None,
                'exit_time': None,
                'entry_price': 0.0,
                'exit_price': 0.0,
                'quantity': 0,
                'side': signal.get('signal', 'UNKNOWN'), # Default side is from the first signal
                'reason': ''
            }

        trade = trades[trade_id]

        # Use float() on ltp/price fields to ensure correct type for calculations and formatting
        signal_timestamp = int(signal['timestamp'])

        if signal['type'] == 'ENTRY':
            # Only update side and instrument if it's the first signal for the trade_id
            if trade['entry_time'] is None:
                trade.update({
                    'status': 'OPEN',
                    'entry_time': datetime.fromtimestamp(signal_timestamp).strftime(TIME_FORMAT),
                    'entry_price': float(signal.get('ltp', 0)),
                    'quantity': int(signal.get('quantity', 0)),
                    'side': signal.get('position_after', trade['side']), # Use position_after for clarity
                })
            else:
                # Handle cases with multiple ENTRY signals for the same trade_id if necessary
                pass

        elif signal['type'] == 'EXIT':
            pnl = float(signal.get('pnl', 0))

            # Use 'trade.side' for display consistency, even if exit has 'signal' key.
            # The 'side' from the ENTRY should determine the trade type (Long/Short).

            trade.update({
                'status': 'COMPLETED',
                'exit_time': datetime.fromtimestamp(signal_timestamp).strftime(TIME_FORMAT),
                'pnl': pnl,
                'exit_price': float(signal.get('exit_price', signal.get('ltp', 0))),
                'reason': signal.get('reason_code', 'EXIT'),
                'instrument': instrument, # Redundant but safe update
            })
            total_pnl += pnl

    # 4. Separate and Structure Results
    open_positions = []
    completed_trades = []
    summary = defaultdict(lambda: {'trades': 0, 'pnl': 0.0})

    for trade_id, trade_data in trades.items():
        if trade_data['instrument'] is None or trade_data['entry_time'] is None:
            # Skip trades that are incomplete (e.g., only an exit signal found without entry today)
            continue

        # Standardize data structure for output
        output_trade = {
            'instrument': trade_data['instrument'],
            'side': trade_data['side'],
            'entry_time': trade_data['entry_time'],
            'entry_price': round(trade_data['entry_price'], 2),
            'quantity': trade_data['quantity'],
             'status': trade_data['status']
        }

        if trade_data['status'] == 'OPEN':
            open_positions.append(output_trade)

        elif trade_data['status'] == 'COMPLETED':
            # Add completion-specific fields for completed trades
            completed_trade = output_trade.copy()
            completed_trade.update({
                'exit_time': trade_data['exit_time'],
                'exit_price': round(trade_data['exit_price'], 2),
                'reason': trade_data['reason'],
                'pnl': round(trade_data['pnl'], 2),
            })
            completed_trades.append(completed_trade)

            # Update summary
            instrument_key = completed_trade['instrument']
            summary[instrument_key]['trades'] += 1
            summary[instrument_key]['pnl'] += completed_trade['pnl']


    trade_summary = [
        {'instrument': k, 'trades': v['trades'], 'net_pnl': round(v['pnl'], 2)}
        for k, v in summary.items()
    ]

    # 5. Final API Response
    return {
        "status": "success",
        "timestamp": now.strftime(TIME_FORMAT),
        "total_pnl": round(total_pnl, 2),
        "open_positions": open_positions,
        "completed_trades": completed_trades,
        "trade_summary": trade_summary
    }



@app.route('/')
def dashboard():
    """Main dashboard view."""
    data = get_live_report_data()
    if isinstance(data, tuple):
        return render_template_string("<h1>Error</h1><p>{{ error }}</p>", error=data[0]["error"]), data[1]

    total_trades = len(data['completed_trades'])
    total_open = len(data['open_positions'])

    pnl_color_total = 'bg-green-100 text-green-800' if data['total_pnl'] > 0 else 'bg-red-100 text-red-800'

    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Order Flow Strategy Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
            body {{ font-family: 'Inter', sans-serif; background-color: #f4f7f9; }}
            .card {{ background: white; border-radius: 12px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); padding: 24px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 16px; }}
            th, td {{ padding: 12px 15px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
            th {{ background-color: #edf2f7; font-weight: 600; text-transform: uppercase; font-size: 0.85rem; }}
        </style>
    </head>
    <body class="p-8">
        <div class="max-w-7xl mx-auto">
            <h1 class="text-4xl font-bold text-gray-800 mb-6 border-b pb-2">Live Trading Dashboard</h1>

            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div class="card">
                    <p class="text-sm font-medium text-gray-500">Total P&L (Today)</p>
                    <div class="mt-1 text-3xl font-bold" id="total_pnl">{data['total_pnl']:.2f}</div>
                    <span class="text-xs font-semibold px-2.5 py-0.5 rounded-full {pnl_color_total}" id="pnl_status">{ 'PROFIT' if data['total_pnl'] >= 0 else 'LOSS'}</span>
                </div>
                <div class="card">
                    <p class="text-sm font-medium text-gray-500">Open Positions</p>
                    <div class="mt-1 text-3xl font-bold text-blue-600" id="open_count">{total_open}</div>
                </div>
                <div class="card">
                    <p class="text-sm font-medium text-gray-500">Last Updated</p>
                    <div class="mt-1 text-xl font-bold text-gray-600" id="last_updated">{data['timestamp']}</div>
                </div>
            </div>

            <!-- Open Positions -->
            <div class="card mb-8">
                <h2 class="text-2xl font-semibold text-gray-700 mb-4">Open Positions (<span id="open_count_header">{total_open}</span>)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Instrument</th>
                            <th>Side</th>
                            <th>Entry Time</th>
                            <th>Entry Price</th>
                            <th>Quantity</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody id="open_trades_body">
                        <!-- Content rendered by JavaScript -->
                    </tbody>
                </table>
            </div>

            <!-- Completed Trades -->
            <div class="card mb-8">
                <h2 class="text-2xl font-semibold text-gray-700 mb-4">Completed Trades (<span id="completed_count_header">{total_trades}</span>)</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Instrument</th>
                            <th>Side</th>
                            <th>Entry Time</th>
                            <th>Exit Time</th>
                            <th>Entry Price</th>
                            <th>Exit Price</th>
                            <th>Reason</th>
                            <th>P&L</th>
                            <th>Plot</th>
                        </tr>
                    </thead>
                    <tbody id="completed_trades_body">
                        <!-- Content rendered by JavaScript -->
                    </tbody>
                </table>
            </div>

            <!-- Option Chain -->
            <div class="card mb-8">
                <h2 class="text-2xl font-semibold text-gray-700 mb-4">Option Chain</h2>
                <div class="flex items-center mb-4">
                    <label for="instrument-select" class="mr-2">Select Instrument:</label>
                    <select id="instrument-select" class="border rounded p-2">
                        <option value="NSE_INDEX|Nifty 50">NIFTY</option>
                        <option value="NSE_INDEX|Nifty Bank">BANKNIFTY</option>
                    </select>
                </div>
                <div id="option-chain-container"></div>
            </div>

            <!-- Summary -->
            <div class="card">
                <h2 class="text-2xl font-semibold text-gray-700 mb-4">Summary by Instrument</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Instrument</th>
                            <th>Trades</th>
                            <th>Net P&L</th>
                        </tr>
                    </thead>
                    <tbody id="summary_body">
                        <!-- Content rendered by JavaScript -->
                    </tbody>
                </table>
            </div>

        </div>
        <script>
            // The user requested a 30-second interval, which is 30000 milliseconds.
            const REFRESH_INTERVAL_MS = 30000;

            function renderOpenTrades(trades) {{
                const tbody = document.getElementById('open_trades_body');
                let rows = '';
                if (trades.length === 0) {{
                    rows = '<tr><td colspan="6" style="text-align: center;">No open positions.</td></tr>';
                }} else {{
                    trades.forEach(trade => {{
                        rows += `
                        <tr>
                            <td>
                                <a href="/plot/${{trade.instrument}}" target="_blank">
                                    ${{trade.instrument}}
                                </a>
                            </td>

                            <td>${{trade.side}}</td>
                            <td>${{trade.entry_time}}</td>
                            <td>${{trade.entry_price.toFixed(2)}}</td>
                            <td>${{trade.quantity}}</td>
                            <td>${{trade.status}}</td>
                        </tr>
                        `;
                    }});
                }}
                tbody.innerHTML = rows;
                document.getElementById('open_count').textContent = trades.length;
                document.getElementById('open_count_header').textContent = trades.length;
            }}

            function renderCompletedTrades(trades) {{
                const tbody = document.getElementById('completed_trades_body');
                // Reverse trades to show newest at the top
                const reversedTrades = [...trades].reverse();
                let rows = '';
                if (reversedTrades.length === 0) {{
                    rows = '<tr><td colspan="9" style="text-align: center;">No completed trades to display.</td></tr>';
                }} else {{
                    reversedTrades.forEach(trade => {{
                        const pnlColor = trade.pnl > 0 ? 'text-green-500' : 'text-red-500';
                        const viewPlotBtn = `<a href='/plot/${{trade.instrument}}' target='_blank' class='text-blue-500 hover:text-blue-700 font-medium'>View Plot</a>`;

                        rows += `
                        <tr>
                            <td>${{trade.instrument}}</td>
                            <td>${{trade.side}}</td>
                            <td>${{trade.entry_time}}</td>
                            <td>${{trade.exit_time}}</td>
                            <td>${{trade.entry_price.toFixed(2)}}</td>
                            <td>${{trade.exit_price.toFixed(2)}}</td>
                            <td>${{trade.reason}}</td>
                            <td class='${{pnlColor}}'>${{trade.pnl.toFixed(2)}}</td>
                            <td>${{viewPlotBtn}}</td>
                        </tr>
                        `;
                    }});
                }}
                tbody.innerHTML = rows;
                document.getElementById('completed_count_header').textContent = reversedTrades.length;
            }}

            function renderSummary(summary) {{
                const tbody = document.getElementById('summary_body');
                let rows = '';
                if (summary.length === 0) {{
                    rows = '<tr><td colspan="3" style="text-align: center;">No completed trades to display.</td></tr>';
                }} else {{
                    summary.forEach(s => {{
                        const netPnlColor = s.net_pnl > 0 ? 'text-green-500' : 'text-red-500';
                        rows += `
                        <tr>
                            <td>${{s.instrument}}</td>
                            <td>${{s.trades}}</td>
                            <td class='${{netPnlColor}}'>${{s.net_pnl.toFixed(2)}}</td>
                        </tr>
                        `;
                    }});
                }}
                tbody.innerHTML = rows;
            }}


            function updateMetrics(data) {{
                // 1. Update Metrics
                document.getElementById('total_pnl').textContent = data.total_pnl.toFixed(2);
                document.getElementById('last_updated').textContent = data.timestamp;

                const statusElement = document.getElementById('pnl_status');
                const pnlContainer = statusElement.parentElement.parentElement; // The card element

                // Update P&L color status and text
                if (data.total_pnl >= 0) {{
                     statusElement.textContent = 'PROFIT';
                     statusElement.className = "text-xs font-semibold px-2.5 py-0.5 rounded-full bg-green-100 text-green-800";
                     pnlContainer.className = pnlContainer.className.replace(/bg-red-100 text-red-800/, 'bg-green-100 text-green-800');
                }} else {{
                     statusElement.textContent = 'LOSS';
                     statusElement.className = "text-xs font-semibold px-2.5 py-0.5 rounded-full bg-red-100 text-red-800";
                     pnlContainer.className = pnlContainer.className.replace(/bg-green-100 text-green-800/, 'bg-red-100 text-red-800');
                }}
            }}

            function updateDashboard() {{
                fetch('/api/live_pnl')
                    .then(response => response.json())
                    .then(data => {{
                        if (data.status === 'error') {{
                            console.error('API Error:', data.message);
                            return;
                        }}

                        updateMetrics(data);
                        renderOpenTrades(data.open_positions);
                        renderCompletedTrades(data.completed_trades);
                        renderSummary(data.trade_summary);

                    }})
                    .catch(error => {{
                        console.error('Error fetching live P&L:', error);
                        document.getElementById('total_pnl').textContent = "ERROR";
                    }});
            }}

            function renderOptionChain(data) {{
                const container = document.getElementById('option-chain-container');
                let table = '<table class="w-full text-sm text-left text-gray-500">';
                table += '<thead class="text-xs text-gray-700 uppercase bg-gray-50">';
                table += '<tr>';
                table += '<th scope="col" class="px-6 py-3">CE Buildup</th>';
                table += '<th scope="col" class="px-6 py-3">CE OI Chg</th>';
                table += '<th scope="col" class="px-6 py-3">CE OI</th>';
                table += '<th scope="col" class="px-6 py-3">CE LTP</th>';
                table += '<th scope="col" class="px-6 py-3">Strike</th>';
                table += '<th scope="col" class="px-6 py-3">PE LTP</th>';
                table += '<th scope="col" class="px-6 py-3">PE OI</th>';
                table += '<th scope="col" class="px-6 py-3">PE OI Chg</th>';
                table += '<th scope="col" class="px-6 py-3">PE Buildup</th>';
                table += '</tr></thead><tbody>';

                data.options_chain.forEach(option => {{
                    table += '<tr class="bg-white border-b">';
                    table += `<td class="px-6 py-4">${{option.ce_long_buildup ? 'Long' : (option.ce_short_buildup ? 'Short' : (option.ce_long_unwinding ? 'Unwinding' : (option.ce_short_covering ? 'Covering' : '')))}}</td>`;
                    table += `<td class="px-6 py-4">${{option.ce_oi_change}}</td>`;
                    table += `<td class="px-6 py-4">${{option.ce_open_interest}}</td>`;
                    table += `<td class="px-6 py-4">${{option.ce_ltp}}</td>`;
                    table += `<th scope="row" class="px-6 py-4 font-medium text-gray-900 whitespace-nowrap">${{option.strike_price}}</th>`;
                    table += `<td class="px-6 py-4">${{option.pe_ltp}}</td>`;
                    table += `<td class="px-6 py-4">${{option.pe_open_interest}}</td>`;
                    table += `<td class="px-6 py-4">${{option.pe_oi_change}}</td>`;
                    table += `<td class="px-6 py-4">${{option.pe_long_buildup ? 'Long' : (option.pe_short_buildup ? 'Short' : (option.pe_long_unwinding ? 'Unwinding' : (option.pe_short_covering ? 'Covering' : '')))}}</td>`;
                    table += '</tr>';
                }});

                table += '</tbody></table>';
                container.innerHTML = table;
            }}

            function fetchOptionChain(instrumentKey) {{
                fetch(`/api/option_chain/${{instrumentKey}}`)
                    .then(response => response.json())
                    .then(data => {{
                        if (data.status === 'error') {{
                            console.error('API Error:', data.message);
                            return;
                        }}
                        renderOptionChain(data);
                    }})
                    .catch(error => {{
                        console.error('Error fetching option chain:', error);
                    }});
            }}

            // Initial load
            updateDashboard();

            // Refresh every 30 seconds (30000 milliseconds)
            setInterval(updateDashboard, REFRESH_INTERVAL_MS);

            const instrumentSelect = document.getElementById('instrument-select');
            instrumentSelect.addEventListener('change', (event) => {{
                fetchOptionChain(event.target.value);
            }});

            // Initial load
            fetchOptionChain(instrumentSelect.value);
        </script>
    </body>
    </html>
    """
    return render_template_string(html_template)

@app.route('/api/live_pnl')
def live_pnl_api():
    """API endpoint to return all trade metrics and data as JSON."""
    data = get_live_report_data()
    if isinstance(data, tuple):
        return jsonify({"status": "error", "message": data[0].get("error")}), data[1]
    return jsonify(data)

@app.route('/api/option_chain/<instrument_key>')
def option_chain_api(instrument_key):
    """API endpoint to return the latest option chain data as JSON."""
    if db is None:
        return jsonify({"status": "error", "message": "Database not connected."}), 500

    try:
        clean_key = unquote(instrument_key)
        latest_oc = db["option_chain"].find_one(
            {"instrument_key": clean_key},
            sort=[("timestamp", -1)]
        )
        if latest_oc:
            # The _id field is not JSON serializable, so we remove it.
            latest_oc.pop('_id', None)
            return jsonify(latest_oc)
        else:
            return jsonify({"status": "error", "message": "No option chain data found for the instrument."}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500




from flask import jsonify
from urllib.parse import unquote
from datetime import datetime
import json
# Assumes 'db' is the MongoDB connection object initialized in the main Flask app
# Assumes 'SIGNAL_COLLECTION' is defined globally (e.g., "trade_signals")

def get_trade_signals_for_chart(instrument_key  ):
    """
    Queries MongoDB for trade signals (ENTRY/EXIT) for a specific instrument today,
    formats them as a list of dictionaries for Lightweight Charts markers.
    """
    if db is None:
        # Return error as JSON string for safe handling in the API endpoint
        return json.dumps({"status": "error", "message": "Database not connected."})

    print(" DB IS THERE ")
    print(instrument_key)
    # Query for all signals for the instrument for today
    # Assuming 'timestamp' field in MongoDB is a int object
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    # Get today's date
    # today = date.today()

    prior_date = today - timedelta(days=1)
    # Create a timedelta object for one day
    timestamp = int(prior_date.timestamp())-1000000
    query = {
        "instrumentKey": instrument_key,
        "timestamp": {"$gte": timestamp}
    }

    print(query)

# [
#   {
#     $match: {
#       instrumentKey: "NSE_EQ|INE585B01010"
#     }
#   },
#   {
#     $group: {
#       _id: "$trade_id",
#       docs: {
#         $push: "$$ROOT"
#       }
#     }
#   }
# ]



    signals_data = []
    try:
        # Sort by timestamp ascending to ensure correct chronological plotting
        cursor = db[SIGNAL_COLLECTION].find(query).sort("timestamp", 1)


        ist_offset_seconds =   18000 + 1800
        for doc in cursor:
            # print("got data 111")
            if 'timestamp' in doc :
                # Convert MongoDB datetime to UTC Unix timestamp (seconds)
                unix_time_seconds = int(doc['timestamp'] ) +ist_offset_seconds

            print("TYPE IS  : ", doc['type'])
            print("SIGNAL IS  : ", doc['signal'])
            print("TRADE ID IS  : ", doc['trade_id'])
            if doc['type'] == 'ENTRY':
                signals_data.append({
                    "time": unix_time_seconds,
                    # order_type should be one of ENTRY_BUY, ENTRY_SELL, EXIT_BUY, EXIT_SELL
                    "trade_id": doc['trade_id'],
                    "signal": doc['signal'],
                    "type": doc['type'],
                    "price": float(doc['ltp']),
                    "sl_price" : float(doc['sl_price']),
                    "tp_price" : float(doc['tp_price']),
                    "reason": doc.get('reason', "")


                })
            else :
                if doc['type'] == 'EXIT':
                    # Convert MongoDB datetime to UTC Unix timestamp (seconds)

                    signals_data.append({
                        "time": unix_time_seconds,
                        # order_type should be one of ENTRY_BUY, ENTRY_SELL, EXIT_BUY, EXIT_SELL
                        "trade_id": doc['trade_id'],
                        "signal": doc['signal'],
                        "type": doc['type'],
                        "price": float(doc['exit_price']),
                        "sl_price" : float(doc['sl_price']),
                        "tp_price" : float(doc['tp_price']),
                        "reason": doc.get('reason_code', "")

                            # exit_price
                            # 306.55
                            # entry_price
                            # 305.85
                    })




                # print("got data ")
        return json.dumps(signals_data)

    except Exception as e:
        error_msg = f"Error fetching trade signals from MongoDB for {instrument_key}: {e}"
        print(f"[ERROR] {error_msg}")
        import traceback
        traceback.print_exc()
        return json.dumps({"status": "error", "message": error_msg})


@app.route('/api/trade_signals/<instrument_key>')
def trade_signals_api(instrument_key):
    """
    Flask route handler for /api/trade_signals/<instrument_key>.
    """
    # NOTE: This function needs to be registered with the Flask app instance
    # using @app.route('/api/trade_signals/<path:instrument_key>')

    clean_key = unquote(instrument_key)

    # 1. Generate signals data (JSON string)
    signals_data_json_str = get_trade_signals_for_chart(clean_key )

    # 2. Check for internal errors and return JSON response
    try:
        print(signals_data_json_str)
        signals_data = json.loads(signals_data_json_str)
        # Check for JSON structure errors (e.g., {"status": "error", ...})
        if isinstance(signals_data, dict) and signals_data.get("status") == "error":
             return jsonify(signals_data), 500

        return jsonify(signals_data)

    except Exception as e:
        # Handle cases where the output is not valid JSON (e.g., raw error string)
        return jsonify({"status": "error", "message": f"Failed to process signals JSON on server: {e}"}), 500


@app.route('/analyze/')
def analyze_view_empty():
    """Handle empty analyze route elegantly."""
    return render_template_string("""
        <html>
            <body style="font-family: sans-serif; text-align: center; padding-top: 50px;">
                <h1>Instrument Required</h1>
                <p>Please select an instrument from the dashboard or enter one manually.</p>
                <a href="/">Return to Dashboard</a>
            </body>
        </html>
    """)

@app.route('/plot/<path:instrument_key>')
def analyze_view(instrument_key):
    """New Route: Lightweight OHLCV chart for an instrument."""
    if not instrument_key or instrument_key == '/':
         return analyze_view_empty()
    decoded_key = unquote(instrument_key)
    return render_template('lightweight_chart.html', instrument_key=decoded_key)

# -------------------------------------------------------------------
# NEW PLOTTING ROUTES (Modified for OHLC/Lightweight Charts)
# -------------------------------------------------------------------

# @app.route('/plot/<path:instrument_key>')
# def plot_page(instrument_key):
#     """Serves the HTML page to display the chart using Lightweight Charts."""
#     clean_key = unquote(instrument_key)
#     return render_template_string(template, instrument_key=clean_key)





@app.route('/api/chart_data/<path:instrument_key>')
def chart_data_api(instrument_key):
    """API endpoint to return OHLC JSON for the given instrument."""
    clean_key = unquote(instrument_key)

    # 1. Generate OHLC data (JSON string)
    chart_data_json_str = generate_ohlc_data_for_lightweight_charts(clean_key)

    # # 2. Check for internal errors
    # if chart_data_json_str.startswith("Error:"):
    #     # Safely return the error message
    #     return jsonify({"status": "error", "message": chart_data_json_str}), 500

    # 3. Parse and return the JSON data structure
    try:
        # chart_data_json_str should be a valid JSON list of OHLC objects
        chart_data = json.loads(chart_data_json_str)

        # The frontend expects a list of data points, not a wrapped JSON object.
        # We wrap it only if we need status, otherwise just return the data list.
        return jsonify(chart_data)
    except Exception as e:
        # This catches errors if the data generation stub returned something that isn't valid JSON
        return jsonify({"status": "error", "message": f"Failed to parse chart JSON on server: {e}"}), 500


# Template for the chart page (using Lightweight Charts)


template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trading Chart - {{ instrument_key }}</title>
    <script src="https://unpkg.com/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {
            font-family: 'Inter', sans-serif;
            background-color: #1f2937; /* Dark background */
            color: #f3f4f6;
            margin: 0;
            padding: 0;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container {
            width: 90%;
            max-width: 1400px;
            margin-top: 20px;
            padding: 20px;
            background-color: #374151;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }
        #chart-container {
            height: 65vh;
            min-height: 400px;
            width: 100%;
        }
        .loader {
            border: 5px solid #f3f3f3;
            border-top: 5px solid #3b82f6;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .chart-controls {
            margin-top: 10px;
        }
        .chart-controls button {
            padding: 8px 16px;
            margin: 2px;
            cursor: pointer;
            background-color: #3b82f6;
            color: white;
            border: none;
            border-radius: 4px;
            transition: background-color 0.2s;
        }
        .chart-controls button:hover {
            background-color: #2563eb;
        }
        .back-button {
            margin-top: 10px;
            padding: 8px 16px;
            background-color: #4b5563;
            color: white;
            text-decoration: none;
            border-radius: 4px;
        }
    </style>
</head>
<body>
    <a href="/" class="back-button">Back to Home</a>

    <div class="container">
        <h1 class="text-3xl font-bold mb-6 text-gray-100">Chart for: <span id="instrument-key-display">{{ instrument_key }}</span></h1>

        <div id="loading-message" class="text-center p-8">
            <div class="loader"></div>
            <span class="text-lg text-blue-400">Loading chart data...</span>
        </div>

        <div id="error-message" class="hidden bg-red-800 border border-red-500 text-red-200 px-4 py-3 rounded relative mb-4" role="alert">
            <strong class="font-bold">Error!</strong>
            <span class="block sm:inline" id="error-text"></span>
        </div>

        <div id="chart-container" class="hidden"></div>
    </div>

    <div class="chart-controls">
        <button id="zoom-in">+</button>
        <button id="zoom-out">-</button>
        <button id="reset-zoom">Reset Zoom</button>
    </div>

    <script>
        let chart = null;
        let candlestickSeries = null;

        /**
         * Custom Primitive Renderer for TP/SL/Entry Price Dots.
         * This ensures the dots are drawn correctly at the exact price coordinates.
         */
        class CustomPriceMarkerRenderer {
            constructor(time, price, color, series) {
                this.time = time;
                this.price = price;
                this.color = color;
                this.series = series;
            }

            draw(target) {
                const timeScale = target.timeScale;
                const priceScale = target.priceScale;
                const y = priceScale.priceToCoordinate(this.price);
                const x = timeScale.timeToCoordinate(this.time);

                if (x === null || y === null) {
                    return;
                }

                const ctx = target.context;
                const radius = 5;

                ctx.save();
                ctx.beginPath();
                ctx.arc(x, y, radius, 0, Math.PI * 2, false);
                ctx.fillStyle = this.color;
                ctx.fill();
                ctx.closePath();
                ctx.restore();
            }
        }

        class CustomPriceMarker {
            constructor(time, price, color) {
                this.time = time;
                this.price = price;
                this.color = color;
                this.id = crypto.randomUUID();
            }
            attached({ chart, series }) {
                this._chart = chart;
                this._series = series;
            }
            detached() {
                this._chart = null;
                this._series = null;
            }
            renderer() {
                return new CustomPriceMarkerRenderer(this.time, this.price, this.color, this._series);
            }
        }


        // Add this global variable outside the main function block:
let attachedPrimitives = [];

        /**
         * Fetches trade signals and plots both built-in markers (arrows) and custom primitives (dots).
         */
        async function fetchAndPlotSignals(instrumentKey) {
            const signalsApiUrl = `/api/trade_signals/${encodeURIComponent(instrumentKey)}`;
            if (!candlestickSeries) {
                console.warn("Candlestick series not initialized. Cannot plot signals.");
                return;
            }

            try {
                const response = await fetch(signalsApiUrl);
                if (!response.ok) {
                    throw new Error(`Failed to fetch signals: ${response.statusText}`);
                }
                const signals = await response.json();

                if (signals.status === 'error' && signals.message) {
                    console.error('Server error fetching signals:', signals.message);
                    return;
                }

                // IMPORTANT: Remove any previously attached custom primitives (TP/SL dots)
                // before adding new ones to prevent duplicates.
               // 1. CLEAR EXISTING PRIMITIVES (FIX for v4.2.3)
    attachedPrimitives.forEach(primitive => {
        // Use a try-catch, as some old primitives might already be detached
        // if the chart re-rendered, preventing a crash.
        try {
            candlestickSeries.removePrimitive(primitive);
        } catch (e) {
            // console.warn("Could not remove primitive:", e.message);
        }
    });
    // Reset the tracking array
    attachedPrimitives = [];
                const markers = [];

                signals.forEach(signal => {
                    let color, shape, text, position;

                    // --- A. Handle TP/SL/Entry Primitives (Dots) ---
                    // --- A. Handle TP/SL/Entry Primitives (Dots) ---
        if (signal.type.includes('ENTRY') && signal.tp_price && signal.sl_price) {
            const entryTime = signal.time;

            // Create and attach new primitives, and track them
            const tp = new CustomPriceMarker(entryTime, signal.tp_price, 'rgba(39, 245, 80, 1)');
            const sl = new CustomPriceMarker(entryTime, signal.sl_price, 'rgba(242, 25, 25, 1)');
            const entry = new CustomPriceMarker(entryTime, signal.price, '#3b82f6');

            candlestickSeries.attachPrimitive(tp);
            candlestickSeries.attachPrimitive(sl);
            candlestickSeries.attachPrimitive(entry);

            attachedPrimitives.push(tp, sl, entry); // Track them for removal later
        }

                    // --- B. Handle Built-in Markers (Entry/Exit Arrows and Text) ---
                    if (signal.type.includes('ENTRY')) {
                        if (signal.signal.includes('BUY')) {
                            color = '#10b981'; // Green
                            shape = 'arrowUp';
                            text = `BUY ENTRY @ ${signal.price.toFixed(2)}`;
                            position = 'belowBar';
                        } else { // SELL Entry
                            color = '#ef4444'; // Red
                            shape = 'arrowDown';
                            text = `SELL ENTRY @ ${signal.price.toFixed(2)}`;
                            position = 'aboveBar';
                        }
                    } else if (signal.type.includes('EXIT')) {
                        color = '#1d4ed8'; // Blue
                        shape = 'square';
                        // Determine exit direction for context
                        if (signal.signal.includes('SQUARE_OFF') || signal.signal.includes('BUY')) {
                             text = `EXIT (Buy Cover) @ ${signal.price.toFixed(2)}`;
                             position = 'belowBar';
                        } else {
                             text = `EXIT (Sell) @ ${signal.price.toFixed(2)}`;
                             position = 'aboveBar';
                        }
                    }

                    if (shape) {
                        markers.push({
                            time: signal.time,
                            position: position,
                            color: color,
                            shape: shape,
                            text: text,
                        });
                    }
                });

                candlestickSeries.setMarkers(markers);
                console.log(`Plotted ${markers.length} trade markers (arrows).`);

                // Re-fit content to ensure the new primitive price levels are visible
                if (chart) {
                    chart.timeScale().fitContent();
                }

            } catch (error) {
                console.error('Error plotting trade markers:', error);
            }
        }

// --- Zoom Functions ---

// Use barSpacing to change zoom level (works across v4.x)
function zoomIn() {
    if (chart) {
        const timeScale = chart.timeScale();
        const currentOptions = timeScale.options();
        timeScale.applyOptions({
            barSpacing: currentOptions.barSpacing * 1.25 // Zoom in by 25%
        });
    }
}

function zoomOut() {
    if (chart) {
        const timeScale = chart.timeScale();
        const currentOptions = timeScale.options();
        timeScale.applyOptions({
            barSpacing: currentOptions.barSpacing * 0.8 // Zoom out by 20%
        });
    }
}

function resetZoom() {
    if (chart) {
        chart.timeScale().fitContent(); // Automatically fits all data points
    }
}

        // --- Main Initialization ---
        (async function() {
            const instrumentKey = "{{ instrument_key }}";
            const ohlcApiUrl = `/api/chart_data/${encodeURIComponent(instrumentKey)}`;
            const chartContainer = document.getElementById('chart-container');
            const loadingMessage = document.getElementById('loading-message');
            const errorMessageDiv = document.getElementById('error-message');
            const errorText = document.getElementById('error-text');

            function showError(message) {
                loadingMessage.classList.add('hidden');
                errorMessageDiv.classList.remove('hidden');
                errorText.textContent = message;
                chartContainer.classList.add('hidden');
            }

            try {
                // 1. Fetch OHLC Data
                const response = await fetch(ohlcApiUrl);

                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }

                const data = await response.json();

                if (data.status === 'error' && data.message) {
                    showError(data.message);
                    return;
                }

                if (!Array.isArray(data) || data.length === 0) {
                    showError("API returned no valid OHLC data.");
                    return;
                }

                // 2. Initialize Lightweight Chart
                chart = LightweightCharts.createChart(chartContainer, {
                    layout: {
                        background: { type: 'solid', color: '#1f2937' },
                        textColor: '#d1d5db',
                    },
                    grid: {
                        vertLines: { color: '#374151' },
                        horzLines: { color: '#374151' },
                    },
                    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                    rightPriceScale: { borderColor: '#4b5563' },
                    timeScale: {
                        borderColor: '#4b5563',
                        timeVisible: true,
                        secondsVisible: true,
                    },
                    width: chartContainer.clientWidth,
                    height: chartContainer.clientHeight,
                });

                new ResizeObserver(entries => {
                    const { width, height } = entries[0].contentRect;
                    chart.applyOptions({ width, height });
                }).observe(chartContainer);

                // 3. Add Candlestick series and set OHLC data
                candlestickSeries = chart.addCandlestickSeries({
                    upColor: '#10b981',
                    downColor: '#ef4444',
                    borderVisible: false,
                    wickUpColor: '#10b981',
                    wickDownColor: '#ef4444',
                });

                candlestickSeries.setData(data);

                // 4. Fetch and Plot Trade Signals (Markers/Primitives)
                await fetchAndPlotSignals(instrumentKey);

                // 5. Fit the data to the view
                chart.timeScale().fitContent();

                // Hide loading message and show chart
                loadingMessage.classList.add('hidden');
                chartContainer.classList.remove('hidden');

            } catch (error) {
                console.error('Fetch or Render Error:', error);
                showError(`Failed to fetch or render chart. Details: ${error.message}`);
            }
        })();

        // Attach event listeners to the buttons
        document.addEventListener('DOMContentLoaded', () => {
             document.getElementById('zoom-in').addEventListener('click', zoomIn);
             document.getElementById('zoom-out').addEventListener('click', zoomOut);
             document.getElementById('reset-zoom').addEventListener('click', resetZoom);
        });

    </script>
</body>
</html>
"""

if __name__ == '__main__':
    init_db()
    app.run(port = 5080, debug=True)
