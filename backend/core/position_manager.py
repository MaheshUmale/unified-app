
"""
Position Manager
Tracks live positions and calculates real-time PnL.
"""

from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import json

@dataclass
class Position:
    """Represents a trading position"""
    instrument_key: str
    side: str  # 'LONG' or 'SHORT'
    quantity: int
    avg_entry_price: float
    entry_time: datetime
    current_price: float = 0.0
    realized_pnl: float = 0.0
    trades: List[Dict] = field(default_factory=list)

    @property
    def unrealized_pnl(self) -> float:
        """Calculate unrealized PnL"""
        if self.side == 'LONG':
            return (self.current_price - self.avg_entry_price) * self.quantity
        else:  # SHORT
            return (self.avg_entry_price - self.current_price) * self.quantity

    @property
    def total_pnl(self) -> float:
        """Total PnL (realized + unrealized)"""
        return self.realized_pnl + self.unrealized_pnl

    @property
    def pnl_percent(self) -> float:
        """PnL as percentage of entry value"""
        entry_value = self.avg_entry_price * self.quantity
        if entry_value == 0:
            return 0.0
        return (self.total_pnl / entry_value) * 100

    def update_price(self, price: float):
        """Update current market price"""
        self.current_price = price

    def add_trade(self, trade_info: Dict):
        """Add trade to position history"""
        self.trades.append({
            **trade_info,
            'timestamp': datetime.now().isoformat()
        })

    def to_dict(self) -> Dict:
        """Convert position to dictionary"""
        return {
            'instrument_key': self.instrument_key,
            'side': self.side,
            'quantity': self.quantity,
            'avg_entry_price': self.avg_entry_price,
            'current_price': self.current_price,
            'entry_time': self.entry_time.isoformat(),
            'unrealized_pnl': round(self.unrealized_pnl, 2),
            'realized_pnl': round(self.realized_pnl, 2),
            'total_pnl': round(self.total_pnl, 2),
            'pnl_percent': round(self.pnl_percent, 2),
            'num_trades': len(self.trades)
        }


