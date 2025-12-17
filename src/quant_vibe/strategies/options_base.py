"""Base classes for options trading strategies."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd


class OptionType(Enum):
    """Option type enum."""
    CALL = "CALL"
    PUT = "PUT"


class SpreadType(Enum):
    """Options spread types."""
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
    expiration_date: datetime
    quantity: int  # Positive for long, negative for short
    entry_price: float
    current_price: Optional[float] = None


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
    profit_target: float  # Percentage (e.g., 0.5 for 50%)
    stop_loss: Optional[float] = None  # Percentage
    trailing_stop: Optional[float] = None  # Percentage

    # Position tracking
    current_value: Optional[float] = None
    highest_value: Optional[float] = None
    exit_time: Optional[datetime] = None
    exit_value: Optional[float] = None
    exit_reason: Optional[str] = None

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

    def __init__(self, name: str) -> None:
        """
        Initialize options strategy.

        Args:
            name: Strategy name
        """
        self.name = name
        self.positions: List[OptionsPosition] = []
        self.active_position: Optional[OptionsPosition] = None

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

    @abstractmethod
    def should_exit(
        self,
        position: OptionsPosition,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if strategy should exit current position.

        Args:
            position: Current position
            underlying_data: OHLCV data for underlying
            options_data: Options chain data
            current_time: Current timestamp

        Returns:
            Tuple of (should_exit, exit_reason)
        """
        pass

    def update_position_value(
        self,
        position: OptionsPosition,
        options_data: pd.DataFrame
    ) -> None:
        """
        Update current value of position based on options prices.

        Args:
            position: Position to update
            options_data: Current options data
        """
        current_value = 0.0
        missing_legs = []

        for leg in position.legs:
            # Find current price for this contract
            leg_data = options_data[
                options_data['contract_symbol'] == leg.contract_symbol
            ]

            if not leg_data.empty:
                # Use mark price (mid of bid/ask)
                current_price = leg_data.iloc[0]['mark']

                # Validate mark price
                if pd.isna(current_price) or current_price < 0:
                    # Mark price invalid - try to estimate from intrinsic value
                    missing_legs.append(leg.contract_symbol)
                    # For now, use entry price as fallback
                    current_price = leg.entry_price if leg.entry_price else 0
                    if current_price <= 0:
                        continue

                leg.current_price = current_price

                # Calculate leg value: quantity * price * multiplier
                # For short positions (negative quantity), this will be negative
                leg_value = leg.quantity * current_price * 100
                current_value += leg_value
            else:
                # No data for this leg at this timestamp - this is a DATA QUALITY ISSUE
                missing_legs.append(leg.contract_symbol)

                # Try to estimate price from similar strikes
                # Get other contracts at same expiration
                same_exp = options_data[
                    (options_data['expiration_date'] == leg.expiration_date) &
                    (options_data['option_type'] == ('P' if leg.option_type == OptionType.PUT else 'C'))
                ]

                if not same_exp.empty:
                    # Find strikes above and below
                    strikes_above = same_exp[same_exp['strike_price'] > leg.strike_price].sort_values('strike_price')
                    strikes_below = same_exp[same_exp['strike_price'] < leg.strike_price].sort_values('strike_price', ascending=False)

                    # Linear interpolation if we have data on both sides
                    if not strikes_above.empty and not strikes_below.empty:
                        strike_above = strikes_above.iloc[0]
                        strike_below = strikes_below.iloc[0]

                        # Interpolate mark price
                        strike_diff = strike_above['strike_price'] - strike_below['strike_price']
                        if strike_diff > 0:
                            weight = (leg.strike_price - strike_below['strike_price']) / strike_diff
                            estimated_price = strike_below['mark'] + weight * (strike_above['mark'] - strike_below['mark'])

                            leg.current_price = estimated_price
                            leg_value = leg.quantity * estimated_price * 100
                            current_value += leg_value

                            print(f"      ⚠️  Interpolated {leg.contract_symbol}: ${estimated_price:.2f} (from ${strike_below['mark']:.2f} @ {strike_below['strike_price']} and ${strike_above['mark']:.2f} @ {strike_above['strike_price']})")
                            continue

                # Fallback: use entry price (conservative estimate)
                print(f"      ⚠️  Using entry price for {leg.contract_symbol}: ${leg.entry_price:.2f} (NO CURRENT DATA)")
                current_price = leg.entry_price if leg.entry_price else 0
                leg.current_price = current_price
                leg_value = leg.quantity * current_price * 100
                current_value += leg_value

        if missing_legs:
            print(f"   ⚠️  Missing/invalid data for legs: {', '.join(missing_legs)}")

        position.current_value = current_value

        # Validate current_value is reasonable for the spread
        # For credit spreads (entry_cost < 0), max loss is limited to spread width
        # For debit spreads (entry_cost > 0), max gain is limited to spread width
        if position.entry_cost < 0:  # Credit spread
            # Maximum risk = spread width * contracts * multiplier
            # If current_value (cost to buy back) exceeds max risk, something is wrong
            max_risk = abs(position.entry_cost) * 10  # Allow 10x for safety check
            if abs(current_value) > max_risk:
                print(f"⚠️  WARNING: Position value ${current_value:,.2f} exceeds reasonable max ${max_risk:,.2f}")
                print(f"   Entry cost: ${position.entry_cost:,.2f}, Entry time: {position.entry_time}")
                print(f"   This may indicate bad data or calculation error")

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
        return position.pnl_percent >= position.profit_target

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
            print(f"   ⚠️  No historical data available for completeness check")
            return False, {}

        # Get unique timestamps in the window
        all_timestamps = historical_data['timestamp'].unique()
        total_timestamps = len(all_timestamps)

        if total_timestamps == 0:
            print(f"   ⚠️  No timestamps found in lookback window")
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
