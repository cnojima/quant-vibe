"""
Bollinger Band Limit Strategy - A directional strategy using Bollinger Bands with limit orders.

This strategy:
1. Uses Bollinger Bands to determine bullish (call) or bearish (put) direction
   - Price near/below lower band = bullish (buy calls)
   - Price near/above upper band = bearish (buy puts)
2. Finds an option strike 10-15% OTM, targeting contracts priced near $2.00
3. Sets a limit buy order at $1.00 (50% of target value)
4. When filled, immediately sets a sell order for 100% profit ($2.00)
5. Maximum trades per day limit enforced
"""

from datetime import datetime, time, timedelta
from typing import Dict, Optional, Any, List
from dataclasses import dataclass
from enum import Enum

import pandas as pd
import pytz

from quant_vibe.indicators.technical import calculate_bollinger_bands
from quant_vibe.strategies.options_base import (
    OptionLeg,
    OptionsPosition,
    OptionsStrategy,
    OptionType,
    SpreadType,
)
from quant_vibe.utils import generate_position_id


class OrderStatus(Enum):
    """Status of a limit order."""
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


@dataclass
class LimitOrder:
    """Represents a pending limit order."""
    order_id: str
    contract_symbol: str
    option_type: OptionType
    strike_price: float
    expiration_date: datetime
    quantity: int
    limit_price: float
    direction: str  # 'buy' or 'sell'
    status: OrderStatus = OrderStatus.PENDING
    created_time: Optional[datetime] = None
    filled_time: Optional[datetime] = None
    filled_price: Optional[float] = None


