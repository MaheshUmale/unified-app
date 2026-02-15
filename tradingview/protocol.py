"""
Protocol Handling Module
"""
import json
import base64
import zipfile
import io
import binascii
import re
from typing import List, Union, Any

def parse_ws_packet(data: str) -> List[Any]:
    """
    Parse WebSocket data packets from TradingView using robust regex.
    """
    if not data:
        return []

    if not isinstance(data, str):
        try:
            data = data.decode('utf-8') if isinstance(data, bytes) else str(data)
        except Exception:
            return []

    # TradingView sends messages in the format: ~m~LEN~m~PAYLOAD
    # Multiple messages can be bundled in one WebSocket frame.
    # Heartbeats are often bundled too: ~m~4~m~~h~1

    packets = []
    # Split by the ~m~LEN~m~ pattern
    # We use a non-consuming split to keep the payloads
    parts = re.split(r"~m~\d+~m~", data)
    for part in parts:
        if not part:
            continue

        # Check for heartbeat
        if part.startswith("~h~"):
            packets.append(part)
            continue

        # Try to parse as JSON
        try:
            packets.append(json.loads(part))
        except json.JSONDecodeError:
            # Fallback for non-JSON payloads
            if part.isdigit():
                packets.append(int(part))
            else:
                packets.append(part)

    return packets

def format_ws_packet(packet: Any) -> str:
    """
    Format data packet for TradingView WebSocket.
    """
    try:
        if isinstance(packet, dict):
            msg = json.dumps(packet, separators=(',', ':'))
        else:
            msg = str(packet)

        return f'~m~{len(msg)}~m~{msg}'
    except Exception:
        return ""

async def parse_compressed(data: str) -> dict:
    """
    Parse TradingView compressed data (Base64 + Zip + JSON).
    """
    if not data:
        return {}

    try:
        decoded = base64.b64decode(data)
        zip_data = io.BytesIO(decoded)

        with zipfile.ZipFile(zip_data) as zf:
            file_list = zf.namelist()
            if not file_list:
                return {}

            with zf.open(file_list[0]) as f:
                content = f.read().decode('utf-8')
                return json.loads(content)
    except Exception:
        return {}
