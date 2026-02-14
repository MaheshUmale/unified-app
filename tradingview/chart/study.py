"""
Chart Indicator Study Module
"""
import json
import asyncio
from typing import Dict, Any, Callable, List, Optional
from ..utils import gen_session_id
from ..protocol import parse_compressed
from .graphic_parser import graphic_parse

from tradingview.utils import get_logger
logger = get_logger(__name__)

class ChartStudy:
    """
    Class representing an indicator study on a chart.
    """
    def __init__(self, chart_session, indicator):
        """
        Initialize a chart indicator study.

        Args:
            chart_session: Parent chart session
            indicator: Indicator object
        """
        from ..classes import PineIndicator, BuiltInIndicator

        if not isinstance(indicator, (PineIndicator, BuiltInIndicator)):
            raise TypeError("Indicator must be an instance of PineIndicator or BuiltInIndicator. "
                           "Use 'TradingView.get_indicator()'.")

        self.instance = indicator
        self._study_id = gen_session_id('st')
        self._study_listeners = chart_session._study_listeners
        self._chart_session = chart_session

        # State
        self._periods = {}
        self._indexes = []
        self._graphic = {}
        self._strategy_report = {
            'trades': [],
            'history': {},
            'performance': {},
        }

        # Callbacks
        self._callbacks = {
            'study_completed': [],
            'update': [],
            'event': [],
            'error': []
        }

        # Register listener
        self._study_listeners[self._study_id] = self._handle_study_data

        # Dispatch creation request - Wait for session and symbol resolution
        async def create_study_async():
            try:
                # Wait for session creation task
                if hasattr(chart_session, '_create_session_task'):
                    await chart_session._create_session_task

                # Wait for symbol resolution - Crucial for create_study to succeed
                if hasattr(chart_session, '_symbol_resolved_event'):
                    try:
                        await asyncio.wait_for(chart_session._symbol_resolved_event.wait(), timeout=10.0)
                    except asyncio.TimeoutError:
                        logger.warning(f"Timeout waiting for symbol resolution before creating study {self._study_id}")

                # Check if session ID is valid
                if not chart_session._session_id:
                    self._handle_error("Chart session ID is missing")
                    return

                await chart_session._client.send('create_study', [
                    chart_session._session_id,
                    self._study_id,
                    'st1',
                    '$prices',
                    self.instance.type,
                    self._get_inputs(self.instance),
                ])
            except Exception as e:
                self._handle_error(f"Failed to dispatch create_study: {str(e)}")

        self._create_study_task = asyncio.create_task(create_study_async())

    def _get_inputs(self, options):
        """
        Generate input parameters for the indicator.

        Args:
            options: Indicator object

        Returns:
            dict: Input parameters
        """
        from ..classes import PineIndicator

        if isinstance(options, PineIndicator):
            pine_inputs = {'text': options.script}

            if options.pine_id:
                pine_inputs['pineId'] = options.pine_id

            if options.pine_version:
                pine_inputs['pineVersion'] = options.pine_version

            for n, (input_id, input_obj) in enumerate(options.inputs.items()):
                pine_inputs[input_id] = {
                    'v': input_obj['value'] if input_obj['type'] != 'color' else n,
                    'f': input_obj.get('isFake', False),
                    't': input_obj['type']
                }

            return pine_inputs

        return options.options

    async def _handle_study_data(self, packet):
        """
        Process incoming study data packets.

        Args:
            packet: Data packet
        """
        # Study lifecycle
        if packet['type'] == 'study_completed':
            self._handle_event('study_completed')
            return

        # Data updates
        if packet['type'] in ['timescale_update', 'du']:
            changes = []
            data = packet['data'][1].get(self._study_id, {})

            # Process plot values
            if data and data.get('st') and data['st'][0]:
                for p in data['st']:
                    period = {}

                    for i, plot in enumerate(p['v']):
                        if not hasattr(self.instance, 'plots') or not self.instance.plots:
                            period['$time' if i == 0 else f'plot_{i-1}'] = plot
                        else:
                            plot_name = '$time' if i == 0 else self.instance.plots.get(f'plot_{i-1}')
                            if plot_name and plot_name not in period:
                                period[plot_name] = plot
                            else:
                                period[f'plot_{i-1}'] = plot

                    self._periods[p['v'][0]] = period

                changes.append('plots')

            # Process graphic data
            if data.get('ns') and data['ns'].get('d'):
                try:
                    parsed = json.loads(data['ns'].get('d', '{}'))

                    if parsed.get('graphicsCmds'):
                        # Handle erasure
                        if parsed['graphicsCmds'].get('erase'):
                            for instruction in parsed['graphicsCmds']['erase']:
                                if instruction['action'] == 'all':
                                    if not instruction.get('type'):
                                        self._graphic = {}
                                    else:
                                        if instruction['type'] in self._graphic:
                                            del self._graphic[instruction['type']]
                                elif instruction['action'] == 'one':
                                    if instruction['type'] in self._graphic and instruction['id'] in self._graphic[instruction['type']]:
                                        del self._graphic[instruction['type']][instruction['id']]

                        # Handle creation
                        if parsed['graphicsCmds'].get('create'):
                            for draw_type, groups in parsed['graphicsCmds']['create'].items():
                                if draw_type not in self._graphic:
                                    self._graphic[draw_type] = {}

                                for group in groups:
                                    if isinstance(group, dict) and 'data' in group:
                                        for item in group['data']:
                                            self._graphic[draw_type][item['id']] = item

                        changes.append('graphic')

                    # Update strategy reports
                    if parsed.get('dataCompressed'):
                        try:
                            decompressed = await parse_compressed(parsed['dataCompressed'])
                            if decompressed and decompressed.get('report'):
                                await self._update_strategy_report(decompressed['report'], changes)
                        except Exception as e:
                            self._handle_error(f"Failed to parse compressed data: {str(e)}")

                    if parsed.get('data') and parsed['data'].get('report'):
                        await self._update_strategy_report(parsed['data']['report'], changes)

                except json.JSONDecodeError:
                    self._handle_error("JSON decode error in study data")

            # Update indexes
            if data.get('ns') and data['ns'].get('indexes') and isinstance(data['ns']['indexes'], list):
                self._indexes = data['ns']['indexes']

            # Dispatch update events
            if changes:
                self._handle_event('update', changes)

        # Error handling
        elif packet['type'] == 'study_error':
            error_msg = f"Study error: {packet['data'][3]}" if len(packet['data']) > 3 else "Unknown study error"
            self._handle_error(error_msg)

    async def _update_strategy_report(self, report, changes):
        """
        Merge strategy report data.

        Args:
            report: New report data
            changes: Tracked changes
        """
        if report.get('currency'):
            self._strategy_report['currency'] = report['currency']
            changes.append('report.currency')

        if report.get('settings'):
            self._strategy_report['settings'] = report['settings']
            changes.append('report.settings')

        if report.get('performance'):
            self._strategy_report['performance'] = report['performance']
            changes.append('report.perf')

        if report.get('trades'):
            self._strategy_report['trades'] = self._parse_trades(report['trades'])
            changes.append('report.trades')

        if report.get('equity'):
            self._strategy_report['history'] = {
                'buyHold': report.get('buyHold'),
                'buyHoldPercent': report.get('buyHoldPercent'),
                'drawDown': report.get('drawDown'),
                'drawDownPercent': report.get('drawDownPercent'),
                'equity': report.get('equity'),
                'equityPercent': report.get('equityPercent'),
            }
            changes.append('report.history')

    def _parse_trades(self, trades):
        """
        Normalize strategy trade data.

        Args:
            trades: Raw trade list

        Returns:
            list: Normalized trade list
        """
        return [
            {
                'entry': {
                    'name': t['e']['c'],
                    'type': 'short' if t['e']['tp'][0] == 's' else 'long',
                    'value': t['e']['p'],
                    'time': t['e']['tm'],
                },
                'exit': {
                    'name': t['x']['c'],
                    'value': t['x']['p'],
                    'time': t['x']['tm'],
                },
                'quantity': t['q'],
                'profit': t['tp'],
                'cumulative': t['cp'],
                'runup': t['rn'],
                'drawdown': t['dd'],
            }
            for t in reversed(trades)
        ]

    def _handle_event(self, event, *data):
        """
        Broadcast events to subscribers.

        Args:
            event: Event type
            data: Payloads
        """
        for callback in self._callbacks[event]:
            callback(*data)

        for callback in self._callbacks['event']:
            callback(event, *data)

    def _handle_error(self, *msgs):
        """
        Handle and log errors.

        Args:
            msgs: Error messages
        """
        if not self._callbacks['error']:
            error_msg = " ".join(str(msg) for msg in msgs)
            logger.error(f"ERROR: {error_msg}")
        else:
            self._handle_event('error', *msgs)

    @property
    def periods(self):
        """Get study period data as objects."""
        from types import SimpleNamespace

        periods_list = []
        for period_data in sorted(self._periods.values(), key=lambda p: p.get('$time', 0), reverse=True):
            period = SimpleNamespace()
            period.time = period_data.get('$time', 0)

            # Default initialized plots
            for i in range(10):
                setattr(period, f'plot_{i}', None)

            for key, value in period_data.items():
                if key != '$time':
                    setattr(period, key, value)

            periods_list.append(period)

        return periods_list

    @property
    def graphic(self):
        """Retrieve parsed graphic data."""
        translator = {}
        chart_indexes = getattr(self._chart_session, 'indexes', {})
        sorted_indexes = sorted(chart_indexes.keys(), key=lambda k: chart_indexes[k], reverse=True)

        for n, r in enumerate(sorted_indexes):
            translator[r] = n

        indexes = [translator.get(i, 0) for i in self._indexes]
        return graphic_parse(self._graphic, indexes)

    @property
    def strategy_report(self):
        """Retrieve latest strategy results."""
        return self._strategy_report

    async def set_indicator(self, indicator):
        """
        Update the study with a new indicator configuration.

        Args:
            indicator: New indicator instance
        """
        from ..classes import PineIndicator, BuiltInIndicator

        if not isinstance(indicator, (PineIndicator, BuiltInIndicator)):
            raise TypeError("Indicator must be an instance of PineIndicator or BuiltInIndicator.")

        self.instance = indicator

        await self._chart_session._client.send('modify_study', [
            self._chart_session._session_id,
            self._study_id,
            'st1',
            self._get_inputs(self.instance),
        ])

    def on_ready(self, callback):
        """Register callback for completion."""
        self._callbacks['study_completed'].append(callback)

    def on_update(self, callback):
        """Register callback for data updates."""
        self._callbacks['update'].append(callback)

    def on_error(self, callback):
        """Register callback for errors."""
        self._callbacks['error'].append(callback)

    async def remove(self):
        """Cleanup and remove this study."""
        await self._chart_session._client.send('remove_study', [
            self._chart_session._session_id,
            self._study_id,
        ])
        if self._study_id in self._study_listeners:
            del self._study_listeners[self._study_id]
