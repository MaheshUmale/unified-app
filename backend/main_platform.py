# import eventlet
# eventlet.monkey_patch() # Commented out to prevent conflict with Upstox SDK threading

import json
import os
import sys
import threading
from collections import defaultdict
from datetime import datetime
from urllib.parse import unquote
import glob # For report listing

from flask import Flask, render_template, render_template_string, jsonify, request, send_file
from flask_socketio import SocketIO, emit, join_room
import requests
import upstox_client


from datetime import datetime , timedelta
from CandleCrossStrategy import CandleCrossStrategy, DataPersistor
from database import get_db, get_tick_data_collection, get_oi_collection, get_instruments_collection
import data_engine

# --- Configuration ---
from config import ACCESS_TOKEN

SIGNAL_COLLECTION = "trade_signals"
TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
# --- Import Strategies ---
# Ensure strategies folder is importable


try:
    from strategies.combined_signal_engine import CombinedSignalEngine
except ImportError:
    # If not in path, try appending current dir
    sys.path.append(os.path.join(os.path.dirname(__file__), 'strategies'))

    try:
        from strategies.combined_signal_engine import CombinedSignalEngine
    except ImportError:
        print("Warning: Could not import CombinedSignalEngine.")
        CombinedSignalEngine = None

# Flask & SocketIO Setup
app = Flask(__name__, static_folder='../frontend/dist', static_url_path='')
app.config['SECRET_KEY'] = 'secret!' # Required for SocketIO
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='threading',
    logger=False,  # Suppress Flask-SocketIO logs
    engineio_logger=False,  # Suppress Engine.IO logs (fixes WebSocket error)
    ping_timeout=60,
    ping_interval=25

)

# Database Setup
db = get_db()

# Create indexes for performance
try:
    from database import ensure_indexes
    ensure_indexes()
except Exception as e:
    print(f"Warning: Could not ensure indexes: {e}")

# Inject SocketIO
data_engine.set_socketio(socketio)

# --- Routes ---

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve(path):
    """Serve the React frontend."""
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_file(os.path.join(app.static_folder, path))
    else:
        return send_file(os.path.join(app.static_folder, 'index.html'))

@app.route('/legacy')
def dashboard():
    """Main Dashboard: P&L, Signals, Portfolio."""
    # Fetch data using the existing function
    data = get_live_report_data()

    # If error, return error
    if isinstance(data, tuple):
        return render_template_string("<h1>Error</h1><p>{{ error }}</p>", error=data[0]["error"]), data[1]

    # Fetch available instruments for the datalist
    # Use all subscribed instruments instead of only those with trade data
    available_instruments = []
    instrument_details = {}
    try:
        # Access subscribed_instruments directly from data_engine module
        if data_engine:
            available_instruments = sorted(list(data_engine.subscribed_instruments))
    except Exception as e:
        print(f"[DASHBOARD] Error getting subscribed instruments: {e}")

    # Fallback to instruments with data if subscribed_instruments not available or empty
    if not available_instruments:
        available_instruments = db[SIGNAL_COLLECTION].distinct('instrumentKey')
        if not available_instruments:
            available_instruments = db['tick_data'].distinct('instrumentKey')


    instr_coll = get_instruments_collection()
    project={
        "instrument_key": 1,
        'trading_symbol': 1,
        'underlying_symbol': 1,
        '_id': 0
    }
    filter ={"instrument_key": {"$in": available_instruments}}

    for instrument in available_instruments:
        instrument_details[instrument] = instrument

    print(filter)
    doclist = instr_coll.find(filter=filter,
            projection=project)
    for doc in doclist:
        # print(doc)
        #check if trading_symbol exists and not Null or null,
        # if not use underlying_symbol
        if doc.get('trading_symbol'):
            instrument_name = doc.get('trading_symbol')
            print(instrument_name)
        elif doc.get('underlying_symbol'):
            instrument_name = doc.get('underlying_symbol')
        else:
            instrument_name =  doc.get('instrument_key')

        instrument_details[doc.get('instrument_key')] = instrument_name
    print(instrument_details)
    # Use new dashboard.html template
    return render_template('dashboard.html',
                          data=data,
                          total_trades=len(data['completed_trades']),
                          total_open=len(data['open_positions']),
                          available_instruments=instrument_details)


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

    signals_data = []
    try:
        # Sort by timestamp ascending to ensure correct chronological plotting
        cursor = db[SIGNAL_COLLECTION].find(query).sort("timestamp", 1)


        ist_offset_seconds =   18000 + 1800
        for doc in cursor:
            # print("got data 111")
            if 'timestamp' in doc :
                # Convert MongoDB datetime to UTC Unix timestamp (seconds)
                unix_time_seconds = int(doc['timestamp'] / 1000) +ist_offset_seconds

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

