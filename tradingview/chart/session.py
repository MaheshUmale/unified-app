"""
Chart Session Module
"""
import json
import time
import asyncio
from typing import Dict, Any, Callable, List, Optional
from ..utils import gen_session_id
from .study import ChartStudy

from tradingview.utils import get_logger
logger = get_logger(__name__)

class ChartSession:
    """
    Class representing a chart session.
    """
    def __init__(self, client):
        """
        Initialize the chart session.

        Args:
            client: Client instance
        """
        self._session_id = gen_session_id('cs')
        self._replay_session_id = gen_session_id('rs')
        self._client = client
        self._study_listeners = {}
        self._deleted = False

        # State events
        self._symbol_resolved_event = asyncio.Event()

        # Replay mode properties
        self._replay_active = False
        self._replay_ok_cb = {}

        # Register sessions
        self._client.sessions[self._session_id] = {
            'type': 'chart',
            'on_data': self._on_session_data
        }

        # Replay session
        self._client.sessions[self._replay_session_id] = {
            'type': 'replay',
            'on_data': self._on_replay_data
        }

        # Initialize data
        self._periods = {}
        self._infos = {}
        self._indexes = {}
        self._timezone = 'Etc/UTC'
        self._symbol = 'BITSTAMP:BTCUSD'
        self._timeframe = '240'

        # Series management
        self._series_created = False
        self._current_series = 0

        # Callbacks
        self._callbacks = {
            'symbol_loaded': [],
            'update': [],
            'replay_loaded': [],
            'replay_resolution': [],
            'replay_end': [],
            'replay_point': [],
            'event': [],
            'error': []
        }

        # Create chart session
        self._create_session_task = asyncio.create_task(self._client.send('chart_create_session', [self._session_id]))

        # Create study factory
        self.Study = lambda indicator: ChartStudy(self, indicator)

    def _on_session_data(self, packet):
        """
        Handle session data.

        Args:
            packet: Data packet
        """
        if self._deleted:
            return

        try:
            # Handle study data
            if isinstance(packet['data'], list) and len(packet['data']) > 1 and isinstance(packet['data'][1], str) and packet['data'][1] in self._study_listeners:
                study_id = packet['data'][1]
                self._study_listeners[study_id](packet)
                return

            # Handle symbol resolution
            if packet['type'] == 'symbol_resolved':
                self._infos = {
                    'series_id': packet['data'][1],
                    **packet['data'][2]
                }

                # Set symbol resolved event
                self._symbol_resolved_event.set()

                self._handle_event('symbol_loaded')
                return

            # Handle timescale updates
            if packet['type'] in ['timescale_update', 'du']:
                changes = []

                if isinstance(packet['data'], list) and len(packet['data']) > 1:
                    data_dict = packet['data'][1]
                    if not isinstance(data_dict, dict):
                        return

                    for k in data_dict.keys():
                        changes.append(k)

                        if k == '$prices':
                            periods = data_dict['$prices']
                            if not periods or 's' not in periods:
                                continue

                            # {"i":2,"v":[1754297700.0,3359.56,3359.925,3358.205,3358.605,696.0]}
                            for p in periods['s']:
                                if 'i' in p and 'v' in p:
                                    if len(p['v']) >= 6:
                                        self._indexes[p['i']] = p['v'][0]
                                        self._periods[p['v'][0]] = {
                                            'time': p['v'][0],
                                            'open': p['v'][1],
                                            'close': p['v'][4],
                                            'max': p['v'][2],
                                            'min': p['v'][3],
                                            'high': p['v'][2],  # Alias
                                            'low': p['v'][3],   # Alias
                                            'volume': round(p['v'][5] * 100) / 100 if len(p['v']) > 5 else 0,
                                        }

                            continue

                        if k in self._study_listeners:
                            self._study_listeners[k](packet)

                    self._handle_event('update', changes)
                    return

            # Handle symbol errors
            if packet['type'] == 'symbol_error':
                self._handle_error(f"({packet['data'][1]}) Symbol error:", packet['data'][2])
                return

            # Handle series errors
            if packet['type'] == 'series_error':
                self._handle_error('Series error:', packet['data'][3])
                return

            # Handle critical errors
            if packet['type'] == 'critical_error':
                name, description = None, None
                if len(packet['data']) > 1:
                    name = packet['data'][1]
                if len(packet['data']) > 2:
                    description = packet['data'][2]
                self._handle_error('Critical error:', name, description)
                return

        except Exception as e:
            self._handle_error(f"Error processing session data: {str(e)}")

    def _on_replay_data(self, packet):
        """
        Handle replay session data.

        Args:
            packet: Data packet
        """
        if self._deleted:
            return

        try:
            if packet['type'] == 'replay_ok':
                # Handle replay confirmation
                if packet['data'][1] in self._replay_ok_cb:
                    self._replay_ok_cb[packet['data'][1]]()
                    del self._replay_ok_cb[packet['data'][1]]
                return

            if packet['type'] == 'replay_instance_id':
                self._handle_event('replay_loaded', packet['data'][1])
                return

            if packet['type'] == 'replay_point':
                self._handle_event('replay_point', packet['data'][1])
                return

            if packet['type'] == 'replay_resolutions':
                self._handle_event('replay_resolution', packet['data'][1], packet['data'][2])
                return

            if packet['type'] == 'replay_data_end':
                self._handle_event('replay_end')
                return

            if packet['type'] == 'critical_error':
                name, description = packet['data'][1], packet['data'][2]
                self._handle_error('Critical error:', name, description)
                return
        except Exception as e:
            self._handle_error(f"Error processing replay data: {str(e)}")

    def _handle_event(self, event, *data):
        """
        Handle events.

        Args:
            event: Event type
            data: Event data
        """
        # Special handling for 'update' event for compatibility
        if event == 'update':
            for callback in self._callbacks[event]:
                try:
                    import inspect
                    if inspect.signature(callback).parameters:
                        callback(*data)
                    else:
                        # If callback doesn't accept args, call directly
                        callback()
                except Exception as e:
                    self._handle_error(f"Callback error: {str(e)}")
        else:
            # Normal handling for other events
            for callback in self._callbacks[event]:
                callback(*data)

        for callback in self._callbacks['event']:
            callback(event, *data)

    def _handle_error(self, *msgs):
        """
        Handle errors.

        Args:
            msgs: Error messages
        """
        if not self._callbacks['error']:
            # Format and log error
            error_msg = " ".join(str(msg) for msg in msgs)
            logger.error(f"ERROR: {error_msg}")
        else:
            self._handle_event('error', *msgs)

    @property
    def session_id(self):
        """Get session ID"""
        return self._session_id

    @property
    def periods(self):
        """Get all K-line periods, sorted descending by time"""
        from types import SimpleNamespace

        # Get sorted period data
        sorted_periods = sorted(self._periods.values(), key=lambda p: p['time'], reverse=True)

        # Convert to attribute-accessible objects
        periods_list = []
        for period_data in sorted_periods:
            period = SimpleNamespace()
            period.time = period_data['time']
            period.open = period_data['open']
            period.high = period_data['high']
            period.max = period_data['high']   # Alias
            period.low = period_data['low']
            period.min = period_data['low']    # Alias
            period.close = period_data['close']
            period.volume = period_data['volume']

            # Add other properties
            for key, value in period_data.items():
                if key not in ['time', 'open', 'high', 'low', 'close', 'volume']:
                    setattr(period, key, value)

            periods_list.append(period)

        return periods_list

    @property
    def infos(self):
        """Get session info as attribute-accessible object"""
        from types import SimpleNamespace
        info_obj = SimpleNamespace()

        # Copy all attributes
        for key, value in self._infos.items():
            setattr(info_obj, key, value)

        # Add common attributes if missing
        if not hasattr(info_obj, 'description'):
            info_obj.description = getattr(info_obj, 'name', self._symbol)

        if not hasattr(info_obj, 'exchange'):
            if ':' in self._symbol:
                info_obj.exchange = self._symbol.split(':')[0]
            else:
                info_obj.exchange = ""

        if not hasattr(info_obj, 'currency_id'):
            info_obj.currency_id = "USD"

        return info_obj

    @property
    def indexes(self):
        """Get indexes"""
        return self._indexes

    def set_market(self, symbol, options=None):
        """
        Set market (compatible with JS version).

        Args:
            symbol: Trading pair code
            options: Loading options
        """
        if self._deleted:
            return
        if options is None:
            options = {}

        # Reset data
        self._periods = {}
        self._symbol_resolved_event.clear()

        # Replay mode handling
        if self._replay_active:
            self._replay_active = False
            asyncio.create_task(self._client.send('replay_delete_session', [self._replay_session_id]))

        # Create async task
        async def load_market():
            try:
                # Ensure session is created
                if hasattr(self, '_create_session_task'):
                    await self._create_session_task

                # Base symbol initialization
                symbol_init = {
                    'symbol': symbol or 'BTCEUR',
                    'adjustment': options.get('adjustment', 'splits'),
                }

                # Optional parameters
                if options.get('backadjustment'):
                    symbol_init['backadjustment'] = 'default'

                if options.get('session'):
                    symbol_init['session'] = options.get('session')

                if options.get('currency'):
                    symbol_init['currency-id'] = options.get('currency')

                # Replay mode processing
                if options.get('replay'):
                    if not self._replay_active:
                        self._replay_active = True
                        await self._client.send('replay_create_session', [self._replay_session_id])

                    await self._client.send('replay_add_series', [
                        self._replay_session_id,
                        'req_replay_addseries',
                        f"={json.dumps(symbol_init)}",
                        options.get('timeframe', '240'),
                    ])

                    await self._client.send('replay_reset', [
                        self._replay_session_id,
                        'req_replay_reset',
                        options['replay'],
                    ])

                # Complex chart type processing
                complex_chart = options.get('type') or options.get('replay')
                chart_init = {} if complex_chart else symbol_init

                if complex_chart:
                    if options.get('replay'):
                        chart_init['replay'] = self._replay_session_id
                    chart_init['symbol'] = symbol_init
                    if options.get('type'):
                        chart_init['type'] = options.get('type')
                        chart_init['inputs'] = options.get('inputs', {})

                # Increment series count
                self._current_series += 1

                # Resolve symbol
                await self._client.send('resolve_symbol', [
                    self._session_id,
                    f"ser_{self._current_series}",
                    f"={json.dumps(chart_init)}",
                ])

                # Set series
                self.set_series(
                    options.get('timeframe', '240'),
                    options.get('range', 100),
                    options.get('to')
                )
            except Exception as e:
                self._handle_error(f"load_market error: {e}")

        # Execute task
        return asyncio.create_task(load_market())

    def set_series(self, timeframe='240', range_val=100, reference=None):
        """
        Set series (compatible with JS version).

        Args:
            timeframe: Timeframe
            range_val: Range value
            reference: Reference time (timestamp)
        """
        if self._deleted:
            return
        if self._current_series == 0:
            self._handle_error('Please set market before setting series')
            return

        # calcRange = !reference ? range : ['bar_count', reference, range];
        calc_range = range_val if reference is None else ['bar_count', reference, range_val]
        self._periods = {}

        async def setup_series():
            try:
                command = 'modify_series' if self._series_created else 'create_series'
                params = [
                    self._session_id,
                    '$prices',
                    's1',
                    f"ser_{self._current_series}",
                    timeframe
                ]

                if not self._series_created:
                    params.append(calc_range)
                else:
                    params.append('')

                await self._client.send(command, params)
                self._series_created = True
            except Exception as e:
                self._handle_error(f"Error setting series: {str(e)}")

        return asyncio.create_task(setup_series())

    async def set_timezone(self, timezone):
        """Set timezone"""
        if self._deleted: return
        self._timezone = timezone
        await self._client.send('set_timezone', [
            self._session_id,
            timezone,
        ])

    async def fetch_more(self, number=1):
        """Fetch more data"""
        if self._deleted: return
        await self._client.send('request_more_data', [self._session_id, 'sds_1', number])

    async def replay_step(self, number=1):
        """Replay step"""
        if self._deleted or not self._replay_active:
            return

        fut = asyncio.Future()
        req_id = gen_session_id('rsq_step')
        await self._client.send('replay_step', [self._replay_session_id, req_id, number])
        self._replay_ok_cb[req_id] = lambda: fut.set_result(None)
        return fut

    async def replay_start(self, interval=1000):
        """Start replay"""
        if self._deleted or not self._replay_active:
            return

        fut = asyncio.Future()
        req_id = gen_session_id('rsq_start')
        await self._client.send('replay_start', [self._replay_session_id, req_id, interval])
        self._replay_ok_cb[req_id] = lambda: fut.set_result(None)
        return fut

    async def replay_stop(self):
        """Stop replay"""
        if self._deleted or not self._replay_active:
            return

        fut = asyncio.Future()
        req_id = gen_session_id('rsq_stop')
        await self._client.send('replay_stop', [self._replay_session_id, req_id])
        self._replay_ok_cb[req_id] = lambda: fut.set_result(None)
        return fut

    def on_symbol_loaded(self, callback):
        self._callbacks['symbol_loaded'].append(callback)
    def on_update(self, callback):
        self._callbacks['update'].append(callback)
    def on_error(self, callback):
        self._callbacks['error'].append(callback)

    async def remove(self):
        """Asynchronously remove session"""
        if self._deleted:
            return
        self._deleted = True

        try:
            await self._client.send('chart_delete_session', [self._session_id])
            if self._replay_active:
                await self._client.send('replay_delete_session', [self._replay_session_id])
        except Exception:
            pass

        if self._session_id in self._client.sessions:
            del self._client.sessions[self._session_id]
        if self._replay_session_id in self._client.sessions:
            del self._client.sessions[self._replay_session_id]

    def delete(self):
        """Delete session (backward compatibility)"""
        asyncio.create_task(self.remove())

    async def get_historical_data(self, symbol: str, timeframe: str, count: int = 500) -> List[Dict]:
        """Convenience method to get historical K-line data"""
        try:
            self._periods = {}
            data_loaded = False
            result_data = []
            data_future = asyncio.get_running_loop().create_future()

            def on_update():
                nonlocal data_loaded, result_data
                if data_loaded or not self._periods:
                    return
                klines = []
                for period in sorted(self._periods.values(), key=lambda p: p['time']):
                    klines.append({
                        'time': period['time'],
                        'open': period['open'],
                        'high': period['high'],
                        'low': period['low'],
                        'close': period['close'],
                        'volume': period.get('volume', 0)
                    })
                result_data = klines
                data_loaded = True
                if not data_future.done():
                    data_future.set_result(klines)

            def on_error(*msgs):
                error_msg = " ".join(str(msg) for msg in msgs)
                if not data_future.done():
                    data_future.set_exception(Exception(error_msg))

            self.on_update(on_update)
            self.on_error(on_error)

            # Format timeframe
            if timeframe.endswith('m'): tf_value = timeframe[:-1]
            elif timeframe.endswith('h'): tf_value = str(int(timeframe[:-1]) * 60)
            else: tf_value = timeframe

            self.set_market(symbol, {'timeframe': tf_value, 'range': count})

            try:
                return await asyncio.wait_for(data_future, timeout=20.0)
            except asyncio.TimeoutError:
                if self._periods:
                    klines = []
                    for period in sorted(self._periods.values(), key=lambda p: p['time']):
                        klines.append({
                            'time': period['time'],
                            'open': period['open'],
                            'high': period['high'],
                            'low': period['low'],
                            'close': period['close'],
                            'volume': period.get('volume', 0)
                        })
                    return klines
                else:
                    raise Exception(f"Timeout fetching data for {symbol}")
        except Exception as e:
            logger.error(f"get_historical_data error: {e}")
            raise e
