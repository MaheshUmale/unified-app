
"""
Dashboard Client
Sends updates to the Dashboard Server.
"""
import requests
import threading

class DashboardClient:
    def __init__(self, server_url="http://localhost:5050", enabled=True):
        self.server_url = server_url
        self.enabled = enabled

    def _send(self, endpoint, data):
        if not self.enabled: return
        try:
            requests.post(f"{self.server_url}{endpoint}", json=data, timeout=0.5)
        except:
            pass # Ignore errors to avoid blocking trading

    def update_positions(self, positions_list):
        # Run in thread to allow non-blocking
        threading.Thread(target=self._send, args=('/api/update', {
            'type': 'POSITION_UPDATE',
            'payload': positions_list
        })).start()

    def send_signal(self, type_, details, instrument):
        threading.Thread(target=self._send, args=('/api/update', {
            'type': 'SIGNAL',
            'payload': {
                'type': type_,
                'details': details,
                'instrument': instrument
            }
        })).start()

    def update_pnl(self, summary_dict):
        threading.Thread(target=self._send, args=('/api/update', {
            'type': 'PNL_UPDATE',
            'payload': summary_dict
        })).start()
