"""Hail Mary Strategy - Buy OTM calls before close, hold overnight with trailing stop."""

from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
import pandas as pd

from .options_base import (
    OptionsStrategy,
    OptionsPosition,
    OptionLeg,
    OptionType,
    SpreadType
)
from quant_vibe.utils import generate_position_id


class HailMaryStrategy(OptionsStrategy):
    """
    Hail Mary Strategy - Speculative overnight call buying.

    Strategy Logic:
    1. Buy 10 CALL contracts in final 15 minutes of trading (3:45-4:00 PM ET)
    2. Target strike: 5-10% above current underlying price
    3. Expiration: Next trading day (1 DTE)
    4. Hold overnight
    5. Set trailing stop at market open with 5% limit

    Entry Criteria:
    - During final 15 minutes of trading day (3:45-4:00 PM ET)
    - Only enter once per day (first signal in window)
    - Sufficient options liquidity
    - Timeframe-agnostic: works with 1min, 5min, 15min, 1hr bars

    Exit Criteria:
    - Trailing stop triggered (5% from peak)
    - End of day (4:00 PM ET)
    - Expiration approaching
    """

    def __init__(
        self,
        otm_percent_min: float = -0.05,  # 5% OTM minimum
        otm_percent_max: float = 0.05,  # 10% OTM maximum
        entry_time_before_close: int = 15,  # minutes before close (3:45 PM ET)
        num_contracts: int = 10,  # number of contracts to buy
        trailing_stop_pct: float = 0.05,  # 5% trailing stop
        min_volume: int = 50,  # minimum volume per contract
        max_bid_ask_spread_pct: float = 15.0,  # maximum bid/ask spread percentage
        max_trades_daily: int = 3,  # maximum trades per day
        **kwargs,
    ) -> None:
        """
        Initialize Hail Mary Strategy.

        Args:
            otm_percent_min: Minimum percentage OTM for strike selection (default: 0.05 = 5%)
            otm_percent_max: Maximum percentage OTM for strike selection (default: 0.10 = 10%)
            entry_time_before_close: Minutes before close to enter position (default: 15)
            num_contracts: Number of contracts to buy (default: 10)
            trailing_stop_pct: Trailing stop percentage (default: 0.05 = 5%)
            min_volume: Minimum volume per contract for liquidity filter (default: 50)
            max_bid_ask_spread_pct: Maximum bid/ask spread percentage (default: 15%)
            max_trades_daily: Maximum trades allowed per day (default: 1)
        """
        super().__init__(
            name="HailMary",
            max_trades_daily=max_trades_daily,
            quantity=num_contracts,
            otm_percent_min=otm_percent_min,
            otm_percent_max=otm_percent_max,
            trailing_stop_pct=trailing_stop_pct,
            min_volume=min_volume,
            **kwargs
        )

        # Strategy-specific parameters (not in base class)
        self.otm_percent_min = otm_percent_min
        self.otm_percent_max = otm_percent_max
        self.num_contracts = num_contracts
        self.entry_time_before_close = entry_time_before_close
        self.max_bid_ask_spread_pct = max_bid_ask_spread_pct

        # State tracking
        self.current_day: Optional[datetime] = None
        self.market_close_time: Optional[datetime] = None
        self.entry_window_start: Optional[datetime] = None
        self.entry_window_end: Optional[datetime] = None
        self.entered_today: bool = False

    def reset_daily_state(self):
        """Reset state for a new trading day."""
        super().reset_daily_state()
        self.market_close_time = None
        self.entry_window_start = None
        self.entry_window_end = None
        self.entered_today = False

    def analyze_market(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Dict:
        """
        Analyze market conditions - check if we're in entry window.

        Returns:
            Dict with keys:
            - current_price: current underlying price
            - in_entry_window: bool (true if in entry window)
            - minutes_to_close: minutes until market close
        """
        analysis = {
            'current_price': 0.0,
            'in_entry_window': False,
            'minutes_to_close': 0,
        }

        if underlying_data.empty:
            return analysis

        current_price = underlying_data['close'].iloc[-1]
        analysis['current_price'] = current_price

        # Check if this is a new trading day
        current_day = current_time.date()
        if self.current_day is None or current_day != self.current_day:
            # New day - reset daily state
            self.reset_daily_state()
            self.current_day = current_day

        # Determine market close time (4:00 PM ET)
        if self.market_close_time is None:
            import pytz
            market_date = current_time.date()

            # Create 4:00 PM ET
            et_tz = pytz.timezone('America/New_York')
            market_close_et = et_tz.localize(
                datetime.combine(market_date, datetime.strptime("16:00", "%H:%M").time())
            )
            # Convert to UTC
            self.market_close_time = market_close_et.astimezone(pytz.UTC)

            # Entry window: 15 minutes before close (3:45 PM ET) until close
            # This is timeframe-agnostic - works with 1min, 5min, 15min, 1hr bars
            self.entry_window_start = self.market_close_time - timedelta(
                minutes=self.entry_time_before_close
            )
            # Allow entry any time from entry_window_start until close
            self.entry_window_end = self.market_close_time

        # Calculate time to close
        minutes_to_close = (self.market_close_time - current_time).total_seconds() / 60
        analysis['minutes_to_close'] = minutes_to_close

        # Check if we're in entry window (and haven't entered today)
        if (
            current_time >= self.entry_window_start
            and current_time <= self.entry_window_end
        ):
            # Only set in_entry_window if we haven't entered today
            analysis['in_entry_window'] = not self.entered_today

        return analysis

    def should_enter(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        market_analysis: Dict
    ) -> bool:
        """
        Determine if we should enter a position.

        Entry conditions:
        1. In entry window (15 min before close)
        2. No active position
        3. Haven't traded today yet
        4. Sufficient options liquidity
        """
        current_price = market_analysis.get('current_price', 0)

        # Don't enter if we have an active position
        if self.active_position is not None:
            return False

        # Don't enter if we've exceeded daily trade limit
        if not self.can_enter_new_position():
            return False

        # Must be in entry window
        if not market_analysis.get('in_entry_window', False):
            return False

        # Check if we have options data
        if options_data.empty:
            print(f"  ⚠️  No options data available")
            return False

        # All conditions met - log entry signal
        import pytz
        et_tz = pytz.timezone('America/New_York')
        if current_time.tzinfo is None:
            current_time_utc = pytz.UTC.localize(current_time)
        else:
            current_time_utc = current_time
        current_time_et = current_time_utc.astimezone(et_tz)

        print(f"\n  🚀 HAIL MARY BUY SIGNAL!")
        print(f"     Current Price: ${current_price:.2f}")
        print(f"     Time: {current_time_et.strftime('%H:%M:%S %Z')}")
        print(f"     Minutes to close: {market_analysis.get('minutes_to_close', 0):.1f}")

        return True

    def construct_spread(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        market_analysis: Dict,
        full_options_data: Optional[pd.DataFrame] = None
    ) -> Optional[OptionsPosition]:
        """
        Construct a long call position (single leg).

        Position structure:
        - Buy 10 CALL contracts
        - Strike: 5-10% above current price
        - Expiration: Next trading day (1 DTE)

        Args:
            underlying_data: OHLCV data for underlying
            options_data: Options chain data for current timestamp
            current_time: Current timestamp
            market_analysis: Result from analyze_market()
            full_options_data: Complete options dataset (for data completeness checks)

        Returns:
            OptionsPosition or None if position cannot be constructed
        """
        current_price = market_analysis.get('current_price', 0)

        if current_price == 0:
            return None

        # Calculate target strike range (5-10% OTM)
        min_strike = current_price * (1 + self.otm_percent_min)
        max_strike = current_price * (1 + self.otm_percent_max)

        # Filter for CALL options expiring next trading day (1 DTE)
        # Filter options by DTE range using base class utility (1-2 days for hail mary)
        dte_filtered = self._filter_by_dte(
            options_data=options_data,
            current_time=current_time,
            min_dte=1,
            max_dte=2
        )

        # Filter for CALL options in strike range
        valid_options = dte_filtered[
            (dte_filtered['contract_type'] == 'call') &
            (dte_filtered['strike_price'] >= min_strike) &
            (dte_filtered['strike_price'] <= max_strike)
        ]

        if valid_options.empty:
            print(f"  ⚠️  No call options found in strike range ${min_strike:.2f}-${max_strike:.2f}")
            return None

        # Apply liquidity filters using base class utility method
        liquid_options = self._filter_by_liquidity(
            options_data=valid_options,
            min_volume=self.min_volume,
            max_bid_ask_spread_pct=self.max_bid_ask_spread_pct
        )

        if liquid_options.empty:
            print(f"  ⚠️  No liquid options found (volume >= {self.min_volume}, spread <= {self.max_bid_ask_spread_pct}%)")
            return None

        # Select strike closest to middle of range (7.5% OTM)
        target_strike_pct = (self.otm_percent_min + self.otm_percent_max) / 2
        target_strike = current_price * (1 + target_strike_pct)

        # Find closest strike
        liquid_options = liquid_options.copy()
        liquid_options['strike_distance'] = abs(liquid_options['strike_price'] - target_strike)
        selected_option = liquid_options.sort_values('strike_distance').iloc[0]

        strike = selected_option['strike_price']
        expiration = selected_option['expiration_date']

        # Check for valid price
        if pd.isna(selected_option['mark']) or selected_option['mark'] <= 0:
            print(f"  ⚠️  Invalid mark price for selected strike")
            return None

        # Log selected contract
        print(f"\n  📋 Selected Contract:")
        print(f"     {strike} CALL (expiring {expiration.strftime('%Y-%m-%d')})")
        print(f"     Volume: {selected_option['volume']:.0f}")
        if 'bid' in selected_option and 'ask' in selected_option and selected_option['mark'] > 0:
            spread_pct = (
                (selected_option['ask'] - selected_option['bid']) / selected_option['mark'] * 100
            )
            print(
                f"     Bid/Ask: ${selected_option['bid']:.2f}/${selected_option['ask']:.2f} "
                f"(spread: {spread_pct:.2f}%)"
            )
        print(f"     Mark: ${selected_option['mark']:.2f}")
        print(f"     OTM: {((strike - current_price) / current_price * 100):.2f}%")

        # Calculate entry cost
        call_price = selected_option['mark']
        entry_cost = call_price * 100 * self.num_contracts  # Total cost for all contracts

        # Create single leg position
        legs = [
            OptionLeg(
                contract_symbol=selected_option['contract_symbol'],
                option_type=OptionType.CALL,
                strike_price=strike,
                expiration_date=expiration,
                quantity=self.num_contracts,  # Long calls
                entry_price=call_price
            )
        ]

        # Create position
        position = OptionsPosition(
            position_id=generate_position_id("HM", current_time),
            spread_type=SpreadType.SINGLE,
            legs=legs,
            entry_time=current_time,
            entry_cost=entry_cost,  # Debit (we pay)
            underlying_price_at_entry=current_price,
            profit_target_pct=None,  # No profit target, only trailing stop
            trailing_stop=self.trailing_stop_pct
        )

        # Mark that we entered today
        self.entered_today = True
        self.increment_daily_trade_count()

        print(f"     Total Cost: ${entry_cost:.2f}")

        return position

    def should_exit(
        self,
        position: OptionsPosition,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if we should exit the current position.

        Exit conditions:
        1. Trailing stop triggered (5% from peak)
        2. End of trading day (4:00 PM ET)
        3. Expiration approaching

        For long calls:
        - We want the call value to increase
        - Profit = current_value - entry_cost
        """
        # Get current underlying price
        underlying_price = underlying_data['close'].iloc[-1] if not underlying_data.empty else None

        # Update position value
        self.update_position_value(position, options_data, underlying_price)

        # Check trailing stop (only after market open next day)
        import pytz
        et_tz = pytz.timezone('America/New_York')
        if current_time.tzinfo is None:
            current_time_et = pytz.UTC.localize(current_time).astimezone(et_tz)
        else:
            current_time_et = current_time.astimezone(et_tz)

        # Enable trailing stop after 9:30 AM ET (market open)
        if current_time_et.hour >= 9 and current_time_et.minute >= 30:
            if self.check_trailing_stop(position):
                return True, "Trailing stop triggered"

        # Check if near end of day (close at 4:00 PM ET)
        if current_time_et.hour >= 16:
            return True, "End of trading day"

        # Check if expiration is approaching
        if position.legs:
            expiration = position.legs[0].expiration_date
            days_to_expiration = (expiration - current_time_et.date()).days

            # If expiring today, close at 3:45 PM ET (15 minutes before market close)
            if days_to_expiration == 0 and current_time_et.hour >= 15 and current_time_et.minute >= 45:
                return True, "Expiration approaching"

            # If expiration has passed
            if days_to_expiration < 0:
                return True, "Expiration passed"

        return False, None
