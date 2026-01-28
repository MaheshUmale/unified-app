
"""
Order Manager
Handles automated order placement and execution logic.
"""

from upstox_client import UpstoxClient
from position_manager import PositionManager
from typing import Optional, Dict
from datetime import datetime
import time
# forward ref for type hinting
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from risk_controller import RiskController

class OrderManager:
    """Manages order placement and execution"""

    def __init__(
        self,
        upstox_client: UpstoxClient,
        position_manager: PositionManager,
        order_type: str = "MARKET",
        product: str = "I",  # Intraday
        max_retries: int = 3,
        risk_controller: Optional['RiskController'] = None,
        default_quantity: int = 1
    ):
        """
        Initialize Order Manager

        Args:
            upstox_client: Upstox API client
            position_manager: Position manager instance
            default_quantity: Default order quantity
            order_type: 'MARKET' or 'LIMIT'
            product: 'I' (Intraday) or 'D' (Delivery)
            max_retries: Max retry attempts for failed orders
        """
        self.client = upstox_client
        self.position_manager = position_manager
        self.default_quantity = default_quantity
        self.order_type = order_type
        self.product = product
        self.max_retries = max_retries
        self.risk_controller = risk_controller

        self.pending_orders: Dict[str, Dict] = {}  # order_id -> order_info
        self.filled_orders: Dict[str, Dict] = {}
        self.rejected_orders: Dict[str, Dict] = {}

    def place_entry_order(
        self,
        instrument_key: str,
        side: str,  # 'BUY' or 'SELL'
        quantity: Optional[int] = None,
        price: Optional[float] = None,
        signal_info: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Place an entry order

        Args:
            instrument_key: Instrument to trade
            side: 'BUY' or 'SELL'
            quantity: Order quantity (uses default if None)
            price: Limit price (for LIMIT orders)
            signal_info: Additional signal metadata

        Returns:
            Order ID if successful, None otherwise
        """
        qty = quantity or self.default_quantity

        # --- RISK CHECK ---
        if self.risk_controller:
            if not self.risk_controller.can_trade(side, instrument_key, qty):
                print(f"⛔ Order REJECTED by Risk Controller: {side} {qty} {instrument_key}")
                return None
        # ------------------

        print(f"\n{'='*60}")
        print(f"📊 PLACING {side} ORDER")
        print(f"Instrument: {instrument_key}")
        print(f"Quantity: {qty}")
        print(f"Type: {self.order_type}")
        if signal_info:
            print(f"Signal: {signal_info.get('reason', 'N/A')}")
        print(f"{'='*60}")

        try:
            # Place order via Upstox
            response = self.client.place_order(
                instrument_key=instrument_key,
                quantity=qty,
                side=side,
                order_type=self.order_type,
                product=self.product,
                price=price or 0.0
            )

            if response.get('status') == 'success':
                order_id = response['data']['order_id']

                self.pending_orders[order_id] = {
                    'instrument_key': instrument_key,
                    'side': side,
                    'quantity': qty,
                    'order_type': self.order_type,
                    'price': price,
                    'signal_info': signal_info,
                    'placed_at': datetime.now().isoformat()
                }

                print(f"✓ Order placed successfully! Order ID: {order_id}")

                # Wait for fill (for MARKET orders)
                if self.order_type == "MARKET":
                    self._wait_for_fill(order_id, instrument_key, side, qty)

                return order_id
            else:
                print(f"✗ Order placement failed: {response}")
                return None

        except Exception as e:
            print(f"✗ Error placing order: {e}")
            self.rejected_orders[str(datetime.now())] = {
                'instrument_key': instrument_key,
                'side': side,
                'error': str(e)
            }
            return None

    def place_exit_order(
        self,
        instrument_key: str,
        reason: str = "Exit Signal",
        quantity: Optional[int] = None,
        price: Optional[float] = None
    ) -> Optional[str]:
        """
        Place an exit order for existing position

        Args:
            instrument_key: Instrument to exit
            reason: Reason for exit
            quantity: Quantity to exit (None = close full position)
            price: Exit price (for LIMIT orders)

        Returns:
            Order ID if successful
        """
        # Check if we have an open position
        position = self.position_manager.get_position(instrument_key)
        if not position:
            print(f"⚠ No position to exit for {instrument_key}")
            return None

        # Determine exit side (opposite of position)
        exit_side = 'SELL' if position.side == 'LONG' else 'BUY'
        exit_qty = quantity or position.quantity

        print(f"\n{'='*60}")
        print(f"🔚 PLACING EXIT ORDER")
        print(f"Instrument: {instrument_key}")
        print(f"Position: {position.side} {position.quantity} @ {position.avg_entry_price}")
        print(f"Exit: {exit_side} {exit_qty}")
        print(f"Reason: {reason}")
        print(f"{'='*60}")

        try:
            response = self.client.place_order(
                instrument_key=instrument_key,
                quantity=exit_qty,
                side=exit_side,
                order_type=self.order_type,
                product=self.product,
                price=price or 0.0
            )

            if response.get('status') == 'success':
                order_id = response['data']['order_id']

                self.pending_orders[order_id] = {
                    'instrument_key': instrument_key,
                    'side': exit_side,
                    'quantity': exit_qty,
                    'is_exit': True,
                    'reason': reason,
                    'placed_at': datetime.now().isoformat()
                }

                print(f"✓ Exit order placed! Order ID: {order_id}")

                # Wait for fill
                if self.order_type == "MARKET":
                    self._wait_for_fill(order_id, instrument_key, exit_side, exit_qty, is_exit=True, reason=reason)

                return order_id
            else:
                print(f"✗ Exit order failed: {response}")
                return None

        except Exception as e:
            print(f"✗ Error placing exit order: {e}")
            return None

    def _wait_for_fill(
        self,
        order_id: str,
        instrument_key: str,
        side: str,
        quantity: int,
        is_exit: bool = False,
        reason: str = "",
        timeout: int = 5
    ):
        """Wait for order to be filled and update position manager"""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                order_details = self.client.get_order_details(order_id)
                status = order_details.get('data', {}).get('status', '')

                if status == 'complete':
                    # Get fill price from order details
                    filled_price = float(order_details['data'].get('average_price', 0))

                    print(f"✓ Order FILLED at {filled_price}")

                    # Update position manager
                    if is_exit:
                        self.position_manager.close_position(
                            instrument_key,
                            filled_price,
                            quantity,
                            reason=reason,
                            order_id=order_id
                        )
                    else:
                        pos_side = 'LONG' if side == 'BUY' else 'SHORT'
                        self.position_manager.open_position(
                            instrument_key,
                            pos_side,
                            quantity,
                            filled_price,
                            order_id=order_id
                        )

                    # Move to filled orders
                    self.filled_orders[order_id] = self.pending_orders.pop(order_id)
                    self.filled_orders[order_id]['filled_price'] = filled_price
                    self.filled_orders[order_id]['filled_at'] = datetime.now().isoformat()

                    return

                elif status in ['rejected', 'cancelled']:
                    print(f"✗ Order {status.upper()}: {order_details}")
                    self.rejected_orders[order_id] = self.pending_orders.pop(order_id)
                    return

                time.sleep(0.5)  # Wait 500ms before retry

            except Exception as e:
                print(f"⚠ Error checking order status: {e}")
                time.sleep(0.5)

        print(f"⏱ Order fill timeout for {order_id}")

    def cancel_pending_orders(self, instrument_key: Optional[str] = None):
        """Cancel all pending orders (optionally filtered by instrument)"""
        orders_to_cancel = []

        for order_id, order_info in self.pending_orders.items():
            if instrument_key is None or order_info['instrument_key'] == instrument_key:
                orders_to_cancel.append(order_id)

        for order_id in orders_to_cancel:
            try:
                self.client.cancel_order(order_id)
                print(f"✓ Cancelled order {order_id}")
                self.pending_orders.pop(order_id, None)
            except Exception as e:
                print(f"✗ Failed to cancel {order_id}: {e}")

    def get_order_summary(self) -> Dict:
        """Get order execution summary"""
        return {
            'pending_orders': len(self.pending_orders),
            'filled_orders': len(self.filled_orders),
            'rejected_orders': len(self.rejected_orders),
            'fill_rate': len(self.filled_orders) / max(1, len(self.filled_orders) + len(self.rejected_orders)) * 100
        }
