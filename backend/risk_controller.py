
"""
Risk Controller
Enforces trading limits and risk parameters.
"""

import json
from position_manager import PositionManager
from typing import Dict

class RiskController:
    def __init__(self, position_manager: PositionManager, config_file: str = "risk_config.json"):
        self.pm = position_manager
        self.config_file = config_file
        self.load_config()
        self.shutdown_triggered = False

    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
            print(f"✓ Risk Config Loaded: {self.config}")
        except Exception as e:
            print(f"⚠ Failed to load risk config ({e}), using defaults.")
            self.config = {
                "max_trades_per_day": 10,
                "max_daily_drawdown": 500.0,
                "max_position_size": 10
            }

    def can_trade(self, side: str, instrument_key: str, quantity: int) -> bool:
        if self.shutdown_triggered:
            print("⛔ RISK SHUTDOWN ACTIVE. Trading halted.")
            return False

        # 1. Check Max Trades
        if self.pm.total_trades_today >= self.config.get('max_trades_per_day', 10):
            print(f"⛔ Max trades limit ({self.pm.total_trades_today}) reached.")
            return False

        # 2. Check Daily Drawdown
        pnl = self.pm.get_total_pnl()
        max_dd = self.config.get('max_daily_drawdown', 500.0)
        # Note: Drawdown is usually Peak - Current, but here we check absolute daily loss limit
        # If PnL is negative and exceeds limit (e.g., -600 < -500 (check absolute))
        if pnl < 0 and abs(pnl) > max_dd:
             print(f"⛔ Max daily drawdown hit (PnL: {pnl:.2f}, Limit: -{max_dd})")
             self.shutdown_triggered = True # Trip the breaker
             return False

        # 3. Check Position Limits (if adding to position)
        current_pos = self.pm.get_position(instrument_key)
        current_qty = current_pos.quantity if current_pos else 0

        # If closing (reducing risk), always allow?
        # For simplicity, if side opposes current position, it's a close/reduce -> Allow
        if current_pos and current_pos.side != side:
             return True # Allowing exit/reduction

        # If increasing risk
        if (current_qty + quantity) > self.config.get('max_position_size', 10):
             print(f"⛔ Max position size limit exceeded ({current_qty + quantity})")
             return False

        return True

    def check_risk_status(self):
        """Periodic check intended to be called in loop"""
        pnl = self.pm.get_total_pnl()
        max_dd = self.config.get('max_daily_drawdown', 500.0)

        if pnl < 0 and abs(pnl) > max_dd and not self.shutdown_triggered:
             print(f"⛔ CRITICAL: Max daily drawdown hit dynamically (PnL: {pnl:.2f}). Triggering SHUTDOWN.")
             self.shutdown_triggered = True
             return False # Status bad
        return True # Status ok
