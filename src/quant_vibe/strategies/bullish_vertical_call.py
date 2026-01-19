"""Bullish Vertical Call Spread Strategy for SPX."""

from typing import Optional, Dict, Tuple
from datetime import datetime
import pandas as pd

from .options_base import (
    OptionsStrategy,
    OptionsPosition,
    OptionLeg,
    OptionType,
    SpreadType
)
from quant_vibe.utils import generate_position_id
from quant_vibe.utils.pricing_utils import get_mark_price_from_row


class BullishVerticalCallStrategy(OptionsStrategy):
    """
    Bullish Vertical Call Spread Strategy.

    Strategy Logic:
    1. Watch market open for 15-30 mins to determine direction and momentum
    2. If bullish, wait for a pullback (mean reversion)
    3. Enter when price pulls back 1 standard deviation from the high
    4. Open a $20 wide vertical call spread
    5. Target 50-100% profit, exit with 5% trailing stop

    Entry Criteria:
    - First 15-30 mins shows bullish momentum
    - Price pulls back at least 1 standard deviation
    - Options have sufficient liquidity

    Exit Criteria:
    - Profit target reached (50-100%)
    - Trailing stop triggered (5% from high)
    - End of day
    """

    def __init__(
        self,
        spread_width: float = 20.0,
        observation_period: int = 30,  # minutes to watch market open
        pullback_amount: float = 50.0,  # dollar amount for pullback signal
        profit_target_min: float = 0.5,  # 50%
        profit_target_max: float = 1.0,  # 100%
        trailing_stop_pct: float = 0.05,  # 5%
        min_dte: int = 7,  # minimum days to expiration
        max_dte: int = 45,  # maximum days to expiration
        num_spreads: int = 10,  # number of spreads to open per signal
        max_trades_daily: int = 1,  # maximum trades per day
        **kwargs  # Accept any additional parameters from base class
    ) -> None:
        """
        Initialize Bullish Vertical Call Strategy.

        Args:
            spread_width: Width of the vertical spread (default: $20)
            observation_period: Minutes to observe market at open (default: 30)
            pullback_amount: Dollar amount for pullback signal (default: $50)
            profit_target_min: Minimum profit target percentage (default: 0.5 = 50%)
            profit_target_max: Maximum profit target percentage (default: 1.0 = 100%)
            trailing_stop_pct: Trailing stop percentage (default: 0.05 = 5%)
            min_dte: Minimum days to expiration for options (default: 7)
            max_dte: Maximum days to expiration for options (default: 45)
            num_spreads: Number of spreads to open per buy signal (default: 10)
            max_trades_daily: Maximum trades allowed per day (default: 1)
            **kwargs: Additional parameters passed to OptionsStrategy base class
        """
        super().__init__(
            name=f"BullishVerticalCall_{spread_width}",
            max_trades_daily=max_trades_daily,
            observation_period=observation_period,
            min_dte=min_dte,
            max_dte=max_dte,
            num_spreads=num_spreads,
            profit_target_min=profit_target_min,
            profit_target_max=profit_target_max,
            trailing_stop_pct=trailing_stop_pct,
            **kwargs  # Forward additional parameters to base class
        )

        # Strategy-specific parameters (not in base class)
        self.spread_width = spread_width
        self.pullback_amount = pullback_amount

        # State tracking
        self.market_open_time: Optional[datetime] = None
        self.opening_high: Optional[float] = None
        self.opening_low: Optional[float] = None
        self.opening_mean: Optional[float] = None
        self.opening_std: Optional[float] = None
        self.is_bullish: bool = False
        self.observation_complete: bool = False
        self.current_day: Optional[datetime] = None
        self.last_monitoring_log_time: Optional[datetime] = None
        self.monitoring_log_interval: int = 30  # Log every 30 minutes during monitoring

    def reset_daily_state(self):
        """Reset state for a new trading day."""
        super().reset_daily_state()  # Reset trades_today counter
        self.market_open_time = None
        self.opening_high = None
        self.opening_low = None
        self.opening_mean = None
        self.opening_std = None
        self.is_bullish = False
        self.observation_complete = False
        self.last_monitoring_log_time = None

    def analyze_market(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Dict:
        """
        Analyze market conditions during opening period.

        Returns:
            Dict with keys:
            - direction: 'bullish', 'bearish', or 'neutral'
            - momentum: float (rate of price change)
            - current_price: current underlying price
            - pullback_signal: bool (true if pullback detected)
        """
        analysis = {
            'direction': 'neutral',
            'momentum': 0.0,
            'current_price': 0.0,
            'pullback_signal': False,
            'observation_complete': self.observation_complete,
            'pullback_threshold': None,
            'price_change': 0.0
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

        # Determine market open time (9:30 AM ET = 14:30 UTC for SPX)
        if self.market_open_time is None:
            import pytz
            market_date = current_time.date()

            # Create 9:30 AM ET and convert to UTC
            et_tz = pytz.timezone('America/New_York')
            market_open_et = et_tz.localize(
                datetime.combine(market_date, datetime.strptime("09:30", "%H:%M").time())
            )
            # Always convert to UTC for timezone-aware comparison
            self.market_open_time = market_open_et.astimezone(pytz.UTC)

        # Calculate time since market open
        time_since_open = (current_time - self.market_open_time).total_seconds() / 60

        # During observation period (first 15-30 mins)
        if time_since_open <= self.observation_period and not self.observation_complete:
            # Get data since market open
            # Handle both backtesting (DatetimeIndex) and live (timestamp column) formats
            if isinstance(underlying_data.index, pd.DatetimeIndex):
                # Backtesting: filter by index
                opening_data = underlying_data[underlying_data.index >= self.market_open_time]
            else:
                # Live: filter by timestamp column
                opening_data = underlying_data[
                    underlying_data['timestamp'] >= self.market_open_time
                ]

            if len(opening_data) >= 2:
                self.opening_high = opening_data['high'].max()
                self.opening_low = opening_data['low'].min()
                self.opening_mean = opening_data['close'].mean()
                self.opening_std = opening_data['close'].std()

                # Calculate momentum (price change / time)
                price_change = opening_data['close'].iloc[-1] - opening_data['close'].iloc[0]
                time_elapsed = len(opening_data)
                momentum = price_change / time_elapsed if time_elapsed > 0 else 0

                analysis['momentum'] = momentum
                analysis['price_change'] = price_change

                # Determine direction
                if price_change > 0 and momentum > 0:
                    analysis['direction'] = 'bullish'
                    self.is_bullish = True
                elif price_change < 0 and momentum < 0:
                    analysis['direction'] = 'bearish'
                    self.is_bullish = False

            # Complete observation at end of period
            if time_since_open >= self.observation_period - 1:
                self.observation_complete = True

                # Log observation results
                print(f"\n  📊 OBSERVATION COMPLETE (after {self.observation_period} mins)")
                print(f"     Direction: {analysis['direction'].upper()}")
                print(f"     Momentum: {analysis.get('momentum', 0):.4f} pts/bar")
                print(f"     Price Change: ${analysis.get('price_change', 0):.2f}")

                # Only print range stats if we have valid data
                if self.opening_low is not None and self.opening_high is not None:
                    print(f"     Opening Range: ${self.opening_low:.2f} - ${self.opening_high:.2f}")
                    print(f"     Opening Mean: ${self.opening_mean:.2f}, Std Dev: ${self.opening_std:.2f}")
                else:
                    print("     Opening Range: Insufficient data")

                if self.is_bullish and self.opening_high is not None:
                    pullback_threshold = self.opening_high - self.pullback_amount
                    print(f"     → Waiting for pullback to ${pullback_threshold:.2f}")
                else:
                    print("     → No entry - market not bullish or insufficient data")

        # After observation period - check for pullback
        elif self.observation_complete and self.is_bullish:
            analysis['direction'] = 'bullish'

            # Check if we've pulled back from the opening high
            if self.opening_high is not None:

                # Pullback signal: price is $X below opening high
                pullback_threshold = self.opening_high - self.pullback_amount
                analysis['pullback_threshold'] = pullback_threshold

                # Periodic monitoring update
                should_log = False
                if self.last_monitoring_log_time is None:
                    should_log = True
                else:
                    minutes_since_last_log = (current_time - self.last_monitoring_log_time).total_seconds() / 60
                    if minutes_since_last_log >= self.monitoring_log_interval:
                        should_log = True

                if should_log:
                    distance_to_pullback = current_price - pullback_threshold
                    print(f"  📍 {current_time.strftime('%H:%M')} - Monitoring for pullback")
                    print(f"     Current: ${current_price:.2f} | Target: ${pullback_threshold:.2f} | Distance: ${distance_to_pullback:.2f}")
                    self.last_monitoring_log_time = current_time

                if current_price <= pullback_threshold:
                    analysis['pullback_signal'] = True

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
        1. Observation period is complete
        2. Market direction is bullish
        3. Pullback signal is triggered
        4. No active position
        5. Haven't traded today yet (only 1 position per day)
        6. Sufficient options liquidity
        """
        current_price = market_analysis.get('current_price', 0)
        pullback_threshold = market_analysis.get('pullback_threshold')

        # Don't enter if we have an active position
        if self.active_position is not None:
            return False

        # Don't enter if we've exceeded daily trade limit
        if not self.can_enter_new_position():
            return False

        # Must complete observation period
        if not market_analysis.get('observation_complete', False):
            return False

        # Must be bullish
        if market_analysis.get('direction') != 'bullish':
            return False

        # Must have pullback signal
        if not market_analysis.get('pullback_signal', False):
            return False

        # Check if we have options data
        if options_data.empty:
            print("  ⚠️  No options data available")
            return False

        # All conditions met - log entry signal
        # Convert to ET for display
        import pytz
        et_tz = pytz.timezone('America/New_York')
        if current_time.tzinfo is None:
            current_time_utc = pytz.UTC.localize(current_time)
        else:
            current_time_utc = current_time
        current_time_et = current_time_utc.astimezone(et_tz)

        print("\n  🎯 BUY SIGNAL TRIGGERED!")
        print(f"     Current Price: ${current_price:.2f}")
        print(f"     Pullback Threshold: ${pullback_threshold:.2f}")
        print(f"     Pullback Amount: ${pullback_threshold - current_price:.2f} ({((pullback_threshold - current_price) / current_price * 100):.2f}%)")
        print(f"     Time: {current_time_et.strftime('%H:%M:%S %Z')}")

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
        Construct a bullish vertical call spread.

        Spread structure:
        - Buy 1 call at lower strike (ATM or slightly OTM)
        - Sell 1 call at higher strike (lower strike + spread_width)

        Returns:
            OptionsPosition or None if spread cannot be constructed
        """
        current_price = market_analysis.get('current_price', 0)

        if current_price == 0:
            return None

        # Filter options by DTE range using base class utility
        dte_filtered = self._filter_by_dte(
            options_data=options_data,
            current_time=current_time,
            min_dte=self.min_dte,
            max_dte=self.max_dte
        )

        # Filter for CALL options
        valid_options = dte_filtered[dte_filtered['contract_type'] == 'call']

        if valid_options.empty:
            return None

        # Get the nearest expiration
        nearest_expiration = valid_options['expiration_date'].min()
        expiration_options = valid_options[
            valid_options['expiration_date'] == nearest_expiration
        ]

        # Find ATM or slightly OTM strike for long call
        # Look for strike just above current price
        long_strike_candidates = expiration_options[
            expiration_options['strike_price'] >= current_price
        ].sort_values('strike_price')

        if long_strike_candidates.empty:
            return None

        long_strike = long_strike_candidates.iloc[0]['strike_price']
        short_strike = long_strike + self.spread_width

        # Find the contracts
        long_call = expiration_options[
            expiration_options['strike_price'] == long_strike
        ]

        short_call = expiration_options[
            expiration_options['strike_price'] == short_strike
        ]

        if long_call.empty or short_call.empty:
            return None

        # Get prices (use mark price = mid of bid/ask)
        long_call_data = long_call.iloc[0]
        short_call_data = short_call.iloc[0]

        # Calculate mark prices using pricing utilities
        long_call_price = get_mark_price_from_row(long_call_data)
        short_call_price = get_mark_price_from_row(short_call_data)

        # Check for valid prices
        if long_call_price <= 0 or short_call_price <= 0:
            return None

        # Calculate net debit (cost to enter) per spread, then multiply by number of spreads
        net_debit_per_spread = (long_call_price - short_call_price) * 100  # Per contract
        net_debit = net_debit_per_spread * self.num_spreads  # Total for all spreads

        # Create legs (quantity represents number of contracts = number of spreads)
        legs = [
            OptionLeg(
                option_ticker=long_call_data['option_ticker'],
                option_type=OptionType.CALL,
                strike_price=long_strike,
                expiration_date=nearest_expiration,
                quantity=self.num_spreads,  # Long (positive = buy)
                entry_price=long_call_price
            ),
            OptionLeg(
                option_ticker=short_call_data['option_ticker'],
                option_type=OptionType.CALL,
                strike_price=short_strike,
                expiration_date=nearest_expiration,
                quantity=-self.num_spreads,  # Short (negative = sell)
                entry_price=short_call_price
            )
        ]

        # Create position
        position = OptionsPosition(
            position_id=generate_position_id("BVC", current_time),
            spread_type=SpreadType.VERTICAL_CALL,
            legs=legs,
            entry_time=current_time,
            entry_cost=net_debit,
            underlying_price_at_entry=current_price,
            profit_target_pct=self.profit_target_max,  # Use max profit target
            trailing_stop=self.trailing_stop_pct
        )

        # Increment daily trade counter
        self.increment_daily_trade_count()

        return position

    def _check_strategy_exits(
        self,
        position: OptionsPosition,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Check strategy-specific exit conditions.

        Exit conditions:
        1. Profit target reached (50-100%)
        2. Trailing stop triggered (5% from high)
        3. End of trading day
        4. Expiration approaching

        Note: Absolute stop loss is automatically checked by base class.

        Returns:
            Tuple of (should_exit, exit_reason)
        """
        # Update position value
        current_underlying_price = underlying_data['close'].iloc[-1] if not underlying_data.empty else None
        self.update_position_value(position, options_data, current_underlying_price)

        # Check profit target
        if self.check_profit_target(position):
            return True, "Profit target reached"

        # Check trailing stop
        if self.check_trailing_stop(position):
            return True, "Trailing stop triggered"

        # Check if near end of day (close at 4:00 PM ET)
        # Convert to ET for checking time of day
        import pytz
        et_tz = pytz.timezone('America/New_York')
        if current_time.tzinfo is None:
            current_time_et = pytz.UTC.localize(current_time).astimezone(et_tz)
        else:
            current_time_et = current_time.astimezone(et_tz)

        if current_time_et.hour >= 16:
            return True, "End of trading day"

        # Check if expiration is approaching (close 15 minutes before market close on expiration day)
        if position.legs:
            expiration = position.legs[0].expiration_date
            days_to_expiration = (expiration - current_time_et.date()).days

            # If expiring today, close at 3:45 PM ET (15 minutes before market close)
            if days_to_expiration == 0 and current_time_et.hour >= 15 and current_time_et.minute >= 45:
                return True, "Expiration approaching"

            # If expiration has passed (shouldn't happen in normal trading)
            if days_to_expiration < 0:
                return True, "Expiration passed"

        return False, None
