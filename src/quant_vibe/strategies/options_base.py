"""Base classes for options trading strategies."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta, date

import pandas as pd

from quant_vibe.logging import get_logger

logger = get_logger(__name__)


class OptionType(Enum):
    """Option type enum."""
    CALL = "CALL"
    PUT = "PUT"


class SpreadType(Enum):
    """Options spread types."""
    SINGLE = "SINGLE"  # Single-leg position (not a spread)
    VERTICAL_CALL = "VERTICAL_CALL"
    VERTICAL_PUT = "VERTICAL_PUT"
    IRON_CONDOR = "IRON_CONDOR"
    BUTTERFLY = "BUTTERFLY"
    CALENDAR = "CALENDAR"


@dataclass
class OptionLeg:
    """Represents a single option leg in a spread."""
    contract_symbol: str
    option_type: OptionType
    strike_price: float
    expiration_date: date  # Changed from datetime to date to match OptionsBar Pydantic model
    quantity: int  # Positive for long, negative for short
    entry_price: float
    current_price: Optional[float] = None

    def __post_init__(self):
        """Ensure numeric fields are converted from Decimal to float if needed."""
        # Convert strike_price from Decimal to float if necessary
        if not isinstance(self.strike_price, float):
            self.strike_price = float(self.strike_price)

        # Convert entry_price from Decimal to float if necessary
        if not isinstance(self.entry_price, float):
            self.entry_price = float(self.entry_price)

        # Convert current_price from Decimal to float if necessary
        if self.current_price is not None and not isinstance(self.current_price, float):
            self.current_price = float(self.current_price)


@dataclass
class OptionsPosition:
    """Represents an options spread position."""
    position_id: str
    spread_type: SpreadType
    legs: List[OptionLeg]
    entry_time: datetime
    entry_cost: float  # Net debit/credit
    underlying_price_at_entry: float

    # Risk management
    profit_target_pct: float  # Percentage (e.g., 0.5 for 50%)
    stop_loss: Optional[float] = None  # Percentage
    trailing_stop: Optional[float] = None  # Percentage

    # Position tracking
    current_value: Optional[float] = None
    highest_value: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_value: Optional[float] = None
    exit_reason: Optional[str] = None
    has_valid_market_data: bool = True  # Track if current_value is from actual market data

    def __post_init__(self):
        """Ensure numeric fields are converted from Decimal to float if needed."""
        # Convert entry_cost from Decimal to float if necessary
        if not isinstance(self.entry_cost, float):
            self.entry_cost = float(self.entry_cost)

        # Convert underlying_price_at_entry from Decimal to float if necessary
        if not isinstance(self.underlying_price_at_entry, float):
            self.underlying_price_at_entry = float(self.underlying_price_at_entry)

        # Convert current_value from Decimal to float if necessary
        if self.current_value is not None and not isinstance(self.current_value, float):
            self.current_value = float(self.current_value)

        # Convert exit_value from Decimal to float if necessary
        if self.exit_value is not None and not isinstance(self.exit_value, float):
            self.exit_value = float(self.exit_value)

    @property
    def pnl(self) -> Optional[float]:
        """
        Calculate current P&L.

        For debit spreads (entry_cost > 0): profit when current_value > entry_cost
        For credit spreads (entry_cost < 0): profit when current_value < abs(entry_cost)

        The formula current_value - entry_cost works for both:
        - Debit: current_value - (+entry_cost) = profit when current_value increases
        - Credit: current_value - (-entry_cost) = profit when current_value decreases
        """
        if self.current_value is None:
            return None
        return self.current_value - self.entry_cost

    @property
    def pnl_percent(self) -> Optional[float]:
        """
        Calculate current P&L percentage.

        Percentage is always based on absolute value of entry cost (capital at risk).
        """
        if self.current_value is None or self.entry_cost == 0:
            return None
        return (self.current_value - self.entry_cost) / abs(self.entry_cost)

    @property
    def is_closed(self) -> bool:
        """Check if position is closed."""
        return self.exit_time is not None


class OptionsStrategy(ABC):
    """Base class for options trading strategies."""

    def __init__(
        self,
        name: str,
        observation_period: Optional[int] = None,
        max_trades_daily: int = 1,

        ## start: COLLECTED FROM CURRENT STRATEGIES
        min_volume: int = 0,
        max_dte: int = 2,
        min_dte: int = 0,
        num_spreads: int = 1,
        otm_percent_max: float = 0.05,
        otm_percent_min: float = -0.05,
        profit_target_pct: float = 0.5,
        profit_target_min: float = 1.0,
        profit_target_max: float = 5.0,
        stop_loss_pct: float = 0.25,  # Default 25% stop loss for protection
        trailing_stop_pct: Optional[float] = None,
        quantity: int = 10,
        ## end: COLLECTED FROM CURRENT STRATEGIES


        **kwargs  # Accept any additional parameters for child classes
    ) -> None:
        """
        Initialize options strategy.

        Args:
            name: Strategy name
            max_trades_daily: Maximum number of trades allowed per day (default: 1)
            observation_period: Observation period in minutes for market analysis (optional, strategy-specific)
            **kwargs: Additional parameters accepted by child classes (silently ignored)
        """
        self.name = name
        self.max_trades_daily = max_trades_daily
        self.observation_period = observation_period
        self.trades_today = 0  # Track number of trades entered today
        self.positions: List[OptionsPosition] = []
        self.active_position: Optional[OptionsPosition] = None

        # Store common strategy parameters
        self.min_volume = min_volume
        self.max_dte = max_dte
        self.min_dte = min_dte
        self.num_spreads = num_spreads
        self.otm_percent_max = otm_percent_max
        self.otm_percent_min = otm_percent_min
        self.profit_target_pct = profit_target_pct
        self.profit_target_min = profit_target_min
        self.profit_target_max = profit_target_max
        self.stop_loss_pct = stop_loss_pct
        self.trailing_stop_pct = trailing_stop_pct
        self.quantity = quantity

    def _filter_by_dte(
        self,
        options_data: pd.DataFrame,
        current_time: datetime,
        min_dte: int,
        max_dte: int
    ) -> pd.DataFrame:
        """
        Filter options by days to expiration (DTE).

        This method handles the date type conversion to ensure compatibility with
        the DataFrame's expiration_date column, which contains datetime.date objects
        from the Pydantic model.

        Args:
            options_data: Options DataFrame with 'expiration_date' column
            current_time: Current timestamp (UTC-aware)
            min_dte: Minimum days to expiration
            max_dte: Maximum days to expiration

        Returns:
            Filtered DataFrame with options in the DTE range
        """
        from datetime import timedelta

        # Calculate target date range
        target_date = current_time + timedelta(days=min_dte)
        max_date = current_time + timedelta(days=max_dte)

        # Convert to date objects for comparison (expiration_date column contains date objects)
        # This prevents "Cannot compare Timestamp with datetime.date" pandas errors
        target_date = target_date.date()
        max_date = max_date.date()

        # Filter by DTE range
        return options_data[
            (options_data["expiration_date"] >= target_date) &
            (options_data["expiration_date"] <= max_date)
        ].copy()

    def _filter_by_liquidity(
        self,
        options_data: pd.DataFrame,
        min_volume: int,
        max_bid_ask_spread_pct: Optional[float] = None
    ) -> pd.DataFrame:
        """
        Filter options by liquidity criteria.

        This method applies volume and bid-ask spread filters to ensure adequate
        liquidity for trading. It safely handles None/zero mark prices that would
        cause division errors when calculating bid-ask spread percentages.

        Args:
            options_data: Options DataFrame with volume, bid, ask, and mark columns
            min_volume: Minimum volume required per contract
            max_bid_ask_spread_pct: Maximum bid-ask spread as percentage of mark price
                                   (e.g., 10.0 for 10%). If None, no spread filter is applied.

        Returns:
            Filtered DataFrame with liquid options only
        """
        # Filter by minimum volume
        liquid_options = options_data[options_data['volume'] >= min_volume].copy()

        if liquid_options.empty:
            return liquid_options

        # Apply bid-ask spread filter if requested and data is available
        if (max_bid_ask_spread_pct is not None and
            'bid' in liquid_options.columns and
            'ask' in liquid_options.columns and
            'mark' in liquid_options.columns):

            # First filter out rows with invalid mark prices (None or zero)
            # This prevents TypeError when dividing by None or division by zero
            liquid_options = liquid_options[
                (liquid_options['mark'].notna()) & (liquid_options['mark'] > 0)
            ].copy()

            if liquid_options.empty:
                return liquid_options

            # Calculate spread percentage safely
            # Convert to float to handle decimal.Decimal types from database
            liquid_options['bid_ask_spread_pct'] = (
                (liquid_options['ask'].astype(float) - liquid_options['bid'].astype(float)) /
                liquid_options['mark'].astype(float) * 100
            )

            # Filter out wide spreads
            liquid_options = liquid_options[
                liquid_options['bid_ask_spread_pct'] <= max_bid_ask_spread_pct
            ].copy()

        return liquid_options

    @abstractmethod
    def analyze_market(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Dict:
        """
        Analyze market conditions.

        Args:
            underlying_data: OHLCV data for underlying
            options_data: Options chain data
            current_time: Current timestamp

        Returns:
            Dictionary with market analysis (direction, momentum, etc.)
        """
        pass

    @abstractmethod
    def should_enter(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        market_analysis: Dict
    ) -> bool:
        """
        Determine if strategy should enter a position.

        Args:
            underlying_data: OHLCV data for underlying
            options_data: Options chain data
            current_time: Current timestamp
            market_analysis: Result from analyze_market()

        Returns:
            True if should enter position
        """
        pass

    @abstractmethod
    def construct_spread(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        market_analysis: Dict,
        full_options_data: Optional[pd.DataFrame] = None
    ) -> Optional[OptionsPosition]:
        """
        Construct the options spread to enter.

        Args:
            underlying_data: OHLCV data for underlying
            options_data: Options chain data for current timestamp
            current_time: Current timestamp
            market_analysis: Result from analyze_market()
            full_options_data: Complete options dataset (for data completeness checks)

        Returns:
            OptionsPosition object or None
        """
        pass

    def should_exit(
        self,
        position: OptionsPosition,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if strategy should exit current position.

        This is the main exit evaluation method that enforces mandatory risk checks
        before delegating to strategy-specific logic.

        MANDATORY CHECKS (always enforced):
        1. Absolute stop loss (default 25% drawdown)

        Args:
            position: Current position
            underlying_data: OHLCV data for underlying
            options_data: Options chain data
            current_time: Current timestamp

        Returns:
            Tuple of (should_exit, exit_reason)
        """
        # MANDATORY: Check absolute stop loss first (protection against catastrophic losses)
        if self.check_stop_loss(position):
            return True, f"Stop loss hit ({position.stop_loss*100:.0f}%)"

        # Delegate to strategy-specific exit logic
        return self._check_strategy_exits(position, underlying_data, options_data, current_time)

    @abstractmethod
    def _check_strategy_exits(
        self,
        position: OptionsPosition,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Check strategy-specific exit conditions.

        This is called AFTER mandatory stop loss checks. Implement your strategy's
        custom exit logic here (profit targets, trailing stops, time-based exits, etc.).

        Note: You do NOT need to check absolute stop loss here - it's automatically
        enforced by the base class should_exit() method.

        Args:
            position: Current position
            underlying_data: OHLCV data for underlying
            options_data: Options chain data
            current_time: Current timestamp

        Returns:
            Tuple of (should_exit, exit_reason)
        """
        pass

    def _calculate_intrinsic_value(
        self,
        leg: OptionLeg,
        underlying_price: float
    ) -> float:
        """
        Calculate intrinsic value of an option.

        Args:
            leg: Option leg to value
            underlying_price: Current underlying asset price

        Returns:
            Intrinsic value (max of 0 or in-the-money amount)
        """
        if leg.option_type == OptionType.CALL:
            # Call: max(0, underlying - strike)
            intrinsic = max(0, underlying_price - leg.strike_price)
        else:  # PUT
            # Put: max(0, strike - underlying)
            intrinsic = max(0, leg.strike_price - underlying_price)

        return intrinsic

    def update_position_value(
        self,
        position: OptionsPosition,
        options_data: pd.DataFrame,
        underlying_price: Optional[float] = None
    ) -> None:
        """
        Update current value of position based on options prices.

        Args:
            position: Position to update
            options_data: Current options data
            underlying_price: Current underlying asset price (for intrinsic value calculation)
        """
        current_value = 0.0
        missing_legs = []
        used_fallback = False  # Track if we used fallback pricing

        for leg in position.legs:
            # Find current price for this contract
            leg_data = options_data[
                options_data['contract_symbol'] == leg.contract_symbol
            ]

            if not leg_data.empty:
                # Use mark price (mid of bid/ask)
                mark_value = leg_data.iloc[0]['mark']

                # Validate mark price (check for None/NaN before converting)
                if mark_value is None or pd.isna(mark_value):
                    current_price = None
                else:
                    current_price = float(mark_value)

                if current_price is None or current_price < 0:
                    # Mark price invalid - try to calculate intrinsic value
                    missing_legs.append(leg.contract_symbol)
                    used_fallback = True  # Using fallback pricing
                    if underlying_price is not None:
                        # Use intrinsic value (conservative estimate)
                        current_price = self._calculate_intrinsic_value(leg, underlying_price)
                        logger.debug(f"      ⚠️  Using intrinsic value for {leg.contract_symbol}: ${current_price:.2f} (invalid mark price)")
                    else:
                        # No underlying price - use entry price as last resort
                        current_price = leg.entry_price if leg.entry_price else 0
                        if current_price <= 0:
                            continue

                leg.current_price = current_price

                # Calculate exit value (cash flow from closing the position)
                # This must match position_manager's sign convention:
                # - Long positions (qty > 0): selling = POSITIVE (credit received)
                # - Short positions (qty < 0): buying = NEGATIVE (debit paid)
                if leg.quantity > 0:
                    # Long position: would sell at current price
                    leg_value = current_price * abs(leg.quantity) * 100  # Positive
                else:
                    # Short position: would buy at current price
                    leg_value = -(current_price * abs(leg.quantity) * 100)  # Negative
                current_value += leg_value
            else:
                # No data for this leg at this timestamp - this is a DATA QUALITY ISSUE
                missing_legs.append(leg.contract_symbol)
                used_fallback = True  # Using fallback pricing

                # Try to estimate price from similar strikes
                # Get other contracts at same expiration
                same_exp = options_data[
                    (options_data['expiration_date'] == leg.expiration_date) &
                    (options_data['contract_type'] == ('put' if leg.option_type == OptionType.PUT else 'call'))
                ]

                if not same_exp.empty:
                    # Find strikes above and below
                    strikes_above = same_exp[same_exp['strike_price'] > leg.strike_price].sort_values('strike_price')
                    strikes_below = same_exp[same_exp['strike_price'] < leg.strike_price].sort_values('strike_price', ascending=False)

                    # Linear interpolation if we have data on both sides
                    if not strikes_above.empty and not strikes_below.empty:
                        strike_above = strikes_above.iloc[0]
                        strike_below = strikes_below.iloc[0]

                        # Check if mark prices are valid before interpolating
                        mark_above = strike_above['mark']
                        mark_below = strike_below['mark']

                        if (mark_above is not None and mark_below is not None and
                            not pd.isna(mark_above) and not pd.isna(mark_below)):
                            # Interpolate mark price (convert Decimals to floats)
                            strike_diff = float(strike_above['strike_price']) - float(strike_below['strike_price'])
                            if strike_diff > 0:
                                weight = (leg.strike_price - float(strike_below['strike_price'])) / strike_diff
                                estimated_price = float(mark_below) + weight * (float(mark_above) - float(mark_below))

                                leg.current_price = estimated_price

                                # Calculate exit value with correct sign convention
                                if leg.quantity > 0:
                                    leg_value = estimated_price * abs(leg.quantity) * 100  # Long: positive
                                else:
                                    leg_value = -(estimated_price * abs(leg.quantity) * 100)  # Short: negative
                                current_value += leg_value

                                logger.debug(f"      ⚠️  Interpolated {leg.contract_symbol}: ${estimated_price:.2f} (from ${mark_below:.2f} @ {strike_below['strike_price']} and ${mark_above:.2f} @ {strike_above['strike_price']})")
                                continue

                # Fallback: use intrinsic value if we have underlying price, else entry price
                if underlying_price is not None:
                    # Calculate intrinsic value (conservative, no time value)
                    current_price = self._calculate_intrinsic_value(leg, underlying_price)
                    logger.debug(f"      ⚠️  Using intrinsic value for {leg.contract_symbol}: ${current_price:.2f} (NO CURRENT DATA, underlying=${underlying_price:.2f})")
                else:
                    # Last resort: use entry price
                    logger.debug(f"      ⚠️  Using entry price for {leg.contract_symbol}: ${leg.entry_price:.2f} (NO CURRENT DATA)")
                    current_price = leg.entry_price if leg.entry_price else 0

                leg.current_price = current_price

                # Calculate exit value with correct sign convention
                if leg.quantity > 0:
                    leg_value = current_price * abs(leg.quantity) * 100  # Long: positive
                else:
                    leg_value = -(current_price * abs(leg.quantity) * 100)  # Short: negative
                current_value += leg_value

        if missing_legs:
            logger.debug(f"   ⚠️  Missing/invalid data for legs: {', '.join(missing_legs)}")

        # Ensure current_value is float (in case of Decimal arithmetic)
        position.current_value = float(current_value) if current_value is not None else None
        position.has_valid_market_data = not used_fallback  # Mark if using real market data

        # Validate current_value is reasonable for the spread
        # For credit spreads (entry_cost < 0), max loss is limited to spread width
        # For debit spreads (entry_cost > 0), max gain is limited to spread width
        if position.entry_cost < 0:  # Credit spread
            # Maximum risk = spread width * contracts * multiplier
            # If current_value (cost to buy back) exceeds max risk, something is wrong
            max_risk = abs(position.entry_cost) * 10  # Allow 10x for safety check
            if abs(current_value) > max_risk:
                logger.debug(f"⚠️  WARNING: Position value ${current_value:,.2f} exceeds reasonable max ${max_risk:,.2f}")
                logger.debug(f"   Entry cost: ${position.entry_cost:,.2f}, Entry time: {position.entry_time}")
                logger.debug("   This may indicate bad data or calculation error")

        # Track highest value for trailing stop
        if position.highest_value is None or current_value > position.highest_value:
            position.highest_value = current_value

    def check_profit_target(self, position: OptionsPosition) -> bool:
        """
        Check if profit target is reached.

        Args:
            position: Position to check

        Returns:
            True if profit target reached
        """
        if position.pnl_percent is None:
            return False
        return position.pnl_percent >= position.profit_target_pct

    def check_stop_loss(self, position: OptionsPosition) -> bool:
        """
        Check if stop loss is hit.

        Args:
            position: Position to check

        Returns:
            True if stop loss hit
        """
        if position.stop_loss is None or position.pnl_percent is None:
            return False
        return position.pnl_percent <= -position.stop_loss

    def check_trailing_stop(self, position: OptionsPosition) -> bool:
        """
        Check if trailing stop is hit.

        Args:
            position: Position to check

        Returns:
            True if trailing stop hit
        """
        if (position.trailing_stop is None or
            position.current_value is None or
            position.highest_value is None or
            position.highest_value <= 0):  # Avoid division by zero
            return False

        # Calculate drawdown from highest value
        drawdown = (position.highest_value - position.current_value) / position.highest_value
        return drawdown >= position.trailing_stop

    def can_enter_new_position(self) -> bool:
        """
        Check if we can enter a new position today.

        Returns:
            True if trades_today < max_trades_daily
        """
        return self.trades_today < self.max_trades_daily

    def increment_daily_trade_count(self) -> None:
        """Increment the daily trade counter after entering a position."""
        self.trades_today += 1

    def reset_daily_state(self) -> None:
        """
        Reset state for a new trading day.

        This method is called automatically by the backtesting engine when
        the date changes. Subclasses should override this to reset additional
        strategy-specific state.
        """
        self.trades_today = 0

    def validate_data_completeness(
        self,
        contract_symbols: List[str],
        options_data: pd.DataFrame,
        current_time: datetime,
        lookback_minutes: int = 60,
        min_completeness_pct: float = 95.0
    ) -> Tuple[bool, Dict[str, float]]:
        """
        Validate that contracts have sufficient data coverage.

        This checks historical data availability to ensure we won't encounter
        missing data issues during the position lifetime.

        Args:
            contract_symbols: List of contract symbols to validate
            options_data: Full options dataset
            current_time: Current timestamp
            lookback_minutes: How many minutes back to check (default: 60)
            min_completeness_pct: Minimum required data completeness % (default: 95)

        Returns:
            Tuple of (is_valid, completeness_dict)
            - is_valid: True if all contracts meet minimum completeness
            - completeness_dict: Dict mapping contract symbol to completeness %
        """
        # Get historical window
        start_time = current_time - timedelta(minutes=lookback_minutes)

        # Get all timestamps in the window
        historical_data = options_data[
            (options_data['timestamp'] >= start_time) &
            (options_data['timestamp'] <= current_time)
        ]

        if historical_data.empty:
            logger.debug("   ⚠️  No historical data available for completeness check")
            return False, {}

        # Get unique timestamps in the window
        all_timestamps = historical_data['timestamp'].unique()
        total_timestamps = len(all_timestamps)

        if total_timestamps == 0:
            logger.debug("   ⚠️  No timestamps found in lookback window")
            return False, {}

        # Check completeness for each contract
        completeness = {}
        for symbol in contract_symbols:
            contract_data = historical_data[
                historical_data['contract_symbol'] == symbol
            ]
            timestamps_with_data = contract_data['timestamp'].nunique()
            completeness_pct = (timestamps_with_data / total_timestamps) * 100
            completeness[symbol] = completeness_pct

        # Check if all contracts meet minimum
        all_valid = all(pct >= min_completeness_pct for pct in completeness.values())

        return all_valid, completeness

    def close_position(
        self,
        position: OptionsPosition,
        current_time: datetime,
        exit_reason: str,
        underlying_price: Optional[float] = None
    ) -> None:
        """
        Close a position.

        Args:
            position: Position to close
            current_time: Exit timestamp
            exit_reason: Reason for exit
            underlying_price: Optional underlying price at exit
        """
        position.exit_time = current_time

        # Ensure we have a valid exit value
        # If current_value is None (missing market data), use entry_cost as fallback
        if position.current_value is None:
            position.exit_value = position.entry_cost
        else:
            position.exit_value = position.current_value

        position.exit_reason = exit_reason

        # Store underlying price at exit
        if underlying_price is not None:
            position.underlying_price_at_exit = underlying_price

        # Store exit prices for each leg
        for leg in position.legs:
            if leg.current_price is not None:
                leg.exit_price = leg.current_price

        # Track peak value achieved
        if position.highest_value is not None:
            position.peak_value = position.highest_value

        if position == self.active_position:
            self.active_position = None