class PositionManager:
    """Manages all trading positions and calculates PnL"""

    def __init__(self):
        self.positions: Dict[str, Position] = {}  # instrument_key -> Position
        self.closed_positions: List[Position] = []
        self.total_trades_today = 0
        self.daily_pnl = 0.0

    def open_position(
        self,
        instrument_key: str,
        side: str,
        quantity: int,
        entry_price: float,
        order_id: Optional[str] = None
    ) -> Position:
        """
        Open a new position or add to existing

        Args:
            instrument_key: Instrument identifier
            side: 'LONG' or 'SHORT'
            quantity: Number of shares
            entry_price: Entry price per share
            order_id: Optional order ID

        Returns:
            Position object
        """
        if instrument_key in self.positions:
            # Add to existing position (average price)
            pos = self.positions[instrument_key]

            if pos.side == side:
                # Same side - average the entry
                total_qty = pos.quantity + quantity
                total_value = (pos.avg_entry_price * pos.quantity) + (entry_price * quantity)
                pos.avg_entry_price = total_value / total_qty
                pos.quantity = total_qty
            else:
                # Opposite side - close or reverse
                if quantity >= pos.quantity:
                    # Close and potentially reverse
                    self.close_position(instrument_key, entry_price, quantity - pos.quantity, f"Reverse to {side}")
                    if quantity > pos.quantity:
                        # Open opposite position
                        return self.open_position(instrument_key, side, quantity - pos.quantity, entry_price, order_id)
                else:
                    # Partial close
                    pos.quantity -= quantity

            pos.add_trade({
                'type': 'ADD' if pos.side == side else 'REDUCE',
                'quantity': quantity,
                'price': entry_price,
                'order_id': order_id
            })
        else:
            # New position
            pos = Position(
                instrument_key=instrument_key,
                side=side,
                quantity=quantity,
                avg_entry_price=entry_price,
                entry_time=datetime.now(),
                current_price=entry_price
            )
            pos.add_trade({
                'type': 'OPEN',
                'quantity': quantity,
                'price': entry_price,
                'order_id': order_id
            })
            self.positions[instrument_key] = pos

        self.total_trades_today += 1
        print(f"✓ Position Opened: {side} {quantity} {instrument_key} @ {entry_price}")
        return pos

    def close_position(
        self,
        instrument_key: str,
        exit_price: float,
        quantity: Optional[int] = None,
        reason: str = "Manual Close",
        order_id: Optional[str] = None
    ) -> Optional[float]:
        """
        Close a position (full or partial)

        Args:
            instrument_key: Instrument to close
            exit_price: Exit price
            quantity: Quantity to close (None = close all)
            reason: Reason for closure
            order_id: Optional order ID

        Returns:
            Realized PnL from the closure
        """
        if instrument_key not in self.positions:
            print(f"⚠ No position found for {instrument_key}")
            return None

        pos = self.positions[instrument_key]
        close_qty = quantity if quantity is not None else pos.quantity

        # Calculate PnL for closed portion
        if pos.side == 'LONG':
            pnl = (exit_price - pos.avg_entry_price) * close_qty
        else:
            pnl = (pos.avg_entry_price - exit_price) * close_qty

        pos.realized_pnl += pnl
        self.daily_pnl += pnl

        pos.add_trade({
            'type': 'CLOSE',
            'quantity': close_qty,
            'price': exit_price,
            'pnl': round(pnl, 2),
            'reason': reason,
            'order_id': order_id
        })

        # Remove from active or reduce quantity
        if close_qty >= pos.quantity:
            # Full close
            self.closed_positions.append(pos)
            del self.positions[instrument_key]
            print(f"✓ Position Closed: {pos.side} {close_qty} {instrument_key} @ {exit_price} | PnL: {pnl:.2f} | {reason}")
        else:
            # Partial close
            pos.quantity -= close_qty
            print(f"✓ Partial Close: {close_qty}/{pos.quantity + close_qty} {instrument_key} | PnL: {pnl:.2f}")

        self.total_trades_today += 1
        return pnl

    def update_market_prices(self, price_updates: Dict[str, float]):
        """
        Update current market prices for all positions

        Args:
            price_updates: Dict of {instrument_key: current_price}
        """
        for instrument_key, price in price_updates.items():
            if instrument_key in self.positions:
                self.positions[instrument_key].update_price(price)

    def get_position(self, instrument_key: str) -> Optional[Position]:
        """Get position for an instrument"""
        return self.positions.get(instrument_key)

    def get_all_positions(self) -> List[Position]:
        """Get all active positions"""
        return list(self.positions.values())

    def get_total_unrealized_pnl(self) -> float:
        """Get total unrealized PnL across all positions"""
        return sum(pos.unrealized_pnl for pos in self.positions.values())

    def get_total_pnl(self) -> float:
        """Get total PnL (realized + unrealized)"""
        return self.daily_pnl + self.get_total_unrealized_pnl()

    def get_summary(self) -> Dict:
        """Get position summary"""
        return {
            'active_positions': len(self.positions),
            'closed_positions': len(self.closed_positions),
            'total_trades_today': self.total_trades_today,
            'realized_pnl': round(self.daily_pnl, 2),
            'unrealized_pnl': round(self.get_total_unrealized_pnl(), 2),
            'total_pnl': round(self.get_total_pnl(), 2),
            'positions': [pos.to_dict() for pos in self.positions.values()]
        }

    def save_state(self, filepath: str = "positions_state.json"):
        """Save current state to file"""
        state = {
            'timestamp': datetime.now().isoformat(),
            'summary': self.get_summary(),
            'closed_positions': [pos.to_dict() for pos in self.closed_positions]
        }
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2)
        print(f"✓ State saved to {filepath}")

    def close_all_positions(self, exit_price_map: Dict[str, float], reason: str = "EOD Close"):
        """Close all open positions"""
        for instrument_key in list(self.positions.keys()):
            price = exit_price_map.get(instrument_key, self.positions[instrument_key].current_price)
            self.close_position(instrument_key, price, reason=reason)