@app.route('/analyze/<path:instrument_key>')
def analyze_view(instrument_key):
    """New Route: Lightweight OHLCV chart for an instrument."""
    if not instrument_key or instrument_key == '/':
         return analyze_view_empty()
    decoded_key = unquote(instrument_key)

    instr_coll = get_instruments_collection()

    instrument_name =decoded_key
    doc = instr_coll.find_one({'instrument_key': decoded_key})
    if doc:
        #check if trading_symbol exists and not Null or null,
        # if not use underlying_symbol
        if doc.get('trading_symbol'):
            instrument_name = doc.get('trading_symbol')
        elif doc.get('underlying_symbol'):
            instrument_name = doc.get('underlying_symbol')
        else:
            instrument_name = decoded_key

    return render_template('lightweight_chart.html', instrument_key=decoded_key, instrument_name=instrument_name)

# --- Report Viewer Routes ---

@app.route('/reports')
def list_reports():
    """List available backtest and EOD reports."""
    # Find all HTML reports
    reports = glob.glob('backtest_report_*.html') + glob.glob('ORDER_FLOW_eod_*.html')
    reports.sort(reverse=True) # Newest first

    report_list_html = """
    <html>
    <head>
        <title>Reports</title>
        <link href="https://cdn.tailwindcss.com" rel="stylesheet">
        <style>body { font-family: sans-serif; padding: 20px; }</style>
    </head>
    <body class="bg-gray-50 p-10">
        <div class="max-w-4xl mx-auto bg-white p-8 rounded shadow">
            <h1 class="text-2xl font-bold mb-6">Available Reports</h1>
            <ul class="space-y-4">
    """

    if not reports:
        report_list_html += "<li class='text-gray-500'>No reports found. Run a backtest first.</li>"
    else:
        for r in reports:
            report_list_html += f"<li><a href='/reports/{r}' class='text-blue-600 hover:underline block p-2 hover:bg-gray-50 rounded border'>{r}</a></li>"

    report_list_html += """
            </ul>
            <div class="mt-6">
                <a href="/" class="text-gray-600 hover:text-gray-900">&larr; Back to Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(report_list_html)

@app.route('/reports/<path:filename>')
def view_report(filename):
    """Serve a specific report file."""
    # Security: Ensure filename is safe (basic check)
    if '..' in filename or filename.startswith('/'):
        return "Invalid filename", 400
    try:
        return send_file(filename)
    except Exception as e:
        return f"Error: {e}", 404

# --- API Routes (Legacy + New) ---

@app.route('/api/live_pnl')
def live_pnl_api():
    data = get_live_report_data()
    if isinstance(data, tuple):
        return jsonify(data[0]), data[1]
    return jsonify(data)

@app.route('/api/replay_range/<instrument_key>')
def get_replay_range(instrument_key):
    """Get min/max date range for available data"""
    if data_engine is not None:
        try:
            collection = get_tick_data_collection()

            # Get first and last documents
            first_doc = collection.find({'instrumentKey': instrument_key}).sort('_id', 1).limit(1)
            last_doc = collection.find({'instrumentKey': instrument_key}).sort('_id', -1).limit(1)

            first_doc = list(first_doc)
            last_doc = list(last_doc)

            if not first_doc or not last_doc:
                return jsonify({'error': 'No data found for this instrument'}), 404

            def get_timestamp(doc):
                try:
                    ff = doc.get('fullFeed', {}).get('marketFF', {})
                    ohlc_data = ff.get('marketOHLC', {}).get('ohlc', [])
                    if ohlc_data:
                        return int(ohlc_data[0].get('ts', 0)) / 1000.0
                    return int(ff.get('ltpc', {}).get('ltt', 0)) / 1000.0
                except:
                    return None

            min_ts = get_timestamp(first_doc[0])
            max_ts = get_timestamp(last_doc[0])

            if min_ts and max_ts:
                from datetime import datetime
                return jsonify({
                    'min_date': datetime.fromtimestamp(min_ts).strftime('%Y-%m-%dT%H:%M'),
                    'max_date': datetime.fromtimestamp(max_ts).strftime('%Y-%m-%dT%H:%M'),
                    'min_timestamp': int(min_ts),
                    'max_timestamp': int(max_ts)
                })

            return jsonify({'error': 'Could not extract timestamps'}), 500
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Data engine not available'}), 500

# --- API Routes (Additional) ---

@app.route('/api/instruments')
def get_instruments():
    """Return list of instrument keys with human readable names."""
    if data_engine is not None:
        try:
            collection = get_tick_data_collection()
            instrument_keys = collection.distinct('instrumentKey')
            instruments = []
            for key in instrument_keys:
                instr_doc = get_instruments_collection().find_one({'instrument_key': key})
                name = key
                if instr_doc:
                    #check if trading_symbol exists and not null or None
                    # if not then check underlying_symbol exist and is not None/null
                    if instr_doc.get('trading_symbol'):
                        name = instr_doc.get('trading_symbol')
                    elif instr_doc.get('underlying_symbol'):
                        name = instr_doc.get('underlying_symbol')
                    else:
                        name = key
                instruments.append({'key': key, 'name': name})
            return jsonify(instruments)
        except Exception as e:
            print(f"Error fetching instruments: {e}")
            return jsonify({'error': 'Failed to fetch instruments'}), 500
    return jsonify({'error': 'Data engine not available'}), 500

@app.route('/api/oi_data/<instrument_key>')
def get_oi_data_route(instrument_key):
    """Return latest OI data for the given instrument."""
    if data_engine is not None:
        try:
            instruments_coll = get_instruments_collection()
            oi_coll = get_oi_collection()
            instrument = instruments_coll.find_one({'instrument_key': instrument_key})
            if not instrument:
                return jsonify({'error': 'Instrument not found'}), 404

            #check if trading_symbol exists and not null or None
            # if not then check underlying_symbol exist and is not None/null
            if instrument.get('trading_symbol'):
                symbol = instrument.get('trading_symbol')
            elif instrument.get('underlying_symbol'):
                symbol = instrument.get('underlying_symbol')
            else:
                return jsonify({'error': 'Trading symbol or underlying symbol not found'}), 404

            oi_doc = oi_coll.find_one({'symbol': symbol}, sort=[('date', -1), ('timestamp', -1)])
            if not oi_doc:
                return jsonify({'error': 'OI data not found'}), 404
            return jsonify({
                'open_interest': oi_doc.get('call_oi', 0),
                'oi_change': oi_doc.get('change_in_call_oi', 0)
            })
        except Exception as e:
            print(f"Error fetching OI data: {e}")
            return jsonify({'error': 'Failed to fetch OI data'}), 500
    return jsonify({'error': 'Data engine not available'}), 500

# --- SocketIO Events ---

@socketio.on('connect')
def handle_connect():
    print("Client Connected to Main Platform WS")

@socketio.on('subscribe')
def handle_frontend_subscribe(data):
    """Handles subscription request from the React frontend."""
    instrument_keys = data.get('instrumentKeys', [])
    if not instrument_keys:
        return

    print(f"[SOCKET] Client subscribing to keys: {instrument_keys}")

    for instrument_key in instrument_keys:
        handle_subscribe_instrument({'instrument_key': instrument_key})

@socketio.on('subscribe_to_instrument')
def handle_subscribe_instrument(data):
    """Subscribe to a new instrument, join room, and send its history."""
    # Extract instrument_key from the data object
    instrument_key = data.get('instrument_key') if isinstance(data, dict) else data

    if not instrument_key:
        print("[SOCKET] Error: No instrument_key provided in subscription request")
        return

    print(f"[SOCKET] Client subscribing to: {instrument_key}")
    join_room(instrument_key)

    if data_engine:
        data_engine.subscribe_instrument(instrument_key)

        # OPTIMIZED: Try to use pre-aggregated OHLC from Upstox API first
        history_sent = False
        try:
            from lightweight_history import load_lightweight_history
            history = load_lightweight_history(instrument_key)
            if history:
                print(f"[SOCKET] Using optimized pre-aggregated OHLC ({len(history)} bars)")
                emit('footprint_history', history)
                history_sent = True
            else:
                # Fallback to tick-based aggregation
                print(f"[SOCKET] Falling back to tick-based aggregation")
                history = data_engine.load_intraday_data(instrument_key)
                if history:
                    emit('footprint_history', history)
                    history_sent = True
        except Exception as e:
            print(f"[SOCKET] Error loading optimized history: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to tick-based aggregation
            history = data_engine.load_intraday_data(instrument_key)
            if history:
                emit('footprint_history', history)
                history_sent = True

        # IMPORTANT: Only send current bar AFTER history is sent to maintain order
        if history_sent and hasattr(data_engine, 'active_bars') and instrument_key in data_engine.active_bars:
            current_bar = data_engine.active_bars[instrument_key]
            if current_bar:
                print(f"[SOCKET] Sending current active bar for {instrument_key}: {current_bar.get('ts')}")
                emit('footprint_update', current_bar)

@socketio.on('replay_market_data')
def handle_replay(data):
    print(f"Replay requested: {data}")
    instrument_key = data.get('instrument_key')
    speed = int(data.get('speed', 100))
    start_ts = data.get('start_ts')
    timeframe = int(data.get('timeframe', 1))

    if data_engine:
        data_engine.start_replay_thread(instrument_key, speed, start_ts, timeframe)

@socketio.on('stop_replay')
def handle_stop_replay():
    print("Stop replay requested")
    if data_engine:
        data_engine.stop_active_replay()

# --- Helpers ---

def get_live_report_data():
    """
    Queries MongoDB for all trade signals today.
    Fixed to match actual signal structure with position_after, stop_loss_price, etc.
    Added: Instrument Name Lookup from Instruments Collection.
    """
    if db is None:
        return {"error": "Database not connected."}, 500

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    signals = list(db[SIGNAL_COLLECTION].find({
        "timestamp": {"$gte": today.timestamp()}
    }).sort("timestamp", 1))

    # Pre-fetch instrument names to optimize
    # We will query on demand or build a cache if many.
    # For simplicitly, let's query on demand since list is small.
    # Or fetch all relevant keys first.

    trades = defaultdict(lambda: {
        'status': 'OPEN',
        'entry_time': None,
        'entry_timestamp': 0,
        'exit_timestamp': 0,
        'instrument': None,
        'instrument_name': None, # New field
        'pnl': 0,
        'entry_price': 0,
        'exit_price': 0,
        'quantity': 50,  # Default qty (can be updated from signal if available)
        'side': '',
        'stop_loss': 0,
        'take_profit': 0,
        'strategy': ''
    })
    total_pnl = 0

    instr_coll = get_instruments_collection()

    for signal in signals:
        trade_id = signal.get('trade_id')
        # Robust key retrieval to handle different signal formats
        instrument = signal.get('instrumentKey') or signal.get('instrument_key') or signal.get('instrument')

        # Name resolution
        instrument_name = instrument
        if instrument:
            doc = instr_coll.find_one({'instrument_key': instrument})
            if doc:
                #check if trading_symbol exists and not Null or null,
                # if not use underlying_symbol
                if doc.get('trading_symbol'):
                    instrument_name = doc.get('trading_symbol')
                elif doc.get('underlying_symbol'):
                    instrument_name = doc.get('underlying_symbol')
                else:
                    instrument_name = instrument

        if signal['type'] == 'ENTRY':
            # Extract side from position_after field (BUY/SELL)
            position = signal.get('position_after', signal.get('signal', 'UNKNOWN'))
            side = 'LONG' if position == 'BUY' else 'SHORT' if position == 'SELL' else position
            # print(signal['timestamp']
            try:
                ts = datetime.fromtimestamp(signal['timestamp']/1000).strftime(TIME_FORMAT)
            except Exception as e:
                ts = "N/A"
                print(signal)
                print(f"Error converting timestamp: {e}")
                import traceback
                traceback.print_exc()

            trades[trade_id].update({
                'status': 'OPEN',
                'entry_time': ts ,#datetime.fromtimestamp(signal['timestamp']).strftime(TIME_FORMAT),
                'entry_timestamp': int(signal['timestamp'] * 1000),  # For chart markers
                'instrument': instrument,
                'instrument_name': instrument_name,
                'entry_price': signal.get('ltp', 0),
                'quantity': signal.get('quantity', 50),  # Default 50 if not specified
                'side': side,
                'stop_loss': signal.get('sl_price', 0),
                'take_profit': signal.get('tp_price', 0),
                'strategy': signal.get('strategy', 'UNKNOWN')
            })

        elif signal['type'] == 'EXIT':
            pnl = signal.get('pnl', 0)
            position = signal.get('position_closed', trades[trade_id].get('side', 'UNKNOWN'))
            side = 'LONG' if position == 'BUY' else 'SHORT' if position == 'SELL' else position

            trades[trade_id]['status'] = 'COMPLETED'
            trades[trade_id]['exit_time'] = datetime.fromtimestamp(signal['timestamp']/1000).strftime(TIME_FORMAT)
            trades[trade_id]['exit_timestamp'] = int(signal['timestamp'] * 1000)  # For chart markers
            trades[trade_id]['pnl'] = pnl
            trades[trade_id]['exit_price'] = signal.get('exit_price', signal.get('ltp', 0))
            trades[trade_id]['reason'] = signal.get('reason_code', 'EXIT')
            trades[trade_id]['side'] = side  # Update side from exit signal if needed
            # Ensure name is set if entry missing (rare)
            if not trades[trade_id]['instrument_name']:
                 trades[trade_id]['instrument_name'] = instrument_name
            total_pnl += pnl

    open_positions = []
    completed_trades = []

    for trade_id, trade_data in trades.items():
        if trade_data['status'] == 'OPEN':
            open_positions.append({
                'id': trade_id,
                'instrument': trade_data['instrument'],
                'instrument_name': trade_data['instrument_name'],
                'side': trade_data['side'],
                'entry_time': trade_data['entry_time'],
                'entry_price': trade_data['entry_price'],
                'quantity': trade_data['quantity'],
                'stop_loss': trade_data['stop_loss'],
                'take_profit': trade_data['take_profit'],
                'strategy': trade_data['strategy'],
                'entry_timestamp': trade_data['entry_timestamp']
            })
        elif trade_data['status'] == 'COMPLETED':
            completed_trades.append({
                'id': trade_id,
                'instrument': trade_data['instrument'],
                'side': trade_data['side'],
                'entry_time': trade_data['entry_time'],
                'exit_time': trade_data['exit_time'],
                'entry_price': trade_data['entry_price'],
                'exit_price': trade_data['exit_price'],
                'quantity': trade_data['quantity'],
                'stop_loss': trade_data['stop_loss'],
                'reason': trade_data['reason'],
                'pnl': trade_data['pnl'],
                'strategy': trade_data['strategy'],
                'entry_timestamp': trade_data['entry_timestamp'],
                'exit_timestamp': trade_data['exit_timestamp']
            })

    # Summary by instrument
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


if __name__ == '__main__':
    # Start the Upstox WebSocket Background Thread
    # Note: In a real app, manage this thread's lifecycle better.
    if data_engine:
        # Example instruments to subscribe to on startup.
        # Ideally, this comes from an active watchlist or open positions.
        # initial_instruments = ["NSE_EQ|INE002A01018"]
        # initial_instruments = ["NSE_EQ|INE002A01018"] # Reliance

        # initial_instruments =["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank","NSE_EQ|INE585B01010","NSE_EQ|INE139A01034","NSE_EQ|INE1NPP01017","NSE_EQ|INE917I01010","NSE_EQ|INE267A01025","NSE_EQ|INE466L01038","NSE_EQ|INE070A01015","NSE_EQ|INE749A01030","NSE_EQ|INE171Z01026","NSE_EQ|INE591G01025","NSE_EQ|INE160A01022","NSE_EQ|INE814H01029","NSE_EQ|INE102D01028","NSE_EQ|INE134E01011","NSE_EQ|INE009A01021","NSE_EQ|INE376G01013","NSE_EQ|INE619A01035","NSE_EQ|INE465A01025","NSE_EQ|INE540L01014","NSE_EQ|INE237A01028","NSE_EQ|INE361B01024","NSE_EQ|INE811K01011","NSE_EQ|INE01EA01019","NSE_EQ|INE030A01027","NSE_EQ|INE476A01022","NSE_EQ|INE721A01047","NSE_EQ|INE028A01039","NSE_EQ|INE670K01029","NSE_EQ|INE158A01026","NSE_EQ|INE123W01016","NSE_EQ|INE192A01025","NSE_EQ|INE118A01012","NSE_EQ|INE674K01013","NSE_EQ|INE094A01015","NSE_EQ|INE528G01035","NSE_EQ|INE093I01010","NSE_EQ|INE073K01018","NSE_EQ|INE006I01046","NSE_EQ|INE142M01025","NSE_EQ|INE169A01031","NSE_EQ|INE849A01020","NSE_EQ|INE669C01036","NSE_EQ|INE216A01030","NSE_EQ|INE111A01025","NSE_EQ|INE062A01020","NSE_EQ|INE081A01020","NSE_EQ|INE883A01011","NSE_EQ|INE075A01022","NSE_EQ|INE498L01015","NSE_EQ|INE377N01017","NSE_EQ|INE484J01027","NSE_EQ|INE205A01025","NSE_EQ|INE027H01010","NSE_EQ|INE121A01024","NSE_EQ|INE974X01010","NSE_EQ|INE854D01024","NSE_EQ|INE742F01042","NSE_EQ|INE226A01021","NSE_EQ|INE047A01021","NSE_EQ|INE326A01037","NSE_EQ|INE584A01023","NSE_EQ|INE414G01012","NSE_EQ|INE669E01016","NSE_EQ|INE211B01039","NSE_EQ|INE813H01021","NSE_EQ|INE213A01029","NSE_EQ|INE335Y01020","NSE_EQ|INE931S01010","NSE_EQ|INE704P01025","NSE_EQ|INE053F01010","NSE_EQ|INE127D01025","NSE_EQ|INE021A01026","NSE_EQ|INE356A01018","NSE_EQ|INE733E01010","NSE_EQ|INE115A01026","NSE_EQ|INE702C01027","NSE_EQ|INE388Y01029","NSE_EQ|INE117A01022","NSE_EQ|INE239A01024","NSE_EQ|INE437A01024","NSE_EQ|INE245A01021","NSE_EQ|INE053A01029","NSE_EQ|INE196A01026","NSE_EQ|INE121J01017","NSE_EQ|INE399L01023","NSE_EQ|INE121E01018","NSE_EQ|INE019A01038","NSE_EQ|INE151A01013","NSE_EQ|INE522F01014","NSE_EQ|INE296A01032","NSE_EQ|INE066F01020","NSE_EQ|INE002A01018","NSE_EQ|INE203G01027","NSE_EQ|INE467B01029","NSE_EQ|INE0ONG01011","NSE_EQ|INE079A01024","NSE_EQ|INE0J1Y01017","NSE_EQ|INE260B01028","NSE_EQ|INE040A01034","NSE_EQ|INE121A08PJ0","NSE_EQ|INE603J01030","NSE_EQ|INE202E01016","NSE_EQ|INE663F01032","NSE_EQ|INE066A01021","NSE_EQ|INE752E01010","NSE_EQ|INE271C01023","NSE_EQ|INE318A01026","NSE_EQ|INE918I01026","NSE_EQ|INE758E01017","NSE_EQ|INE089A01031","NSE_EQ|INE848E01016","NSE_EQ|INE982J01020","NSE_EQ|INE761H01022","NSE_EQ|INE494B01023","NSE_EQ|INE646L01027","NSE_EQ|INE0V6F01027","NSE_EQ|INE010B01027","NSE_EQ|INE302A01020","NSE_EQ|INE634S01028","NSE_EQ|INE397D01024","NSE_EQ|INE192R01011","NSE_EQ|INE775A08105","NSE_EQ|INE059A01026","NSE_EQ|INE377Y01014","NSE_EQ|INE343G01021","NSE_EQ|INE797F01020","NSE_EQ|INE180A01020","NSE_EQ|INE949L01017","NSE_EQ|INE881D01027","NSE_EQ|INE795G01014","NSE_EQ|INE280A01028","NSE_EQ|INE298A01020","NSE_EQ|INE155A01022","NSE_EQ|INE274J01014","NSE_EQ|INE012A01025","NSE_EQ|INE095A01012","NSE_EQ|INE562A01011","NSE_EQ|INE195A01028","NSE_EQ|INE118H01025","NSE_EQ|INE364U01010","NSE_EQ|INE238A01034","NSE_EQ|INE044A01036","NSE_EQ|INE379A01028","NSE_EQ|INE338I01027","NSE_EQ|INE935N01020","NSE_EQ|INE038A01020","NSE_EQ|INE031A01017","NSE_EQ|INE242A01010","NSE_EQ|INE692A01016","NSE_EQ|INE04I401011","NSE_EQ|INE061F01013","NSE_EQ|INE263A01024","NSE_EQ|INE020B01018","NSE_EQ|INE685A01028","NSE_EQ|INE647A01010","NSE_EQ|INE860A01027","NSE_EQ|INE0BS701011","NSE_EQ|INE00H001014","NSE_EQ|INE171A01029","NSE_EQ|INE262H01021","NSE_EQ|INE084A01016","NSE_EQ|INE775A01035","NSE_EQ|INE878B01027","NSE_EQ|INE018E01016","NSE_EQ|INE776C01039","NSE_EQ|INE417T01026","NSE_EQ|INE415G01027","NSE_EQ|INE821I01022","NSE_EQ|INE323A01026","NSE_EQ|INE214T01019","NSE_EQ|INE176B01034","NSE_EQ|INE249Z01020","NSE_EQ|INE343H01029","NSE_EQ|INE758T01015","NSE_EQ|INE154A01025","NSE_EQ|INE455K01017","NSE_EQ|INE406A01037","NSE_EQ|INE101A01026","NSE_EQ|INE208A01029","NSE_EQ|INE303R01014","NSE_EQ|INE090A01021","NSE_EQ|INE472A01039","NSE_EQ|INE628A01036","NSE_EQ|INE040H01021","NSE_EQ|INE018A01030","NSE_EQ|INE092T01019","NSE_EQ|INE067A01029","NSE_EQ|INE423A01024","NSE_EQ|INE259A01022","NSE_EQ|INE07Y701011","NSE_EQ|INE765G01017","NSE_EQ|INE257A01026","NSE_EQ|INE774D01024","NSE_EQ|INE129A01019","NSE_EQ|INE481G01011","NSE_EQ|INE114A01011","NSE_EQ|INE774D08MG3","NSE_EQ|INE935A01035","NSE_EQ|INE003A01024","NSE_EQ|INE029A01011","NSE_EQ|INE670A01012","NSE_EQ|INE200M01039","NSE_EQ|INE016A01026"]

        # NiftyFO = ["NSE_FO|65621","NSE_FO|65622","NSE_FO|65623","NSE_FO|65634","NSE_FO|71403","NSE_FO|65635","NSE_FO|71399","NSE_FO|65628","NSE_FO|65639","NSE_FO|65629"]
        # BN_FO =["NSE_FO|51420","NSE_FO|51421","NSE_FO|51414","NSE_FO|51415","NSE_FO|51416","NSE_FO|51417","NSE_FO|51440","NSE_FO|51439","NSE_FO|51460","NSE_FO|51461","NSE_FO|51475","NSE_FO|51476"]


        # append all 3 arrays into one
        all_instruments = data_engine.subscribed_instruments





        print("Subscribing to initial instruments:", all_instruments)
        data_engine.subscribed_instruments.update(all_instruments)
        data_engine.start_websocket_thread(ACCESS_TOKEN, all_instruments)

        # ###--- Initialize Strategies ---
        if CombinedSignalEngine:
            class DummyWriter:
                def write(self, s): pass

            dummy_writer = DummyWriter()

            for key in all_instruments:
                print(f"Initializing Combined Strategy for {key}...")
                strategy = CombinedSignalEngine(
                    instrument_key=key,
                    csv_writer=dummy_writer,
                    obi_throttle_sec=1.0 # 1s throttling
                )
                data_engine.register_strategy(key, strategy)

        if CandleCrossStrategy:
            class DummyWriter:
                def write(self, s): pass

            dummy_writer = DummyWriter()
            persistor_instance = DataPersistor() # Create a single persistor instance
            for key in all_instruments:
                print(f"Initializing Combined Strategy for {key}...")
                # 2. Connect to the database


                # 3. Initialize the Strategy, passing the persistor
                strategy = CandleCrossStrategy(
                    instrument_key="" + key ,
                    csv_writer=None, # Mock CSV writer
                    persistor=persistor_instance, # <-- Inject the persistor
                    is_backtesting=False
                )
                data_engine.register_strategy(key, strategy)




    print("Starting Unified Platform on port 5050...")
    socketio.run(app, debug=False, use_reloader=False, host='0.0.0.0', port=5050, allow_unsafe_werkzeug=True)
