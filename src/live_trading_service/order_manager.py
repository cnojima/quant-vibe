"""Order management for live trading engine.

Handles order submission in two modes:
1. Simulated mode (paper_trading=True): Simulate fills internally
2. Live mode (paper_trading=False): Submit to Schwab API

Simulated mode provides realistic fill simulation without broker interaction.
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from enum import Enum

from quant_vibe.logging import setup_normalized_logging, get_logger
from quant_vibe.strategies.options_base import OptionsPosition, OptionLeg
from quant_vibe.utils import now_utc


class OrderStatus(Enum):
    """Order status states."""
    PENDING = "pending"
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    ERROR = "error"


class OrderSide(Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OCOStatus(Enum):
    """OCO (One Cancels Other) status."""
    PENDING = "pending"
    PROFIT_FILLED = "profit_filled"
    STOP_FILLED = "stop_filled"
    CANCELLED = "cancelled"
    FAILED = "failed"


class Order:
    """Represents a single order."""

    def __init__(
        self,
        order_id: str,
        position_id: str,
        strategy_name: str,
        legs: List[Dict],
        order_type: str = "LIMIT",
        time_in_force: str = "DAY",
        action_type: str = "opening"  # 'opening' or 'closing'
    ):
        self.order_id = order_id
        self.position_id = position_id
        self.strategy_name = strategy_name
        self.legs = legs  # List of leg dicts with symbol, quantity, side, price
        self.order_type = order_type
        self.time_in_force = time_in_force
        self.action_type = action_type  # 'opening' or 'closing'

        self.status = OrderStatus.PENDING
        self.submitted_time: Optional[datetime] = None
        self.filled_time: Optional[datetime] = None
        self.broker_order_id: Optional[str] = None
        self.expected_total_price: Optional[float] = None
        self.filled_total_price: Optional[float] = None
        self.error_message: Optional[str] = None

        # OCO tracking
        self.has_oco_children: bool = False
        self.oco_group_id: Optional[str] = None
        self.profit_target_order_id: Optional[str] = None
        self.stop_loss_order_id: Optional[str] = None
        self.profit_target_price: Optional[float] = None
        self.stop_loss_price: Optional[float] = None
        self.oco_status: Optional[OCOStatus] = None
        self.oco_children: Optional[List[Dict]] = None  # Full OCO child order structures


class OrderManager:
    """Manages order submission and tracking.

    Supports two modes:
    - Simulated (paper_trading=True): Internal fill simulation
    - Live (paper_trading=False): Schwab API submission
    """

    def __init__(
        self,
        paper_trading: bool = True,
        schwab_client=None,
        state_store=None,
        use_oco: bool = False,
        oco_config: Optional[Dict] = None,
    ):
        """
        Initialize order manager.

        Args:
            paper_trading: If True, simulate fills internally
            schwab_client: Schwab API client (required for live mode)
            state_store: StateStore for persistence
            use_oco: If True, build OCO child orders for profit/stop
            oco_config: OCO configuration dict with profit_target_pct, stop_loss_pct
            logger: Logger instance
        """
        self.paper_trading = paper_trading
        self.schwab_client = schwab_client
        self.state_store = state_store
        self.use_oco = use_oco
        self.logger = get_logger(f'live_trading{self.paper_trading and "_paper" or "_real"}')

        # OCO configuration defaults
        self.oco_config = oco_config or {
            'profit_target_pct': 0.50,  # 50% profit
            'stop_loss_pct': -0.30,     # -30% loss
            'use_market_on_stop': True,  # Market order for stops
            'verify_placement': True     # Verify OCO orders placed
        }

        # Track active orders
        self.active_orders: Dict[str, Order] = {}

        # Validate configuration
        if not paper_trading and schwab_client is None:
            raise ValueError("schwab_client required when paper_trading=False")

        self.logger.info(
            f"OrderManager initialized in {'SIMULATED' if paper_trading else 'LIVE'} mode"
        )
        if use_oco:
            self.logger.info(f"OCO orders enabled: PT={self.oco_config['profit_target_pct']*100}%, SL={self.oco_config['stop_loss_pct']*100}%")

    def submit_position_entry(
        self,
        position: OptionsPosition,
        options_data: Dict[str, Dict],
        strategy_name: str
    ) -> Tuple[bool, str, Optional[Order]]:
        """
        Submit order to open a new position.

        Args:
            position: OptionsPosition to open
            options_data: Current options quotes {symbol: {bid, ask, ...}}
            strategy_name: Name of strategy submitting order

        Returns:
            Tuple of (success, message, order)
        """
        self.logger.debug(f"submit_position_entry() called: strategy={strategy_name}, position={position.position_id}, paper_trading={self.paper_trading}")

        # Create order
        order = self._create_order_from_position(position, strategy_name, is_opening=True)

        # Log clear OPEN order intent
        legs_summary = ", ".join([
            f"{leg['side'].upper()} {leg['quantity']}x {leg['symbol']}"
            for leg in order.legs
        ])
        self.logger.info(f"[OPENING] Position {position.position_id} | {strategy_name} | {legs_summary}")

        # Calculate expected price from position legs
        expected_price = self._calculate_expected_price(position.legs, options_data)
        order.expected_total_price = expected_price

        if self.paper_trading:
            # Simulated mode
            self.logger.debug(f"Simulating fill for order {order.order_id}")
            success, message = self._simulate_fill(order, options_data, is_opening=True)
        else:
            # Live mode
            self.logger.debug(f"Submitting order {order.order_id} to Schwab API")
            success, message = self._submit_to_schwab(order)

        self.logger.debug(f"Order submission result: success={success}, message={message}")

        if success:
            self.active_orders[order.order_id] = order
            self._persist_order(order)
            self.logger.debug(f"Order {order.order_id} added to active orders")

        return success, message, order if success else None

    def submit_position_exit(
        self,
        position: OptionsPosition,
        options_data: Dict[str, Dict],
        strategy_name: str
    ) -> Tuple[bool, str, Optional[Order]]:
        """
        Submit order to close an existing position.

        Args:
            position: OptionsPosition to close
            options_data: Current options quotes
            strategy_name: Name of strategy

        Returns:
            Tuple of (success, message, order)
        """
        self.logger.debug(f"submit_position_exit() called: strategy={strategy_name}, position={position.position_id}")

        # Create closing order (reverse sides)
        order = self._create_order_from_position(position, strategy_name, is_opening=False)

        # Log clear CLOSE order intent
        legs_summary = ", ".join([
            f"{leg['side'].upper()} {leg['quantity']}x {leg['symbol']}"
            for leg in order.legs
        ])
        self.logger.info(f"[CLOSING] Position {position.position_id} | {strategy_name} | {legs_summary}")

        # Calculate expected exit price
        expected_price = self._calculate_exit_price(position.legs, options_data)
        order.expected_total_price = expected_price

        if self.paper_trading:
            success, message = self._simulate_fill(order, options_data, is_opening=False)
        else:
            success, message = self._submit_to_schwab(order)

        if success:
            self.active_orders[order.order_id] = order
            self._persist_order(order)

        return success, message, order if success else None

    def _create_order_from_position(
        self,
        position: OptionsPosition,
        strategy_name: str,
        is_opening: bool
    ) -> Order:
        """Create Order from OptionsPosition."""
        order_id = f"ORD_{uuid.uuid4().hex[:12]}"

        # Convert legs to order format
        order_legs = []
        for leg in position.legs:
            # Determine side based on opening vs closing
            if is_opening:
                side = OrderSide.BUY if leg.quantity > 0 else OrderSide.SELL
            else:
                # Reverse for closing
                side = OrderSide.SELL if leg.quantity > 0 else OrderSide.BUY

            order_legs.append({
                'symbol': leg.contract_symbol,
                'quantity': abs(leg.quantity),
                'side': side.value,
                'option_type': leg.option_type.value,
                'strike': leg.strike_price,
                'expiration': leg.expiration_date.strftime('%Y-%m-%d') if isinstance(leg.expiration_date, datetime) else str(leg.expiration_date),
                'entry_price': leg.entry_price
            })

        order = Order(
            order_id=order_id,
            position_id=position.position_id,
            strategy_name=strategy_name,
            legs=order_legs,
            action_type="opening" if is_opening else "closing"
        )

        return order

    def _calculate_expected_price(
        self,
        legs: List[OptionLeg],
        options_data: Dict[str, Dict]
    ) -> float:
        """
        Calculate expected entry price (debit/credit).

        Positive = debit (we pay)
        Negative = credit (we receive)

        NOTE: Result includes × 100 multiplier to match position.current_value convention.
        """
        total = 0.0

        for leg in legs:
            quote = options_data.get(leg.contract_symbol, {})

            if not quote:
                self.logger.warning(f"No quote data for {leg.contract_symbol}")
                continue

            # Buy at ask, sell at bid
            if leg.quantity > 0:  # Buying
                price = quote.get('ask', quote.get('close', 0))
            else:  # Selling
                price = quote.get('bid', quote.get('close', 0))

            # Apply × 100 multiplier for options contracts
            total += price * abs(leg.quantity) * 100 * (1 if leg.quantity > 0 else -1)

        return total

    def _calculate_exit_price(
        self,
        legs: List[OptionLeg],
        options_data: Dict[str, Dict]
    ) -> float:
        """
        Calculate expected exit value (cash flow from closing position).

        Uses "cash flow from exiting" convention to match position.current_value:
        - Long positions: POSITIVE value (credit received from selling)
        - Short positions: NEGATIVE value (debit paid to buy back)

        This aligns with P&L formula: P&L = exit_value - entry_cost
        - Long profit: exit_value > entry_cost (sold for more than paid)
        - Short profit: exit_value > entry_cost (bought back for less than received)

        NOTE: Result includes × 100 multiplier for options contracts.
        """
        total = 0.0

        for leg in legs:
            quote = options_data.get(leg.contract_symbol, {})

            if not quote:
                self.logger.warning(f"No quote data for {leg.contract_symbol}")
                continue

            # Get exit price (we reverse the side)
            if leg.quantity > 0:  # Originally bought, now selling at bid
                price = quote.get('bid', quote.get('close', 0))
                # Long position: selling = POSITIVE (credit received)
                total += price * abs(leg.quantity) * 100
            else:  # Originally sold, now buying back at ask
                price = quote.get('ask', quote.get('close', 0))
                # Short position: buying = NEGATIVE (debit paid)
                total -= price * abs(leg.quantity) * 100

        return total

    def _simulate_fill(
        self,
        order: Order,
        options_data: Dict[str, Dict],
        is_opening: bool = True
    ) -> Tuple[bool, str]:
        """
        Simulate order fill with realistic slippage.

        Args:
            order: Order to fill
            options_data: Current options quotes
            is_opening: Whether this is an opening trade (True) or closing trade (False)

        Returns:
            Tuple of (success, message)
        """
        try:
            # Calculate fill price with slippage
            filled_price = 0.0

            for leg_dict in order.legs:
                symbol = leg_dict['symbol']
                quantity = leg_dict['quantity']
                side = leg_dict['side']

                quote = options_data.get(symbol, {})
                if not quote:
                    return False, f"No quote data for {symbol}"

                # Get base price (bid/ask)
                if side == 'buy':
                    base_price = quote.get('ask', quote.get('close', 0))
                else:
                    base_price = quote.get('bid', quote.get('close', 0))

                # Apply slippage based on DTE
                dte = self._calculate_dte(leg_dict['expiration'])
                slippage_pct = self._get_slippage_model(dte, base_price)

                # Slippage unfavorable: pay more when buying, receive less when selling
                if side == 'buy':
                    fill_price = base_price * (1 + slippage_pct)
                else:
                    fill_price = base_price * (1 - slippage_pct)

                # Accumulate (buy is positive cost, sell is negative cost)
                # Each options contract represents 100 shares
                if side == 'buy':
                    filled_price += fill_price * quantity * 100
                else:
                    filled_price -= fill_price * quantity * 100

            # Mark as filled
            order.status = OrderStatus.FILLED
            order.submitted_time = now_utc()
            order.filled_time = now_utc()
            order.filled_total_price = filled_price

            # Log fill with clear open/close indicator
            order_type = "OPENING" if is_opening else "CLOSING"
            self.logger.info(
                f"[{order_type}] Simulated fill: {order.order_id} | "
                f"Expected: ${order.expected_total_price:.2f} | "
                f"Filled: ${filled_price:.2f} | "
                f"Slippage: ${filled_price - order.expected_total_price:.2f}"
            )

            return True, "Order filled (simulated)"

        except Exception as e:
            order.status = OrderStatus.ERROR
            order.error_message = str(e)
            self.logger.error(f"Simulation error: {e}", exc_info=True)
            return False, f"Simulation error: {e}"

    def _get_slippage_model(self, dte: int, price: float) -> float:
        """
        Get slippage percentage based on DTE and price.

        Returns slippage as decimal (0.01 = 1%)
        """
        # Base slippage by DTE
        if dte == 0:
            # 0 DTE: High volatility, wide spreads
            base_slippage = 0.03  # 3%
            if price < 0.50:
                base_slippage = 0.10  # 10% for cheap options
        elif dte == 1:
            base_slippage = 0.02  # 2%
            if price < 0.50:
                base_slippage = 0.08
        elif dte <= 7:
            base_slippage = 0.015  # 1.5%
        else:
            base_slippage = 0.01  # 1%

        return base_slippage

    def _calculate_dte(self, expiration_str: str) -> int:
        """Calculate days to expiration."""
        try:
            # Parse expiration date (format: YYYY-MM-DD or YYYYMMDD)
            if '-' in expiration_str:
                exp_date = datetime.strptime(expiration_str, '%Y-%m-%d').date()
            else:
                exp_date = datetime.strptime(expiration_str, '%Y%m%d').date()

            today = now_utc().date()
            dte = (exp_date - today).days
            return max(0, dte)
        except Exception as e:
            self.logger.warning(f"Error calculating DTE: {e}")
            return 7  # Default to 7 days if parse fails

    def _submit_to_schwab(self, order: Order) -> Tuple[bool, str]:
        """
        Submit order to Schwab API (live mode).

        Args:
            order: Order to submit

        Returns:
            Tuple of (success, message)
        """
        try:
            # Build Schwab API order structure
            schwab_order = self._build_schwab_order_structure(order)

            # Log order details
            self.logger.info(
                f"Submitting {order.action_type} order to Schwab: "
                f"Order ID={order.order_id}, Position={order.position_id}, "
                f"Legs={len(order.legs)}, Type={order.order_type}"
            )

            # Get account number
            if not hasattr(self.schwab_client, 'account_number') or not self.schwab_client.account_number:
                # Fetch account number if not already set
                response = self.schwab_client.client.linked_accounts()
                response.raise_for_status()
                accounts = response.json()
                if not accounts:
                    return False, "No Schwab accounts found"
                self.schwab_client.account_number = accounts[0]['hashValue']
                self.logger.info(f"Using Schwab account: {self.schwab_client.account_number[:8]}...")

            # Submit order to Schwab API
            response = self.schwab_client.client.place_order(
                self.schwab_client.account_number,
                schwab_order
            )
            response.raise_for_status()

            # Extract order ID from Location header
            location = response.headers.get('Location', '')
            broker_order_id = location.split('/')[-1] if location else None

            # Update order status
            order.status = OrderStatus.SUBMITTED
            order.submitted_time = now_utc()
            order.broker_order_id = broker_order_id

            self.logger.info(
                f"Order submitted successfully: {order.order_id} -> "
                f"Broker Order ID: {broker_order_id}"
            )

            return True, f"Order submitted successfully (Broker ID: {broker_order_id})"

        except Exception as e:
            error_msg = f"Failed to submit order to Schwab: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            order.status = OrderStatus.ERROR
            order.error_message = error_msg
            return False, error_msg

    def _build_schwab_order_structure(self, order: Order) -> Dict:
        """
        Build Schwab API order structure from Order object.

        Args:
            order: Order to convert

        Returns:
            Schwab API order structure
        """
        # Build order legs in Schwab format
        order_legs = []
        for leg in order.legs:
            # Map our side to Schwab instruction
            if order.action_type == "opening":
                instruction = "BUY_TO_OPEN" if leg['side'] == 'buy' else "SELL_TO_OPEN"
            else:  # closing
                instruction = "BUY_TO_CLOSE" if leg['side'] == 'buy' else "SELL_TO_CLOSE"

            order_legs.append({
                'instruction': instruction,
                'quantity': leg['quantity'],
                'instrument': {
                    'assetType': 'OPTION',
                    'symbol': leg['symbol']
                }
            })

        # Build base order structure
        schwab_order = {
            'orderStrategyType': 'SINGLE',
            'session': 'NORMAL',
            'duration': order.time_in_force,
            'orderType': order.order_type,
            'orderLegCollection': order_legs
        }

        # Add price for LIMIT orders
        if order.order_type == 'LIMIT' and order.expected_total_price is not None:
            # Convert total price to per-spread price
            # expected_total_price already includes the × 100 multiplier
            # For Schwab API, we need price per contract (not total)
            # Calculate the net credit/debit per spread
            if len(order.legs) > 0:
                # Total contracts in the spread
                total_quantity = sum(leg['quantity'] for leg in order.legs)
                if total_quantity > 0:
                    # Price per spread = total_price / (quantity × 100)
                    price_per_spread = abs(order.expected_total_price) / (total_quantity * 100)
                    schwab_order['price'] = round(price_per_spread, 2)

        return schwab_order

    def _cancel_schwab_order(self, order: Order) -> Tuple[bool, str]:
        """
        Cancel order via Schwab API.

        Args:
            order: Order to cancel

        Returns:
            Tuple of (success, message)
        """
        try:
            # Check if we have a broker order ID
            if not order.broker_order_id:
                error_msg = "Cannot cancel order: no broker order ID"
                self.logger.error(f"{error_msg} for order {order.order_id}")
                return False, error_msg

            # Get account number
            if not hasattr(self.schwab_client, 'account_number') or not self.schwab_client.account_number:
                # Fetch account number if not already set
                response = self.schwab_client.client.linked_accounts()
                response.raise_for_status()
                accounts = response.json()
                if not accounts:
                    return False, "No Schwab accounts found"
                self.schwab_client.account_number = accounts[0]['hashValue']

            self.logger.info(
                f"Cancelling order with Schwab: Order ID={order.order_id}, "
                f"Broker ID={order.broker_order_id}"
            )

            # Cancel order via Schwab API
            response = self.schwab_client.client.cancel_order(
                self.schwab_client.account_number,
                order.broker_order_id
            )
            response.raise_for_status()

            # Update order status
            order.status = OrderStatus.CANCELLED
            self._persist_order(order)

            self.logger.info(f"Order cancelled successfully: {order.order_id}")
            return True, "Order cancelled successfully"

        except Exception as e:
            error_msg = f"Failed to cancel order: {str(e)}"
            self.logger.error(error_msg, exc_info=True)

            # If the order was already filled/cancelled at the broker, update our status
            if "not found" in str(e).lower() or "already" in str(e).lower():
                self.logger.warning(f"Order may already be filled/cancelled at broker: {order.order_id}")
                # You might want to query the order status here to verify

            return False, error_msg

    def _submit_schwab_oco_order(self, order: Order, schwab_structure: Dict) -> Tuple[bool, str]:
        """
        Submit OCO order structure to Schwab API.

        Args:
            order: Order object to update with submission results
            schwab_structure: Complete Schwab OCO order structure

        Returns:
            Tuple of (success, message)
        """
        try:
            # Log order details
            self.logger.info(
                f"Submitting OCO order to Schwab: "
                f"Order ID={order.order_id}, Position={order.position_id}, "
                f"Entry Legs={len(order.legs)}, OCO Children=2"
            )

            # Get account number
            if not hasattr(self.schwab_client, 'account_number') or not self.schwab_client.account_number:
                # Fetch account number if not already set
                response = self.schwab_client.client.linked_accounts()
                response.raise_for_status()
                accounts = response.json()
                if not accounts:
                    return False, "No Schwab accounts found"
                self.schwab_client.account_number = accounts[0]['hashValue']
                self.logger.info(f"Using Schwab account: {self.schwab_client.account_number[:8]}...")

            # Submit OCO order to Schwab API
            response = self.schwab_client.client.place_order(
                self.schwab_client.account_number,
                schwab_structure
            )
            response.raise_for_status()

            # Extract order ID from Location header
            location = response.headers.get('Location', '')
            broker_order_id = location.split('/')[-1] if location else None

            # Update order status
            order.status = OrderStatus.SUBMITTED
            order.submitted_time = now_utc()
            order.broker_order_id = broker_order_id

            self.logger.info(
                f"OCO order submitted successfully: {order.order_id} -> "
                f"Broker Order ID: {broker_order_id} "
                f"(Entry + Profit Target + Stop Loss)"
            )

            return True, f"OCO order submitted successfully (Broker ID: {broker_order_id})"

        except Exception as e:
            error_msg = f"Failed to submit OCO order to Schwab: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            order.status = OrderStatus.ERROR
            order.error_message = error_msg
            return False, error_msg

    def _persist_order(self, order: Order):
        """Save order to state store."""
        if not self.state_store:
            return

        # Determine side classification
        if len(order.legs) == 1:
            # Single-leg: use actual side (buy/sell)
            side = order.legs[0]['side']
        else:
            # Multi-leg: classify as DEBIT or CREDIT spread
            # Debit spread: we pay (positive expected_price)
            # Credit spread: we receive (negative expected_price)
            if order.expected_total_price is not None:
                if order.expected_total_price > 0:
                    side = 'debit'  # We pay to enter
                elif order.expected_total_price < 0:
                    side = 'credit'  # We receive to enter
                else:
                    side = 'multi_leg'  # Net-zero (rare)
            else:
                side = 'multi_leg'  # Fallback if price not set yet

        order_data = {
            'order_id': order.order_id,
            'position_id': order.position_id,
            'strategy_name': order.strategy_name,
            'order_type': order.order_type,
            'action_type': order.action_type,  # 'opening' or 'closing'
            'side': side,  # BUG FIX: use actual side for single-leg
            'quantity': len(order.legs),
            'symbol': order.legs[0]['symbol'] if order.legs else 'N/A',
            'status': order.status.value,
            'submitted_time': order.submitted_time,
            'filled_time': order.filled_time,  # BUG FIX: was missing
            'expected_price': order.expected_total_price,
            'filled_price': order.filled_total_price,
            'broker_order_id': order.broker_order_id,
            'metadata': {
                'legs': order.legs,
                'time_in_force': order.time_in_force,
                'error_message': order.error_message
            }
        }

        try:
            self.state_store.save_order(order_data)
        except Exception as e:
            self.logger.error(f"Failed to persist order: {e}")

    def get_order_status(self, order_id: str) -> Optional[OrderStatus]:
        """Get status of an order."""
        order = self.active_orders.get(order_id)
        return order.status if order else None

    def get_active_orders(self) -> List[Order]:
        """Get all active orders."""
        return list(self.active_orders.values())

    def cancel_order(self, order_id: str) -> Tuple[bool, str]:
        """
        Cancel an order.

        Args:
            order_id: Order to cancel

        Returns:
            Tuple of (success, message)
        """
        order = self.active_orders.get(order_id)
        if not order:
            return False, "Order not found"

        if order.status in [OrderStatus.FILLED, OrderStatus.CANCELLED]:
            return False, f"Order already {order.status.value}"

        if self.paper_trading:
            # Simulated cancellation
            order.status = OrderStatus.CANCELLED
            self._persist_order(order)
            return True, "Order cancelled (simulated)"
        else:
            # Live cancellation via Schwab API
            return self._cancel_schwab_order(order)

    # ========================================================================
    # OCO (One Cancels Other) Order Construction
    # ========================================================================

    def _calculate_oco_exit_prices(
        self,
        position: OptionsPosition,
        entry_price: float
    ) -> Tuple[float, float]:
        """
        Calculate profit target and stop loss prices for OCO.

        Args:
            position: Position with profit_target and stop_loss defined
            entry_price: Expected or actual entry fill price

        Returns:
            Tuple of (profit_target_price, stop_loss_price)

        Note:
            For debit spreads (entry_price > 0): profit when exit > entry
            For credit spreads (entry_price < 0): profit when exit < abs(entry)
        """
        # Use position's targets if defined, otherwise use config defaults
        profit_target_pct = position.profit_target if position.profit_target else self.oco_config['profit_target_pct']
        stop_loss_pct = position.stop_loss if position.stop_loss else self.oco_config['stop_loss_pct']

        # Calculate target prices
        profit_price = entry_price * (1 + profit_target_pct)
        stop_price = entry_price * (1 + stop_loss_pct)

        self.logger.debug(
            f"OCO prices calculated: Entry=${entry_price:.2f}, "
            f"Profit=${profit_price:.2f} ({profit_target_pct*100:.1f}%), "
            f"Stop=${stop_price:.2f} ({stop_loss_pct*100:.1f}%)"
        )

        return profit_price, stop_price

    def _build_oco_children(
        self,
        position: OptionsPosition,
        profit_price: float,
        stop_price: float
    ) -> List[Dict]:
        """
        Build OCO child order structures (profit target and stop loss).

        Args:
            position: Position to create exits for
            profit_price: Profit target exit price
            stop_price: Stop loss exit price

        Returns:
            List containing profit target and stop loss order structures
        """
        # Generate unique order IDs for children
        profit_order_id = f"OCO_PROFIT_{uuid.uuid4().hex[:12]}"
        stop_order_id = f"OCO_STOP_{uuid.uuid4().hex[:12]}"

        # Build exit legs (reverse of entry)
        exit_legs = []
        for leg in position.legs:
            # Reverse: buy becomes sell, sell becomes buy
            if leg.quantity > 0:
                instruction = "SELL_TO_CLOSE"
            else:
                instruction = "BUY_TO_CLOSE"

            exit_legs.append({
                'instruction': instruction,
                'quantity': abs(leg.quantity),
                'symbol': leg.contract_symbol,
                'option_type': leg.option_type.value,
                'strike': leg.strike_price,
                'expiration': leg.expiration_date.strftime('%Y-%m-%d') if isinstance(leg.expiration_date, datetime) else str(leg.expiration_date)
            })

        # Profit Target Child (LIMIT order)
        profit_child = {
            'order_id': profit_order_id,
            'order_strategy_type': 'SINGLE',
            'order_type': 'LIMIT',
            'price': profit_price,
            'session': 'NORMAL',
            'duration': 'GOOD_TILL_CANCEL',
            'legs': exit_legs.copy()
        }

        # Stop Loss Child (STOP or STOP_MARKET)
        if self.oco_config.get('use_market_on_stop', True):
            stop_order_type = 'STOP_MARKET'
        else:
            stop_order_type = 'STOP_LIMIT'

        stop_child = {
            'order_id': stop_order_id,
            'order_strategy_type': 'SINGLE',
            'order_type': stop_order_type,
            'stop_price': stop_price,
            'session': 'NORMAL',
            'duration': 'GOOD_TILL_CANCEL',
            'legs': exit_legs.copy()
        }

        # Add limit price for STOP_LIMIT
        if stop_order_type == 'STOP_LIMIT':
            # Set limit slightly worse than stop for guaranteed fill
            stop_child['price'] = stop_price * 0.95  # 5% worse

        self.logger.debug(
            f"Built OCO children: Profit={profit_order_id}, Stop={stop_order_id}"
        )

        return [profit_child, stop_child]

    def _build_schwab_oco_structure(
        self,
        entry_order: Order,
        oco_children: List[Dict]
    ) -> Dict:
        """
        Build complete Schwab API order structure with OCO children.

        This creates a TRIGGER order: entry order triggers OCO children.

        Args:
            entry_order: Parent entry order
            oco_children: List of [profit_child, stop_child] structures

        Returns:
            Complete Schwab API order structure
        """
        # Build entry leg collection for Schwab format
        entry_legs_schwab = []
        for leg in entry_order.legs:
            entry_legs_schwab.append({
                'instruction': 'BUY_TO_OPEN' if leg['side'] == 'buy' else 'SELL_TO_OPEN',
                'quantity': leg['quantity'],
                'instrument': {
                    'assetType': 'OPTION',
                    'symbol': leg['symbol']
                }
            })

        # Build OCO child strategies for Schwab format
        oco_child_strategies = []
        for child in oco_children:
            child_legs = []
            for leg in child['legs']:
                child_legs.append({
                    'instruction': leg['instruction'],
                    'quantity': leg['quantity'],
                    'instrument': {
                        'assetType': 'OPTION',
                        'symbol': leg['symbol']
                    }
                })

            child_order = {
                'orderStrategyType': child['order_strategy_type'],
                'session': child['session'],
                'duration': child['duration'],
                'orderType': child['order_type'],
                'orderLegCollection': child_legs
            }

            # Add price fields based on order type
            if 'price' in child:
                child_order['price'] = child['price']
            if 'stop_price' in child:
                child_order['stopPrice'] = child['stop_price']

            oco_child_strategies.append(child_order)

        # Build complete order with TRIGGER strategy
        schwab_order = {
            'orderStrategyType': 'TRIGGER',
            'session': 'NORMAL',
            'duration': entry_order.time_in_force,
            'orderType': entry_order.order_type,
            'orderLegCollection': entry_legs_schwab,
            'childOrderStrategies': [
                {
                    'orderStrategyType': 'OCO',
                    'childOrderStrategies': oco_child_strategies
                }
            ]
        }

        # Add price for LIMIT entry orders
        if entry_order.order_type == 'LIMIT' and entry_order.expected_total_price is not None:
            # Convert total price to per-spread price (same logic as _build_schwab_order_structure)
            if len(entry_order.legs) > 0:
                total_quantity = sum(leg['quantity'] for leg in entry_order.legs)
                if total_quantity > 0:
                    # Price per spread = total_price / (quantity × 100)
                    price_per_spread = abs(entry_order.expected_total_price) / (total_quantity * 100)
                    schwab_order['price'] = round(price_per_spread, 2)

        self.logger.debug(
            f"Built Schwab OCO structure: Entry order {entry_order.order_id} with 2 OCO children"
        )

        return schwab_order

    def submit_position_entry_with_oco(
        self,
        position: OptionsPosition,
        options_data: Dict[str, Dict],
        strategy_name: str
    ) -> Tuple[bool, str, Optional[Order]]:
        """
        Submit position entry order with OCO profit target and stop loss.

        Args:
            position: OptionsPosition to open
            options_data: Current options quotes
            strategy_name: Name of strategy submitting order

        Returns:
            Tuple of (success, message, order)

        Note:
            In simulated mode, OCO structure is built and logged but not used.
            In live mode, OCO structure is submitted to Schwab API.
        """
        # Create base entry order
        order = self._create_order_from_position(position, strategy_name, is_opening=True)

        # Calculate expected entry price
        expected_price = self._calculate_expected_price(position.legs, options_data)
        order.expected_total_price = expected_price

        # Calculate OCO exit prices
        profit_price, stop_price = self._calculate_oco_exit_prices(position, expected_price)

        # Build OCO children
        oco_children = self._build_oco_children(position, profit_price, stop_price)

        # Generate OCO group ID
        oco_group_id = f"OCO_{uuid.uuid4().hex[:12]}"

        # Attach OCO metadata to order
        order.has_oco_children = True
        order.oco_group_id = oco_group_id
        order.profit_target_order_id = oco_children[0]['order_id']
        order.stop_loss_order_id = oco_children[1]['order_id']
        order.profit_target_price = profit_price
        order.stop_loss_price = stop_price
        order.oco_status = OCOStatus.PENDING
        order.oco_children = oco_children

        self.logger.info(
            f"Entry order with OCO: Position={position.position_id}, "
            f"Entry=${expected_price:.2f}, Profit=${profit_price:.2f}, Stop=${stop_price:.2f}"
        )

        if self.paper_trading:
            # Simulated mode: Build OCO structure but use regular simulation
            self.logger.info("Simulated mode: OCO structure built but not submitted (using manual monitoring)")

            # Build Schwab structure for logging purposes
            schwab_structure = self._build_schwab_oco_structure(order, oco_children)

            # Log the structure
            self.logger.debug(f"OCO Schwab structure (not submitted): {schwab_structure}")

            # Store in order metadata for inspection
            if order.oco_children:
                order.oco_children.append({'schwab_format': schwab_structure})

            # Simulate fill as usual (OCO not actually used in simulation)
            success, message = self._simulate_fill(order, options_data)
        else:
            # Live mode: Submit with OCO to Schwab API
            schwab_structure = self._build_schwab_oco_structure(order, oco_children)
            success, message = self._submit_schwab_oco_order(order, schwab_structure)

        if success:
            self.active_orders[order.order_id] = order
            self._persist_order(order)

        return success, message, order if success else None
