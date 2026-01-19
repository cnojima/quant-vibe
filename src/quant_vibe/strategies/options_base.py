"""Base classes for options trading strategies."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from quant_vibe.utils.pricing_utils import get_mark_price_from_row
import pandas as pd

from quant_vibe.logging import get_logger
from quant_vibe.utils.pnl_utils import PnLCalculator

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
    option_ticker: str
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

        # Convert expiration_date to date if it's a Timestamp or datetime
        if hasattr(self.expiration_date, 'date'):
            # It's a pandas Timestamp or datetime object
            self.expiration_date = self.expiration_date.date()
        elif hasattr(self.expiration_date, 'to_pydatetime'):
            # It's a pandas Timestamp with to_pydatetime method
            self.expiration_date = self.expiration_date.to_pydatetime().date()

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
        Calculate current P&L using centralized calculator.

        Uses unrealized PnL for open positions or realized PnL for closed positions.
        """
        if self.is_closed and self.exit_value is not None:
            # Closed position - use realized PnL
            result = PnLCalculator.calculate_realized_pnl(
                self.entry_cost,
                self.exit_value
            )
        elif self.current_value is not None:
            # Open position - use unrealized PnL
            result = PnLCalculator.calculate_unrealized_pnl(
                self.entry_cost,
                self.current_value
            )
        else:
            return None

        return result.pnl

    @property
    def pnl_percent(self) -> Optional[float]:
        """
        Calculate current P&L percentage using centralized calculator.

        Percentage is always based on absolute value of entry cost (capital at risk).
        """
        if self.is_closed and self.exit_value is not None:
            # Closed position - use realized PnL
            result = PnLCalculator.calculate_realized_pnl(
                self.entry_cost,
                self.exit_value
            )
        elif self.current_value is not None:
            # Open position - use unrealized PnL
            result = PnLCalculator.calculate_unrealized_pnl(
                self.entry_cost,
                self.current_value
            )
        else:
            return None

        return result.pnl_pct

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

        # Convert to pandas datetime for proper comparison
        # Use pd.to_datetime to ensure compatibility with datetime64[ns] columns
        import pandas as pd
        target_date_dt = pd.to_datetime(target_date).tz_localize(None)
        max_date_dt = pd.to_datetime(max_date).tz_localize(None)

        # Filter by DTE range
        return options_data[
            (options_data["expiration_date"] >= target_date_dt) &
            (options_data["expiration_date"] <= max_date_dt)
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
            'ask' in liquid_options.columns):

            # Calculate mark prices using pricing utilities for each row
            liquid_options = liquid_options.copy()
            liquid_options['mark_calc'] = liquid_options.apply(
                lambda row: get_mark_price_from_row(row), axis=1
            )

            # Filter out rows with invalid mark prices (zero)
            liquid_options = liquid_options[
                liquid_options['mark_calc'] > 0
            ].copy()

            if liquid_options.empty:
                return liquid_options

            # Calculate spread percentage safely
            # Convert to float to handle decimal.Decimal types from database
            liquid_options['bid_ask_spread_pct'] = (
                (liquid_options['ask'].astype(float) - liquid_options['bid'].astype(float)) /
                liquid_options['mark_calc'].astype(float) * 100
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
                options_data['option_ticker'] == leg.option_ticker
            ]

            if not leg_data.empty:
                # Calculate mark price from bid/ask, with fallback to pre-calculated mark
                from quant_vibe.utils.pricing_utils import get_mark_price_from_row
                current_price = get_mark_price_from_row(
                    leg_data.iloc[0],
                    bid_col='bid',
                    ask_col='ask',
                    mark_col='mark',
                    fallback_col='last'  # Use last price as additional fallback
                )

                # Additional validation: check if mark price is reasonable given underlying
                if current_price > 0 and underlying_price is not None:
                    intrinsic = self._calculate_intrinsic_value(leg, underlying_price)

                    # Check days to expiration if we have the current time
                    days_to_expiry = None
                    if hasattr(position, 'entry_time') and position.entry_time:
                        from datetime import datetime
                        if isinstance(position.entry_time, datetime):
                            current_date = position.entry_time.date()
                            days_to_expiry = (leg.expiration_date - current_date).days

                    # For OTM options, mark should not be much higher than a reasonable time value
                    # Time value typically decreases as options go further OTM
                    if intrinsic == 0:  # Out-of-the-money
                        # Calculate how far OTM
                        if leg.option_type == OptionType.PUT:
                            otm_amount = underlying_price - leg.strike_price
                        else:  # CALL
                            otm_amount = leg.strike_price - underlying_price

                        # Check for near-expiry options - but be LESS aggressive for 1 DTE
                        if days_to_expiry == 0:
                            # Options expiring TODAY should have minimal time value if OTM
                            if otm_amount > 5:  # More than 5 points OTM on expiry day
                                # Use aggressive caps for 0 DTE
                                if otm_amount > 15:
                                    max_reasonable_value = 0.05  # Deep OTM on expiry day
                                elif otm_amount > 10:
                                    max_reasonable_value = 0.20  # Moderately OTM
                                else:
                                    max_reasonable_value = 0.50  # Slightly OTM

                                if current_price > max_reasonable_value:
                                    logger.debug(f"      ⚠️  0 DTE OTM option may be overpriced: {leg.option_ticker} @ ${current_price:.2f} "
                                               f"(expires TODAY, OTM by ${otm_amount:.2f})")
                                    current_price = max_reasonable_value
                                    used_fallback = True
                                    logger.debug(f"      → Capped at: ${current_price:.2f}")

                        elif days_to_expiry == 1:
                            # Options expiring TOMORROW - should still have significant time value
                            # Only cap if price is unreasonably high
                            if otm_amount > 10 and current_price > otm_amount * 0.5:
                                # If more than 10 points OTM, shouldn't be worth more than 50% of OTM distance
                                max_reasonable_value = otm_amount * 0.5
                                logger.debug(f"      ⚠️  1 DTE option seems overpriced: {leg.option_ticker} @ ${current_price:.2f} "
                                           f"(expires tomorrow, OTM by ${otm_amount:.2f})")
                                current_price = max_reasonable_value
                                used_fallback = True
                                logger.debug(f"      → Capped at: ${current_price:.2f}")

                        # Standard check for all OTM options
                        elif otm_amount > 10:
                            # OTM options > 10 points out shouldn't have mark > 10% of the OTM distance
                            max_reasonable_value = otm_amount * 0.1  # 10% of OTM distance
                            if current_price > max_reasonable_value:
                                logger.debug(f"      ⚠️  Suspicious mark price for {leg.option_ticker}: ${current_price:.2f} "
                                           f"(OTM by ${otm_amount:.2f}, max reasonable: ${max_reasonable_value:.2f})")
                                # Use intrinsic value (0 for OTM) plus small time value
                                current_price = intrinsic + min(0.5, max_reasonable_value * 0.1)
                                used_fallback = True
                                logger.debug(f"      → Using adjusted price: ${current_price:.2f}")

                    # For ITM options, mark should be at least intrinsic value
                    elif current_price < intrinsic:
                        logger.debug(f"      ⚠️  Mark price ${current_price:.2f} below intrinsic ${intrinsic:.2f} for {leg.option_ticker}")
                        current_price = intrinsic  # Use intrinsic as minimum
                        used_fallback = True

                if current_price is None or current_price < 0:
                    # Mark price invalid - try to calculate intrinsic value
                    missing_legs.append(leg.option_ticker)
                    used_fallback = True  # Using fallback pricing
                    if underlying_price is not None:
                        # Use intrinsic value (conservative estimate)
                        current_price = self._calculate_intrinsic_value(leg, underlying_price)
                        logger.debug(f"      ⚠️  Using intrinsic value for {leg.option_ticker}: ${current_price:.2f} (invalid mark price)")
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
                missing_legs.append(leg.option_ticker)
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

                        # Get mark prices using pricing utilities
                        mark_above = get_mark_price_from_row(strike_above)
                        mark_below = get_mark_price_from_row(strike_below)

                        if mark_above > 0 and mark_below > 0:
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

                                logger.debug(f"      ⚠️  Interpolated {leg.option_ticker}: ${estimated_price:.2f} (from ${mark_below:.2f} @ {strike_below['strike_price']} and ${mark_above:.2f} @ {strike_above['strike_price']})")
                                continue

                # Fallback: use intrinsic value if we have underlying price, else entry price
                if underlying_price is not None:
                    # Calculate intrinsic value (conservative, no time value)
                    current_price = self._calculate_intrinsic_value(leg, underlying_price)
                    logger.debug(f"      ⚠️  Using intrinsic value for {leg.option_ticker}: ${current_price:.2f} (NO CURRENT DATA, underlying=${underlying_price:.2f})")
                else:
                    # Last resort: use entry price
                    logger.debug(f"      ⚠️  Using entry price for {leg.option_ticker}: ${leg.entry_price:.2f} (NO CURRENT DATA)")
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

        # Additional sanity check for vertical spreads
        # If one leg is near worthless, the other shouldn't have much value either
        if position.spread_type in [SpreadType.VERTICAL_PUT, SpreadType.VERTICAL_CALL] and len(position.legs) == 2:
            leg_prices = [leg.current_price for leg in position.legs if leg.current_price is not None]
            if len(leg_prices) == 2:
                # If one option is < $0.10, the other shouldn't be > $1.00 for same expiry
                min_price = min(leg_prices)
                max_price = max(leg_prices)
                if min_price < 0.10 and max_price > 1.00:
                    logger.debug(f"⚠️  WARNING: Inconsistent spread prices: ${min_price:.2f} vs ${max_price:.2f}")
                    logger.debug(f"   Capping higher price to $0.50 for consistency")
                    for leg in position.legs:
                        if leg.current_price is not None and leg.current_price > 1.00:
                            leg.current_price = 0.50
                    # Recalculate current_value
                    current_value = 0.0
                    for leg in position.legs:
                        if leg.quantity > 0:
                            current_value += leg.current_price * abs(leg.quantity) * 100
                        else:
                            current_value -= leg.current_price * abs(leg.quantity) * 100
                    used_fallback = True

        # Ensure current_value is float (in case of Decimal arithmetic)
        position.current_value = float(current_value) if current_value is not None else None
        position.has_valid_market_data = not used_fallback  # Mark if using real market data

        # Validate current_value is reasonable for the spread
        # For vertical spreads, calculate the maximum theoretical values
        if position.spread_type in [SpreadType.VERTICAL_PUT, SpreadType.VERTICAL_CALL]:
            # Find the spread width (difference between strikes)
            strikes = [leg.strike_price for leg in position.legs]
            if len(strikes) == 2:
                spread_width = abs(strikes[0] - strikes[1])
                max_spread_value = spread_width * abs(position.legs[0].quantity) * 100

                # For credit spreads (entry_cost < 0)
                if position.entry_cost < 0:
                    # Max profit = credit received (when spread expires worthless)
                    max_profit = abs(position.entry_cost)
                    # Max loss = spread width - credit received
                    max_loss = max_spread_value - abs(position.entry_cost)

                    # Current PnL
                    current_pnl = current_value - position.entry_cost

                    # For credit spreads, current_value should NEVER be positive
                    # Positive value would mean we receive money when closing, which would exceed max profit
                    if current_value > 0:
                        logger.debug(f"⚠️  WARNING: Credit spread has positive exit value ${current_value:.2f}")
                        logger.debug(f"   This would create profit > initial credit. Setting to 0.")
                        current_value = 0
                        position.current_value = 0

                    # Check if PnL exceeds theoretical maximum
                    current_pnl = current_value - position.entry_cost
                    if current_pnl > max_profit * 1.05:  # Allow 5% buffer for pricing anomalies
                        logger.debug(f"⚠️  WARNING: Credit spread PnL ${current_pnl:.2f} exceeds max profit ${max_profit:.2f}")
                        logger.debug(f"   Entry: ${position.entry_cost:.2f}, Current: ${current_value:.2f}")
                        logger.debug(f"   Spread width: ${spread_width:.2f}, Max value: ${max_spread_value:.2f}")

                        # Cap the current value to enforce maximum profit
                        # For credit spreads, max profit occurs when current_value = 0 (spread expires worthless)
                        # We'll allow keeping 99% of the credit as max profit
                        position.current_value = -abs(position.entry_cost) * 0.01  # Tiny cost to close
                        logger.debug(f"   → Capped current value at: ${position.current_value:.2f}")

                # For debit spreads (entry_cost > 0)
                else:
                    # Max profit = spread width - debit paid
                    max_profit = max_spread_value - position.entry_cost
                    # Max loss = debit paid
                    max_loss = position.entry_cost

                    # Current PnL
                    current_pnl = current_value - position.entry_cost

                    # Check if PnL exceeds theoretical maximum
                    if current_pnl > max_profit * 1.1:  # Allow 10% buffer
                        logger.debug(f"⚠️  WARNING: Debit spread PnL ${current_pnl:.2f} exceeds max profit ${max_profit:.2f}")
                        logger.debug(f"   Entry: ${position.entry_cost:.2f}, Current: ${current_value:.2f}")

                        # Cap the current value to enforce maximum profit
                        position.current_value = position.entry_cost + max_profit
                        logger.debug(f"   → Capped current value at: ${position.current_value:.2f}")

        # Track highest value for trailing stop (use the potentially capped value)
        effective_value = position.current_value if position.current_value is not None else current_value
        if position.highest_value is None or effective_value > position.highest_value:
            position.highest_value = effective_value

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
        option_tickers: List[str],
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
            option_tickers: List of contract symbols to validate
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
        for symbol in option_tickers:
            contract_data = historical_data[
                historical_data['option_ticker'] == symbol
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
