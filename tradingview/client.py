"""
TradingView Client Module
"""
import json
import asyncio
import websockets
from typing import Dict, Any, Callable, List, Optional, Union

from .protocol import parse_ws_packet, format_ws_packet
from .chart import ChartSession
from .quote import QuoteSession

from tradingview.utils import get_logger
logger = get_logger(__name__)

class Client:
    """
    TradingView Client Class
    """
    def __init__(self, options=None, **kwargs):
        """
        Initialize the client.

        Args:
            options: Client options
            **kwargs: Extra named arguments, can contain token and signature
        """
        # Merge options and named arguments
        if options is None:
            options = {}

        # Merge named arguments into options
        for key, value in kwargs.items():
            options[key] = value

        # If no auth info provided, try to get from auth manager
        if not options.get('token') or not options.get('signature'):
            try:
                from .auth_config import get_tradingview_auth
                auth_info = get_tradingview_auth(options.get('account_name'))
                if auth_info:
                    options.update(auth_info)
            except ImportError:
                pass  # Auth manager unavailable, continue with provided parameters

        self._ws = None
        self._logged = False
        self._sessions = {}
        self._send_queue = []
        self._debug = options.get('DEBUG', False)

        # Callbacks
        self._callbacks = {
            'connected': [],
            'disconnected': [],
            'logged': [],
            'ping': [],
            'data': [],
            'error': [],
            'event': []
        }

        # Server and auth info
        self._server = options.get('server', 'data')
        self._token = options.get('token', '')
        self._signature = options.get('signature', '')
        self._location = options.get('location', 'https://tradingview.com')

        # Background tasks
        self._heartbeat_task = None
        self._message_loop_task = None
        self._heartbeat_interval = options.get('heartbeat_interval', 10)  # Heartbeat every 10s to avoid timeout

        # Class attributes
        self.Session = type('Session', (), {
            'Chart': lambda: ChartSession(self),
            'Quote': lambda options=None: QuoteSession(self, options)
        })

    @property
    def is_logged(self):
        """Whether logged in"""
        return self._logged

    @property
    def is_open(self):
        """Whether connection is open"""
        if not self._ws:
            return False

        # Check websockets version and use correct property
        try:
            import websockets
            websockets_version = getattr(websockets, '__version__', '0.0')
            version_parts = [int(x) for x in websockets_version.split('.')[:2]]

            if version_parts[0] >= 10:
                # 10.0+ uses 'closed' property
                return not self._ws.closed
            else:
                # Older versions use 'open' property
                return hasattr(self._ws, 'open') and self._ws.open
        except Exception:
            # Fallback checks
            if hasattr(self._ws, 'open'):
                return self._ws.open
            elif hasattr(self._ws, 'closed'):
                return not self._ws.closed
            else:
                # Cannot determine, assume connected if object exists
                return True

    @property
    def sessions(self):
        """Active sessions"""
        return self._sessions

    async def connect(self):
        """
        Connect to TradingView server.
        """
        url = f"wss://{self._server}.tradingview.com/socket.io/websocket?type=chart"

        try:
            import websockets

            # Get websockets version
            websockets_version = getattr(websockets, '__version__', '0.0')
            version_parts = [int(x) for x in websockets_version.split('.')[:2]]

            # Request headers
            headers = {'Origin': 'https://www.tradingview.com'}

            logger.info(f"tradingview connect: {url}, {headers}")

            # Timeout parameters (seconds)
            connection_timeout = 30
            handshake_timeout = 20

            # Handle headers based on version
            if version_parts[0] >= 10:
                # 10.0+ uses extra_headers
                try:
                    self._ws = await asyncio.wait_for(
                        websockets.connect(
                            url,
                            extra_headers=headers,
                            ping_interval=8,
                            ping_timeout=5,
                            close_timeout=3,
                            max_size=10 * 1024 * 1024,  # 10MB max message size
                            open_timeout=handshake_timeout
                        ),
                        timeout=connection_timeout
                    )
                except TypeError:
                    # Fallback for slightly older versions
                    try:
                        self._ws = await asyncio.wait_for(
                            websockets.connect(
                                url,
                                additional_headers=headers,
                                ping_interval=8,
                                ping_timeout=5,
                                open_timeout=handshake_timeout
                            ),
                            timeout=connection_timeout
                        )
                    except TypeError:
                        # Compatibility for older libs
                        self._ws = await asyncio.wait_for(
                            websockets.connect(url, additional_headers=headers),
                            timeout=connection_timeout
                        )
            elif version_parts[0] >= 6:
                # Versions 6.0-9.x
                try:
                    self._ws = await asyncio.wait_for(
                        websockets.connect(
                            url,
                            origin="https://www.tradingview.com",
                            ping_interval=8,
                            ping_timeout=5,
                            open_timeout=handshake_timeout
                        ),
                        timeout=connection_timeout
                    )
                except TypeError:
                    # Legacy compatibility
                    self._ws = await asyncio.wait_for(
                        websockets.connect(url, origin="https://www.tradingview.com"),
                        timeout=connection_timeout
                    )
            else:
                # Much older versions
                from websockets.client import WebSocketClientProtocol

                class CustomWebSocketClientProtocol(WebSocketClientProtocol):
                    def __init__(self, *args, **kwargs):
                        super().__init__(*args, **kwargs)
                        self.origin = "https://www.tradingview.com"

                self._ws = await asyncio.wait_for(
                    websockets.connect(url, klass=CustomWebSocketClientProtocol),
                    timeout=connection_timeout
                )

            # Trigger connected event
            self._handle_event('connected')

            # Set authentication - following JavaScript version logic
            if self._token:
                try:
                    from .misc_requests import get_user
                    user = await get_user(self._token, self._signature, self._location)
                    # Use auth_token
                    self._send_queue.insert(0, format_ws_packet({
                        'm': 'set_auth_token',
                        'p': [user.auth_token]
                    }))
                    self._logged = True
                    await self._send_queue_data()
                except Exception as e:
                    self._handle_error(f"Authentication error: {str(e)}")
            else:
                # Use anonymous Token, consistent with JS version
                self._send_queue.insert(0, format_ws_packet({
                    'm': 'set_auth_token',
                    'p': ['unauthorized_user_token']
                }))
                self._logged = True
                await self._send_queue_data()

            # Stop old tasks to avoid conflict
            await self._stop_background_tasks()

            # Start message receiving loop
            self._message_loop_task = asyncio.create_task(self._message_loop())

            # Start heartbeat task
            self._start_heartbeat()

            return True

        except Exception as e:
            self._handle_error(f"Connection error: {str(e)}")
            return False

    async def _heartbeat(self):
        """Heartbeat task to send pings and keep connection active"""
        retry_count = 0
        max_retries = 5
        base_wait_time = 2

        try:
            while True:  # Reconnection logic is handled by the Enhanced client
                if not self.is_open:
                    self._handle_error("Connection loss detected, exiting heartbeat task")
                    break

                try:
                    # Send an integer as a ping packet per TradingView protocol
                    import time
                    ping_id = int(time.time() * 1000)
                    ping_message = format_ws_packet(f"~h~{ping_id}")

                    if ping_message:
                        await self._ws.send(ping_message)
                        if self._debug:
                            logger.debug(f"Sending heartbeat ping: {ping_id}")
                except Exception as e:
                    self._handle_error(f"Failed to send heartbeat: {str(e)}")
                    # Mark connection as closed for next cycle
                    if self._ws:
                        try:
                            await self._ws.close()
                        except:
                            pass
                    self._ws = None
                    self._logged = False
                    continue

                # Wait for next heartbeat
                await asyncio.sleep(self._heartbeat_interval)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._handle_error(f"Heartbeat task exception: {str(e)}")
        finally:
            self._handle_error("Heartbeat task ended")

    async def _stop_background_tasks(self):
        """Stop all background tasks"""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        if self._message_loop_task and not self._message_loop_task.done():
            self._message_loop_task.cancel()
            try:
                await self._message_loop_task
            except asyncio.CancelledError:
                pass
            self._message_loop_task = None

    def _start_heartbeat(self):
        """Start heartbeat task"""
        self._heartbeat_task = asyncio.create_task(self._heartbeat())

    async def _message_loop(self):
        """Message receiving loop"""
        retry_count = 0
        max_retries = 5
        base_wait_time = 1

        try:
            import websockets

            # Get websockets version
            websockets_version = getattr(websockets, '__version__', '0.0')
            version_parts = [int(x) for x in websockets_version.split('.')[:2]]

            # Capture connection-related exceptions
            connection_exceptions = []
            if hasattr(websockets, 'exceptions'):
                if hasattr(websockets.exceptions, 'ConnectionClosed'):
                    connection_exceptions.append(websockets.exceptions.ConnectionClosed)
                if hasattr(websockets.exceptions, 'ConnectionClosedError'):
                    connection_exceptions.append(websockets.exceptions.ConnectionClosedError)
                if hasattr(websockets.exceptions, 'ConnectionClosedOK'):
                    connection_exceptions.append(websockets.exceptions.ConnectionClosedOK)
            elif hasattr(websockets, 'ConnectionClosed'):
                connection_exceptions.append(websockets.ConnectionClosed)

            while True:
                if not self._ws or not self.is_open:
                    # Connection closed, wait for heartbeat/reconnect
                    await asyncio.sleep(1)
                    continue

                try:
                    if version_parts[0] >= 6:
                        try:
                            async for message in self._ws:
                                await self._parse_packet(message)
                                retry_count = 0  # Reset retry on success
                        except tuple(connection_exceptions) if connection_exceptions else Exception as e:
                            self._logged = False
                            self._handle_error(f"Connection closed: {str(e)}")
                            self._handle_event('disconnected')
                            await asyncio.sleep(1)
                    else:
                        # Older versions using recv()
                        try:
                            message = await self._ws.recv()
                            await self._parse_packet(message)
                            retry_count = 0
                        except tuple(connection_exceptions) if connection_exceptions else Exception as e:
                            self._logged = False
                            self._handle_error(f"Connection closed: {str(e)}")
                            self._handle_event('disconnected')
                            await asyncio.sleep(1)
                except Exception as e:
                    retry_count += 1
                    wait_time = base_wait_time * (2 ** min(retry_count - 1, 5))

                    self._handle_error(f"Message loop exception({retry_count}/{max_retries}): {str(e)}, retrying in {wait_time}s")

                    self._logged = False
                    if self._ws:
                        try:
                            await self._ws.close()
                        except:
                            pass
                    self._ws = None

                    if retry_count >= max_retries:
                        self._handle_error("Max retries reached, message loop terminating")
                        return

                    await asyncio.sleep(wait_time)

        except Exception as e:
            self._handle_error(f"Message loop error: {str(e)}")
            self._logged = False
            self._handle_event('disconnected')

            if self._heartbeat_task and not self._heartbeat_task.done():
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass
                self._heartbeat_task = None

    async def _parse_packet(self, data):
        """
        Parse WebSocket data packet.

        Args:
            data: Raw WebSocket data
        """
        if not self.is_open:
            return

        try:
            packets = parse_ws_packet(data)
            if not packets:
                return

            if not isinstance(packets, list):
                packets = [packets]

            for packet in packets:
                if self._debug:
                    logger.debug(f"Received: {packet}")

                # Handle Ping packets
                if isinstance(packet, int):
                    try:
                        await self._ws.send(format_ws_packet(f"~h~{packet}"))
                        self._handle_event('ping', packet)
                    except Exception as e:
                        self._handle_error(f"Ping handling error: {str(e)}")
                    continue

                # Handle protocol error
                if isinstance(packet, dict) and packet.get('m') == 'protocol_error':
                    self._handle_error(f"Protocol error: {packet.get('p')}")
                    try:
                        await self._ws.close()
                    except Exception as e:
                        self._handle_error(f"Connection close error: {str(e)}")
                    continue

                # Handle session data
                if isinstance(packet, dict) and packet.get('m') and isinstance(packet.get('p'), list):
                    try:
                        parsed = {
                            'type': packet['m'],
                            'data': packet['p']
                        }

                        session_id = packet['p'][0] if packet['p'] else None

                        if session_id and session_id in self._sessions:
                            if 'on_data' in self._sessions[session_id]:
                                self._sessions[session_id]['on_data'](parsed)
                            continue
                    except Exception as e:
                        self._handle_error(f"Session data handling error: {str(e)}")
                        continue

                # Handle login data
                if not self._logged:
                    try:
                        self._handle_event('logged', packet)
                    except Exception as e:
                        self._handle_error(f"Login data handling error: {str(e)}")
                    continue

                # Other data
                try:
                    self._handle_event('data', packet)
                except Exception as e:
                    self._handle_error(f"Data handling error: {str(e)}")
        except Exception as e:
            self._handle_error(f"Packet parsing error: {str(e)}")

    def _handle_event(self, event, *data):
        """
        Handle events.

        Args:
            event: Event type
            data: Event data
        """
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
            error_msg = " ".join(str(msg) for msg in msgs)
            logger.error(f"ERROR: {error_msg}")
        else:
            self._handle_event('error', *msgs)

    async def send(self, packet_type, packet_data=None):
        """
        Send data packet.

        Args:
            packet_type: Packet type
            packet_data: Packet content
        """
        try:
            if packet_data is None:
                packet_data = []

            # Ensure packet_data is a list
            if not isinstance(packet_data, list):
                packet_data = [packet_data]

            processed_data = []

            # Some commands require preserving array structure
            should_preserve_arrays = packet_type in ['create_series', 'modify_series']

            for item in packet_data:
                try:
                    if isinstance(item, dict) and not isinstance(item, str):
                        # Dicts are always JSON stringified
                        processed_data.append(json.dumps(item))
                    elif isinstance(item, list) and not isinstance(item, str) and not should_preserve_arrays:
                        # Arrays stringified unless preserved
                        processed_data.append(json.dumps(item))
                    else:
                        # Others kept as is
                        processed_data.append(item)
                except Exception as e:
                    self._handle_error(f"Data item processing error: {str(e)}")
                    processed_data.append(str(item))

            formatted_packet = format_ws_packet({
                'm': packet_type,
                'p': processed_data
            })

            if formatted_packet:
                self._send_queue.append(formatted_packet)
                await self._send_queue_data()
            else:
                self._handle_error("Failed to format packet")
        except Exception as e:
            self._handle_error(f"Send packet error: {str(e)}")

    async def _send_queue_data(self):
        """Send data from queue"""
        if not self.is_open:
            return

        if not self._logged and self._send_queue and 'set_auth_token' not in self._send_queue[0]:
            # Do not send until logged in (except auth packet)
            return

        try:
            import websockets
            connection_exceptions = []

            if hasattr(websockets, 'exceptions'):
                if hasattr(websockets.exceptions, 'ConnectionClosed'):
                    connection_exceptions.append(websockets.exceptions.ConnectionClosed)
                if hasattr(websockets.exceptions, 'ConnectionClosedError'):
                    connection_exceptions.append(websockets.exceptions.ConnectionClosedError)
                if hasattr(websockets.exceptions, 'ConnectionClosedOK'):
                    connection_exceptions.append(websockets.exceptions.ConnectionClosedOK)
            elif hasattr(websockets, 'ConnectionClosed'):
                connection_exceptions.append(websockets.ConnectionClosed)

            retry_count = 0
            max_retries = 3
            base_wait_time = 0.5

            while self._send_queue:
                if not self.is_open:
                    break

                packet = self._send_queue[0]
                if self._debug:
                    logger.debug(f"Sending: {packet}")

                try:
                    await self._ws.send(packet)
                    self._send_queue.pop(0)
                    retry_count = 0
                except tuple(connection_exceptions) if connection_exceptions else Exception as e:
                    self._handle_error(f"Connection closed, cannot send: {str(e)}")
                    self._logged = False
                    self._handle_event('disconnected')
                    break
                except Exception as e:
                    retry_count += 1
                    wait_time = base_wait_time * (2 ** min(retry_count - 1, 3))

                    if retry_count > max_retries:
                        self._handle_error(f"Failed to send, max retries reached, dropping packet: {str(e)}")
                        self._send_queue.pop(0)
                        retry_count = 0
                        continue

                    self._handle_error(f"Send error({retry_count}/{max_retries}): {str(e)}, retrying in {wait_time}s")
                    await asyncio.sleep(wait_time)

                    if not self.is_open:
                        try:
                            await self.connect()
                        except Exception as conn_err:
                            self._handle_error(f"Reconnection error: {str(conn_err)}")

        except Exception as e:
            self._handle_error(f"Processing send queue error: {str(e)}")

    def on_connected(self, callback):
        """Register connection callback"""
        self._callbacks['connected'].append(callback)

    def on_disconnected(self, callback):
        """Register disconnection callback"""
        self._callbacks['disconnected'].append(callback)

    def on_logged(self, callback):
        """Register login callback"""
        self._callbacks['logged'].append(callback)

    def on_ping(self, callback):
        """Register ping callback"""
        self._callbacks['ping'].append(callback)

    def on_data(self, callback):
        """Register data callback"""
        self._callbacks['data'].append(callback)

    def on_error(self, callback):
        """Register error callback"""
        self._callbacks['error'].append(callback)

    def on_event(self, callback):
        """Register event callback"""
        self._callbacks['event'].append(callback)

    async def end(self):
        """Close connection"""
        await self._stop_background_tasks()

        if self._ws:
            await self._ws.close()
            self._ws = None

        self._logged = False

    def get_connection_status(self):
        """
        Get detailed connection status.

        Returns:
            dict: Detailed status info
        """
        has_heartbeat = False
        if self._heartbeat_task:
            has_heartbeat = not self._heartbeat_task.done()

        websocket_status = "unknown"
        if self._ws is None:
            websocket_status = "none"
        elif not self.is_open:
            websocket_status = "closed"
        else:
            websocket_status = "open"

        return {
            "is_open": self.is_open,
            "is_logged": self._logged,
            "websocket_status": websocket_status,
            "server": self._server,
            "has_active_heartbeat": has_heartbeat,
            "heartbeat_interval": self._heartbeat_interval,
            "active_sessions_count": len(self._sessions),
            "queued_messages": len(self._send_queue)
        }

# For backward compatibility
TradingViewClient = Client