class BollingerBandLimitStrategy(OptionsStrategy):
    """
    Bollinger Band strategy with limit orders for entry and exit.

    Strategy Logic:
    - Use Bollinger Bands to determine direction:
      * Price near/below lower band = bullish (buy calls)
      * Price near/above upper band = bearish (buy puts)
    - Find options with strikes 10-15% OTM, priced near target (~$2)
    - Place limit buy order at $1 (50% of target)
    - When filled, immediately place sell order at $2 (100% profit)
    - Max trades per day limit enforced

    This is purely for educational/experimental purposes.
    """

    def __init__(
        self,
        target_contract_price: float = 2.0,
        limit_buy_price: float = 1.0,
        profit_target_price: float = 2.0,
        otm_percent_min: float = 0.10,  # 10% OTM minimum
        otm_percent_max: float = 0.15,  # 15% OTM maximum
        price_tolerance: float = 1.0,  # How far from $2 to accept
        max_trades_daily: int = 5,
        quantity: int = 10,
        min_dte: int = 0,
        max_dte: int = 45,
        stop_loss_pct: Optional[float] = 0.50,  # 50% stop loss
        order_expiry_minutes: int = 60,  # Cancel unfilled orders after 60 min
        bb_period: int = 20,  # Bollinger Band period
        bb_std: float = 2.0,  # Bollinger Band standard deviations
        bb_threshold: float = 0.0,  # How close to band to trigger (0 = at band)
        **kwargs,
    ):
        """
        Initialize BollingerBandLimitStrategy.

        Args:
            target_contract_price: Target option price to search near ($2.00 default)
            limit_buy_price: Limit price for buy orders ($1.00 default = 50% of target)
            profit_target_price: Target sell price for 100% profit ($2.00 default)
            otm_percent_min: Minimum OTM percentage (0.10 = 10%)
            otm_percent_max: Maximum OTM percentage (0.15 = 15%)
            price_tolerance: Search range around target_price (±$1.00 default)
            max_trades_daily: Maximum number of trades per day (5 default)
            quantity: Number of contracts to trade (10 default)
            min_dte: Minimum days to expiration (0 default)
            max_dte: Maximum days to expiration (45 default)
            stop_loss_pct: Stop loss as percentage (0.50 = 50%)
            order_expiry_minutes: Cancel unfilled orders after this many minutes
            bb_period: Bollinger Band moving average period (20 default)
            bb_std: Bollinger Band standard deviations (2.0 default)
            bb_threshold: How close to band to trigger signal (0 = at band)
        """
        # Calculate profit target percentage for position tracking
        # Buy at $1, sell at $2 = 100% profit
        calculated_profit_target_pct = (profit_target_price - limit_buy_price) / limit_buy_price

        super().__init__(
            name="BollingerBandLimit",
            max_trades_daily=max_trades_daily,
            quantity=quantity,
            min_dte=min_dte,
            max_dte=max_dte,
            otm_percent_min=otm_percent_min,
            otm_percent_max=otm_percent_max,
            profit_target_pct=calculated_profit_target_pct,
            stop_loss_pct=stop_loss_pct,
            **kwargs,
        )

        # Strategy-specific parameters (not in base class)
        self.target_contract_price = target_contract_price
        self.limit_buy_price = limit_buy_price
        self.profit_target_price = profit_target_price
        self.price_tolerance = price_tolerance
        self.order_expiry_minutes = order_expiry_minutes

        # Bollinger Band parameters
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.bb_threshold = bb_threshold

        # Track current day for reset detection
        self.current_day: Optional[datetime] = None

        # Pending limit orders
        self.pending_buy_orders: List[LimitOrder] = []
        self.pending_sell_orders: List[LimitOrder] = []

        # Target contract (remembered after selection)
        self.target_contract: Optional[Dict[str, Any]] = None

    def _reset_daily_state(self, current_time: datetime) -> None:
        """Reset daily state if it's a new day."""
        if self.current_day is None or self.current_day.date() != current_time.date():
            self.current_day = current_time
            self.trades_today = 0
            # Cancel any pending buy orders from previous day
            for order in self.pending_buy_orders:
                if order.status == OrderStatus.PENDING:
                    order.status = OrderStatus.EXPIRED
            self.pending_buy_orders = []
            self.target_contract = None

    def _determine_direction_from_bollinger(
        self,
        underlying_data: pd.DataFrame,
    ) -> tuple[Optional[str], Dict[str, Any]]:
        """
        Determine trade direction using Bollinger Bands.

        - Price near/below lower band = bullish (buy calls)
        - Price near/above upper band = bearish (buy puts)
        - Price in middle = no signal

        Args:
            underlying_data: DataFrame with underlying price data (must have 'close' column)

        Returns:
            Tuple of (direction, bb_info) where direction is 'call', 'put', or None
        """
        if underlying_data.empty or len(underlying_data) < self.bb_period:
            return None, {"reason": f"Insufficient data for BB calculation (need {self.bb_period} bars)"}

        # Calculate Bollinger Bands
        close_prices = underlying_data["close"]
        upper_band, middle_band, lower_band = calculate_bollinger_bands(
            close_prices, period=self.bb_period, num_std=self.bb_std
        )

        # Get current values
        current_price = close_prices.iloc[-1]
        current_upper = upper_band.iloc[-1]
        current_middle = middle_band.iloc[-1]
        current_lower = lower_band.iloc[-1]

        # Check for NaN values
        if pd.isna(current_upper) or pd.isna(current_lower) or pd.isna(current_middle):
            return None, {"reason": "Bollinger Band values are NaN"}

        # Calculate band width for threshold
        band_width = current_upper - current_lower
        threshold_distance = band_width * self.bb_threshold

        bb_info = {
            "current_price": current_price,
            "upper_band": current_upper,
            "middle_band": current_middle,
            "lower_band": current_lower,
            "band_width": band_width,
            "price_position": (current_price - current_lower) / band_width if band_width > 0 else 0.5,
        }

        # Determine direction based on price position relative to bands
        if current_price <= current_lower + threshold_distance:
            # Price at or below lower band = bullish signal (buy calls)
            bb_info["signal"] = "bullish"
            bb_info["reason"] = f"Price ${current_price:.2f} at/below lower band ${current_lower:.2f}"
            return "call", bb_info
        elif current_price >= current_upper - threshold_distance:
            # Price at or above upper band = bearish signal (buy puts)
            bb_info["signal"] = "bearish"
            bb_info["reason"] = f"Price ${current_price:.2f} at/above upper band ${current_upper:.2f}"
            return "put", bb_info
        else:
            # Price in the middle = no clear signal
            bb_info["signal"] = "neutral"
            bb_info["reason"] = f"Price ${current_price:.2f} between bands (${current_lower:.2f} - ${current_upper:.2f})"
            return None, bb_info

    def _find_target_contract(
        self,
        underlying_price: float,
        direction: str,
        options_data: pd.DataFrame,
        current_time: datetime,
    ) -> Optional[Dict[str, Any]]:
        """
        Find an option contract that meets our criteria:
        - Strike 10-15% OTM (higher for calls, lower for puts)
        - Price near $2 (or closest available)

        Args:
            underlying_price: Current price of underlying
            direction: 'call' or 'put'
            options_data: Available options data
            current_time: Current timestamp

        Returns:
            Dict with contract details or None if not found
        """
        # Calculate target strike range
        if direction == "call":
            # For calls, OTM means strike > underlying price
            strike_min = underlying_price * (1 + self.otm_percent_min)
            strike_max = underlying_price * (1 + self.otm_percent_max)
        else:
            # For puts, OTM means strike < underlying price
            strike_min = underlying_price * (1 - self.otm_percent_max)
            strike_max = underlying_price * (1 - self.otm_percent_min)

        # Calculate DTE range
        target_date = current_time + timedelta(days=self.min_dte)
        max_date = current_time + timedelta(days=self.max_dte)

        # Normalize dates for comparison
        target_date = target_date.date()
        max_date = max_date.date()

        # Filter options by type, DTE, and strike range
        options_filtered = options_data[
            (options_data["contract_type"] == direction)
            & (options_data["expiration_date"] >= target_date)
            & (options_data["expiration_date"] <= max_date)
            & (options_data["strike_price"] >= strike_min)
            & (options_data["strike_price"] <= strike_max)
        ].copy()

        if options_filtered.empty:
            # Fallback: expand search to any OTM option
            if direction == "call":
                options_filtered = options_data[
                    (options_data["contract_type"] == direction)
                    & (options_data["expiration_date"] >= target_date)
                    & (options_data["expiration_date"] <= max_date)
                    & (options_data["strike_price"] > underlying_price)
                ].copy()
            else:
                options_filtered = options_data[
                    (options_data["contract_type"] == direction)
                    & (options_data["expiration_date"] >= target_date)
                    & (options_data["expiration_date"] <= max_date)
                    & (options_data["strike_price"] < underlying_price)
                ].copy()

        if options_filtered.empty:
            return None

        # Find contracts with ask price near target (~$2)
        # If no contracts in that range, find closest to $2
        price_min = self.target_contract_price - self.price_tolerance
        price_max = self.target_contract_price + self.price_tolerance

        price_filtered = options_filtered[
            (options_filtered["ask"] >= price_min)
            & (options_filtered["ask"] <= price_max)
        ].copy()

        if not price_filtered.empty:
            options_filtered = price_filtered

        # Calculate how close each option is to our target price ($2)
        options_filtered["price_diff"] = abs(
            options_filtered["ask"].astype(float) - float(self.target_contract_price)
        )

        # Sort by price difference (closest to $2 first)
        options_filtered = options_filtered.sort_values("price_diff")

        # Pick the best one
        selected = options_filtered.iloc[0]

        return {
            "contract_symbol": selected["contract_symbol"],
            "option_type": OptionType.CALL if direction == "call" else OptionType.PUT,
            "strike_price": selected["strike_price"],
            "expiration_date": selected["expiration_date"],
            "current_ask": selected["ask"],
            "current_bid": selected.get("bid", float(selected["ask"]) * 0.9),
            "direction": direction,
        }

    def _check_buy_order_fill(
        self,
        order: LimitOrder,
        options_data: pd.DataFrame,
        current_time: datetime,
    ) -> bool:
        """
        Check if a buy limit order can be filled.

        A buy order fills when the ask price drops to or below our limit.

        Returns:
            True if order was filled
        """
        if order.status != OrderStatus.PENDING:
            return False

        # Check if order has expired
        if order.created_time:
            expiry_time = order.created_time + timedelta(minutes=self.order_expiry_minutes)
            if current_time > expiry_time:
                order.status = OrderStatus.EXPIRED
                return False

        # Find the contract in current options data
        contract_data = options_data[
            options_data["contract_symbol"] == order.contract_symbol
        ]

        if contract_data.empty:
            return False

        if contract_data.iloc[0]["ask"]:
            current_ask = float(contract_data.iloc[0]["ask"])
        else:
            print("Warning: No ask price available for contract", order.contract_symbol, contract_data.iloc[0]["ask"], current_time.astimezone(pytz.timezone("US/Eastern")).strftime("%Y-%m-%d %H:%M"))
            return False

        # Buy order fills when ask <= limit price
        if current_ask <= order.limit_price:
            order.status = OrderStatus.FILLED
            order.filled_time = current_time
            order.filled_price = current_ask  # Fill at the ask (could be better than limit)
            return True

        return False

    def _check_sell_order_fill(
        self,
        order: LimitOrder,
        options_data: pd.DataFrame,
        current_time: datetime,
    ) -> bool:
        """
        Check if a sell limit order can be filled.

        A sell order fills when the bid price rises to or above our limit.

        Returns:
            True if order was filled
        """
        if order.status != OrderStatus.PENDING:
            return False

        # Find the contract in current options data
        contract_data = options_data[
            options_data["contract_symbol"] == order.contract_symbol
        ]

        if contract_data.empty:
            return False

        current_bid = contract_data.iloc[0].get("bid", contract_data.iloc[0]["ask"] * 0.9)

        # Sell order fills when bid >= limit price
        if current_bid >= order.limit_price:
            order.status = OrderStatus.FILLED
            order.filled_time = current_time
            order.filled_price = current_bid
            return True

        return False

    def analyze_market(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
    ) -> Dict[str, Any]:
        """
        Analyze market and manage orders.

        1. Reset daily state if new day
        2. Check pending buy orders for fills
        3. Check pending sell orders for fills
        4. If no pending orders and can trade, use Bollinger Bands for direction

        Returns:
            Dict with market analysis and order status
        """
        self._reset_daily_state(current_time)

        # Get current underlying price
        if underlying_data.empty:
            return {"direction": None, "signal": False, "reason": "No underlying data"}

        current_underlying = underlying_data.iloc[-1]["close"]

        # Check pending buy orders
        filled_buy_order = None
        for order in self.pending_buy_orders:
            if self._check_buy_order_fill(order, options_data, current_time):
                filled_buy_order = order
                break

        # Check pending sell orders (for exit)
        filled_sell_order = None
        for order in self.pending_sell_orders:
            if self._check_sell_order_fill(order, options_data, current_time):
                filled_sell_order = order
                break

        # Clean up expired/filled orders
        self.pending_buy_orders = [
            o for o in self.pending_buy_orders
            if o.status == OrderStatus.PENDING
        ]

        result = {
            "underlying_price": current_underlying,
            "filled_buy_order": filled_buy_order,
            "filled_sell_order": filled_sell_order,
            "pending_buy_orders": len(self.pending_buy_orders),
            "pending_sell_orders": len([o for o in self.pending_sell_orders if o.status == OrderStatus.PENDING]),
            "trades_today": self.trades_today,
        }

        # If we have a pending buy order, don't generate new signal
        if self.pending_buy_orders:
            result["direction"] = None
            result["signal"] = False
            result["reason"] = "Buy order pending"
            return result

        # If we have an active position, don't generate new signal
        if self.active_position is not None:
            result["direction"] = None
            result["signal"] = False
            result["reason"] = "Position active"
            return result

        # Check if we've hit max trades today
        if self.trades_today >= self.max_trades_daily:
            result["direction"] = None
            result["signal"] = False
            result["reason"] = "Max trades today"
            return result

        # Use Bollinger Bands to determine direction
        direction, bb_info = self._determine_direction_from_bollinger(underlying_data)
        result["bollinger_bands"] = bb_info

        if direction is None:
            result["direction"] = None
            result["signal"] = False
            result["reason"] = bb_info.get("reason", "No Bollinger Band signal")
            return result

        # Find target contract
        target = self._find_target_contract(
            current_underlying, direction, options_data, current_time
        )

        if target is None:
            result["direction"] = direction
            result["signal"] = False
            result["reason"] = f"No suitable {direction} contracts found"
            return result

        # Remember the target contract
        self.target_contract = target

        result["direction"] = direction
        result["signal"] = True
        result["target_contract"] = target
        result["target_strike"] = target["strike_price"]
        result["current_ask"] = target["current_ask"]
        result["limit_buy_price"] = self.limit_buy_price

        return result

    def should_enter(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        market_analysis: Dict[str, Any],
    ) -> bool:
        """
        Check if we should enter a position.

        For this strategy, "entering" means placing a limit buy order,
        not actually buying yet.

        Returns:
            True if we should place a buy order
        """
        # Don't enter if we already have a position
        if self.active_position is not None:
            return False

        # Don't enter if we have pending buy orders
        if self.pending_buy_orders:
            return False

        # Don't enter if no signal
        if not market_analysis.get("signal", False):
            return False

        return True

    def construct_spread(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        market_analysis: Dict[str, Any],
        full_options_data: Optional[pd.DataFrame] = None,
    ) -> Optional[OptionsPosition]:
        """
        Place a limit buy order for the target contract.

        This doesn't actually create a position yet - it creates a pending
        limit order. The position is created when the order fills.

        Returns:
            None (position created when order fills)
        """
        if self.target_contract is None:
            return None

        target = self.target_contract
        direction = market_analysis.get("direction")

        if direction not in ["call", "put"]:
            return None

        # Create limit buy order
        date_str = current_time.strftime("%Y-%m-%d_%H%M")
        order_id = f"BBLIMIT_BUY_{date_str}_{self.trades_today + 1}"

        buy_order = LimitOrder(
            order_id=order_id,
            contract_symbol=target["contract_symbol"],
            option_type=target["option_type"],
            strike_price=target["strike_price"],
            expiration_date=target["expiration_date"],
            quantity=self.quantity,
            limit_price=self.limit_buy_price,
            direction="buy",
            status=OrderStatus.PENDING,
            created_time=current_time,
        )

        self.pending_buy_orders.append(buy_order)

        # Log the order placement
        # Note: In a real system, this would be sent to a broker
        # For backtest, the order will be checked in analyze_market

        # Increment trades counter (we count order placement as a trade attempt)
        self.trades_today += 1

        # Clear target contract
        self.target_contract = None

        # Return None - position will be created when order fills
        return None

    def create_position_from_fill(
        self,
        filled_order: LimitOrder,
        current_time: datetime,
        underlying_price: float,
    ) -> OptionsPosition:
        """
        Create a position from a filled buy order.

        Also creates a pending sell order for the profit target.

        Returns:
            OptionsPosition
        """
        # Create position
        position_id = generate_position_id(
            strategy_prefix="BBLIMIT",
            current_time=current_time,
            counter=self.trades_today + 1
        )

        leg = OptionLeg(
            contract_symbol=filled_order.contract_symbol,
            option_type=filled_order.option_type,
            strike_price=filled_order.strike_price,
            expiration_date=filled_order.expiration_date,
            quantity=filled_order.quantity,
            entry_price=filled_order.filled_price,
        )

        # Entry cost includes 100x multiplier
        entry_cost = filled_order.filled_price * filled_order.quantity * 100

        position = OptionsPosition(
            position_id=position_id,
            spread_type=SpreadType.SINGLE,
            legs=[leg],
            entry_time=current_time,
            entry_cost=entry_cost,
            underlying_price_at_entry=underlying_price,
            profit_target_pct=self.profit_target_pct,
            stop_loss=self.stop_loss_pct,
        )

        # Create sell limit order for profit target
        sell_order_id = f"BBLIMIT_SELL_{position_id}"
        sell_order = LimitOrder(
            order_id=sell_order_id,
            contract_symbol=filled_order.contract_symbol,
            option_type=filled_order.option_type,
            strike_price=filled_order.strike_price,
            expiration_date=filled_order.expiration_date,
            quantity=filled_order.quantity,
            limit_price=self.profit_target_price,
            direction="sell",
            status=OrderStatus.PENDING,
            created_time=current_time,
        )

        self.pending_sell_orders.append(sell_order)

        return position

    def _check_strategy_exits(
        self,
        position: OptionsPosition,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
    ) -> tuple[bool, Optional[str]]:
        """
        Check strategy-specific exit conditions.

        Exit conditions:
        1. Sell limit order filled (100% profit target)
        2. End of day (4 PM ET)
        3. Expiration day

        Note: Absolute stop loss is automatically checked by base class.

        Returns:
            (should_exit, exit_reason)
        """
        # Get current underlying price
        underlying_price = underlying_data['close'].iloc[-1] if not underlying_data.empty else None

        # Update position value
        self.update_position_value(position, options_data, underlying_price)

        # Check if sell order was filled
        filled_sell = None
        for order in self.pending_sell_orders:
            if order.status == OrderStatus.FILLED:
                filled_sell = order
                break

        if filled_sell:
            # Remove filled order
            self.pending_sell_orders = [
                o for o in self.pending_sell_orders
                if o.status == OrderStatus.PENDING
            ]
            # Override position exit value with actual fill price (not mark price)
            # This prevents P&L distortion from wide bid/ask spreads or stale market data
            position.current_value = filled_sell.filled_price * position.legs[0].quantity * 100
            position.legs[0].current_price = filled_sell.filled_price

            pnl = (filled_sell.filled_price - position.legs[0].entry_price) * position.legs[0].quantity * 100
            pnl_pct = (filled_sell.filled_price - position.legs[0].entry_price) / position.legs[0].entry_price
            return True, f"Sell limit filled at ${filled_sell.filled_price:.2f} - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        # Check sell orders for fills
        for order in self.pending_sell_orders:
            if order.status == OrderStatus.PENDING:
                self._check_sell_order_fill(order, options_data, current_time)
                if order.status == OrderStatus.FILLED:
                    # Override position exit value with actual fill price (not mark price)
                    # This prevents P&L distortion from wide bid/ask spreads or stale market data
                    position.current_value = order.filled_price * position.legs[0].quantity * 100
                    position.legs[0].current_price = order.filled_price

                    pnl = (order.filled_price - position.legs[0].entry_price) * position.legs[0].quantity * 100
                    pnl_pct = (order.filled_price - position.legs[0].entry_price) / position.legs[0].entry_price
                    # Clean up
                    self.pending_sell_orders = [
                        o for o in self.pending_sell_orders
                        if o.status == OrderStatus.PENDING
                    ]
                    return True, f"Profit target reached at ${order.filled_price:.2f} - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        # Validate position value
        if position.current_value is None or pd.isna(position.current_value):
            return False, None

        # Skip checks if no valid market data
        if not position.has_valid_market_data:
            return False, None

        # Calculate current P&L
        pnl = position.current_value - position.entry_cost
        pnl_pct = pnl / abs(position.entry_cost) if position.entry_cost != 0 else 0

        if pd.isna(pnl_pct):
            return False, None

        # Note: Stop loss check removed - now handled by base class automatically

        # Exit at end of day (4 PM ET)
        eastern = pytz.timezone('US/Eastern')
        current_time_et = current_time.astimezone(eastern)
        exit_time = time(16, 0)
        leg = position.legs[0]

        if current_time_et.time() >= exit_time:
            # Cancel pending sell orders
            for order in self.pending_sell_orders:
                order.status = OrderStatus.CANCELLED
            self.pending_sell_orders = []
            return True, f"End of day exit - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        # Force exit if past expiration
        if current_time.date() > leg.expiration_date:
            for order in self.pending_sell_orders:
                order.status = OrderStatus.CANCELLED
            self.pending_sell_orders = []
            return True, f"Past expiration - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        return False, None

    def process_filled_buy_order(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        market_analysis: Dict[str, Any],
    ) -> Optional[OptionsPosition]:
        """
        Process a filled buy order and create the position.

        This should be called by the backtest engine after analyze_market
        detects a filled buy order.

        Returns:
            OptionsPosition if order was filled, None otherwise
        """
        filled_order = market_analysis.get("filled_buy_order")
        if filled_order is None:
            return None

        underlying_price = market_analysis.get("underlying_price", 0.0)

        position = self.create_position_from_fill(
            filled_order, current_time, underlying_price
        )

        return position

    def get_strategy_name(self) -> str:
        """Return strategy name."""
        return "BollingerBandLimit"

    def get_description(self) -> str:
        """Return strategy description."""
        return (
            f"Bollinger Band ({self.bb_period}, {self.bb_std}) direction with limit orders: "
            f"target {self.otm_percent_min*100:.0f}-{self.otm_percent_max*100:.0f}% OTM, "
            f"contracts near ${self.target_contract_price:.2f}, "
            f"limit buy at ${self.limit_buy_price:.2f}, "
            f"sell at ${self.profit_target_price:.2f} (100% profit), "
            f"max {self.max_trades_daily} trades/day"
        )
