"""Bullish Vertical Put Spread Strategy for SPX."""

from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from .options_base import (
    OptionsStrategy,
    OptionsPosition,
    OptionLeg,
    OptionType,
    SpreadType
)
from quant_vibe.utils import generate_position_id


class BullishVerticalPutStrategy(OptionsStrategy):
    """
    Bullish Vertical Put Spread Strategy.

    Strategy Logic:
    1. Watch market open for 15-30 mins to determine direction and momentum
    2. If bullish, wait for a pullback (mean reversion)
    3. Enter when price pulls back 1 standard deviation from the high
    4. Open a $20 wide vertical put spread (credit spread)
    5. Target 50-100% profit, exit with 5% trailing stop

    Spread Structure:
    - Sell 1 put at higher strike (closer to ATM)
    - Buy 1 put at lower strike (further OTM)
    - Receive net credit on entry

    Entry Criteria:
    - First 15-30 mins shows bullish momentum
    - Price pulls back at least 1 standard deviation
    - Options have sufficient liquidity

    Exit Criteria:
    - Profit target reached (50-100% of max profit)
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
        min_volume: int = 50,  # minimum volume per contract
        min_bid_ask_spread_pct: float = 10.0,  # maximum bid/ask spread percentage
        max_trades_daily: int = 1,  # maximum trades per day
    ) -> None:
        """
        Initialize Bullish Vertical Put Strategy.

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
            min_volume: Minimum volume per contract for liquidity filter (default: 50)
            min_bid_ask_spread_pct: Maximum bid/ask spread percentage (default: 10%)
            max_trades_daily: Maximum trades allowed per day (default: 1)
        """
        super().__init__(name=f"BullishVerticalPut_{spread_width}", max_trades_daily=max_trades_daily)
        self.spread_width = spread_width
        self.observation_period = observation_period
        self.pullback_amount = pullback_amount
        self.profit_target_min = profit_target_min
        self.profit_target_max = profit_target_max
        self.trailing_stop_pct = trailing_stop_pct
        self.min_dte = min_dte
        self.max_dte = max_dte
        self.num_spreads = num_spreads
        self.min_volume = min_volume
        self.min_bid_ask_spread_pct = min_bid_ask_spread_pct

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

            # If current_time is timezone-aware (UTC), create market open in ET then convert
            if hasattr(current_time, 'tz') and current_time.tz is not None:
                # Create 9:30 AM ET
                et_tz = pytz.timezone('America/New_York')
                market_open_et = et_tz.localize(
                    datetime.combine(market_date, datetime.strptime("09:30", "%H:%M").time())
                )
                # Convert to UTC
                self.market_open_time = market_open_et.astimezone(pytz.UTC)
            else:
                # Naive datetime - assume local time
                self.market_open_time = datetime.combine(
                    market_date,
                    datetime.strptime("09:30", "%H:%M").time()
                )

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
                    print(f"     Opening Range: Insufficient data")

                if self.is_bullish and self.opening_high is not None:
                    pullback_threshold = self.opening_high - self.pullback_amount
                    print(f"     → Waiting for pullback to ${pullback_threshold:.2f}")
                else:
                    print(f"     → No entry - market not bullish or insufficient data")

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
            print(f"  ⚠️  No options data available")
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

        print(f"\n  🎯 BUY SIGNAL TRIGGERED!")
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
        Construct a bullish vertical put spread.

        Spread structure:
        - Sell 1 put at higher strike (closer to ATM)
        - Buy 1 put at lower strike (further OTM, for protection)

        This is a CREDIT spread - we receive premium on entry.

        Args:
            underlying_data: OHLCV data for underlying
            options_data: Options chain data for current timestamp
            current_time: Current timestamp
            market_analysis: Result from analyze_market()
            full_options_data: Complete options dataset (for data completeness checks)

        Returns:
            OptionsPosition or None if spread cannot be constructed
        """
        current_price = market_analysis.get('current_price', 0)

        if current_price == 0:
            return None

        # Filter options for appropriate expiration
        target_date = current_time + timedelta(days=self.min_dte)
        max_date = current_time + timedelta(days=self.max_dte)

        # Normalize expiration dates for comparison
        # expiration_date in DataFrame is datetime64[ns] (timezone-naive), normalize to midnight
        import pandas as pd
        target_date = pd.Timestamp(target_date).normalize().tz_localize(None)
        max_date = pd.Timestamp(max_date).normalize().tz_localize(None)

        # Filter for PUT options within DTE range
        # contract_type is 'put' (lowercase enum value)
        valid_options = options_data[
            (options_data['expiration_date'] >= target_date) &
            (options_data['expiration_date'] <= max_date) &
            (options_data['contract_type'] == 'put')
        ]

        if valid_options.empty:
            print(f"  ⚠️  No options found in DTE range {self.min_dte}-{self.max_dte}")
            return None

        # Apply liquidity filters
        # 1. Minimum volume filter
        liquid_options = valid_options[valid_options['volume'] >= self.min_volume]

        if liquid_options.empty:
            print(f"  ⚠️  No options with volume >= {self.min_volume}")
            return None

        # 2. Bid/ask spread filter (only if we have bid/ask data)
        if 'bid' in liquid_options.columns and 'ask' in liquid_options.columns:
            # Calculate spread percentage
            liquid_options = liquid_options.copy()
            liquid_options['bid_ask_spread_pct'] = (
                (liquid_options['ask'] - liquid_options['bid']) / liquid_options['mark'] * 100
            )

            # Filter out wide spreads
            liquid_options = liquid_options[
                liquid_options['bid_ask_spread_pct'] <= self.min_bid_ask_spread_pct
            ]

            if liquid_options.empty:
                print(f"  ⚠️  No options with bid/ask spread <= {self.min_bid_ask_spread_pct}%")
                return None

        # Use liquid_options for strike selection
        valid_options = liquid_options

        # Get the nearest expiration
        nearest_expiration = valid_options['expiration_date'].min()
        expiration_options = valid_options[
            valid_options['expiration_date'] == nearest_expiration
        ]

        # Find strike for short put (higher strike, closer to ATM)
        # Look for strike just below current price (slightly OTM)
        short_strike_candidates = expiration_options[
            expiration_options['strike_price'] <= current_price
        ].sort_values('strike_price', ascending=False)

        if short_strike_candidates.empty:
            return None

        short_strike = short_strike_candidates.iloc[0]['strike_price']
        long_strike = short_strike - self.spread_width

        # Find the contracts
        short_put = expiration_options[
            expiration_options['strike_price'] == short_strike
        ]

        long_put = expiration_options[
            expiration_options['strike_price'] == long_strike
        ]

        if short_put.empty or long_put.empty:
            return None

        # Get prices (use mark price = mid of bid/ask)
        short_put_data = short_put.iloc[0]
        long_put_data = long_put.iloc[0]

        # Check for valid prices
        if (pd.isna(short_put_data['mark']) or
            pd.isna(long_put_data['mark']) or
            short_put_data['mark'] <= 0 or
            long_put_data['mark'] <= 0):
            print(f"  ⚠️  Invalid mark prices for selected strikes")
            return None

        # Log selected contracts and their liquidity metrics
        print(f"\n  📋 Selected Contracts (passed liquidity filters):")
        print(f"     Short {short_strike} PUT:")
        print(f"       Volume: {short_put_data['volume']:.0f}")
        if 'bid' in short_put_data and 'ask' in short_put_data:
            spread_pct = (short_put_data['ask'] - short_put_data['bid']) / short_put_data['mark'] * 100
            print(f"       Bid/Ask: ${short_put_data['bid']:.2f}/${short_put_data['ask']:.2f} (spread: {spread_pct:.2f}%)")
        print(f"       Mark: ${short_put_data['mark']:.2f}")
        print(f"     Long {long_strike} PUT:")
        print(f"       Volume: {long_put_data['volume']:.0f}")
        if 'bid' in long_put_data and 'ask' in long_put_data:
            spread_pct = (long_put_data['ask'] - long_put_data['bid']) / long_put_data['mark'] * 100
            print(f"       Bid/Ask: ${long_put_data['bid']:.2f}/${long_put_data['ask']:.2f} (spread: {spread_pct:.2f}%)")
        print(f"       Mark: ${long_put_data['mark']:.2f}")

        # Validate data completeness for selected contracts
        # This checks that these contracts have been present in recent historical data
        # to reduce likelihood of missing data during position lifetime
        contract_symbols = [short_put_data['contract_symbol'], long_put_data['contract_symbol']]

        # Use full dataset if available, otherwise fall back to current slice
        data_for_validation = full_options_data if full_options_data is not None else options_data

        # DEBUG: Show what dataset is being used
        print(f"     [DEBUG] Validation dataset: {len(data_for_validation)} rows, {data_for_validation['timestamp'].nunique()} unique timestamps")
        print(f"     [DEBUG] Using {'FULL dataset' if full_options_data is not None else 'CURRENT SLICE only'}")

        is_valid, completeness = self.validate_data_completeness(
            contract_symbols=contract_symbols,
            options_data=data_for_validation,
            current_time=current_time,
            lookback_minutes=60,
            min_completeness_pct=95.0
        )

        print(f"\n  📊 Data Completeness Check:")
        for symbol, pct in completeness.items():
            strike = short_strike if 'contract_symbol' in short_put_data and short_put_data['contract_symbol'] == symbol else long_strike
            status = "✅" if pct >= 95.0 else "❌"
            print(f"     {status} {strike} PUT: {pct:.1f}% coverage")

        if not is_valid:
            print(f"  ⚠️  Skipping trade - insufficient data completeness (need ≥95%)")
            return None

        # Calculate net credit (premium received) per spread, then multiply by number of spreads
        short_put_price = short_put_data['mark']
        long_put_price = long_put_data['mark']
        net_credit_per_spread = (short_put_price - long_put_price) * 100  # Per contract
        net_credit = net_credit_per_spread * self.num_spreads  # Total for all spreads

        # For credit spreads, entry_cost is negative (we receive money)
        # But we need to reserve max risk = spread_width * 100 * num_spreads
        max_risk = self.spread_width * 100 * self.num_spreads

        # Create legs
        # Short put: negative quantity (we sell)
        # Long put: positive quantity (we buy for protection)
        legs = [
            OptionLeg(
                contract_symbol=short_put_data['contract_symbol'],
                option_type=OptionType.PUT,
                strike_price=short_strike,
                expiration_date=nearest_expiration,
                quantity=-self.num_spreads,  # Short (negative = sell)
                entry_price=short_put_price
            ),
            OptionLeg(
                contract_symbol=long_put_data['contract_symbol'],
                option_type=OptionType.PUT,
                strike_price=long_strike,
                expiration_date=nearest_expiration,
                quantity=self.num_spreads,  # Long (positive = buy)
                entry_price=long_put_price
            )
        ]

        # Create position
        # For credit spreads: entry_cost is negative (we receive credit)
        position = OptionsPosition(
            position_id=generate_position_id("BVP", current_time),
            spread_type=SpreadType.VERTICAL_PUT,
            legs=legs,
            entry_time=current_time,
            entry_cost=-net_credit,  # Negative because it's a credit
            underlying_price_at_entry=current_price,
            profit_target=self.profit_target_max,  # Use max profit target
            trailing_stop=self.trailing_stop_pct
        )

        # Increment daily trade counter
        self.increment_daily_trade_count()

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
        1. Profit target reached (50-100% of max profit)
        2. Trailing stop triggered (5% from high)
        3. End of trading day
        4. Expiration approaching

        For credit spreads:
        - We want the spread value to decrease (ideally to 0)
        - Profit = credit received - current spread value
        """
        # Get current underlying price for intrinsic value calculation
        underlying_price = underlying_data['close'].iloc[-1] if not underlying_data.empty else None

        # Update position value (with underlying price for intrinsic value)
        self.update_position_value(position, options_data, underlying_price)

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
            days_to_expiration = (expiration.date() - current_time_et.date()).days

            # If expiring today, close at 3:45 PM ET (15 minutes before market close)
            if days_to_expiration == 0 and current_time_et.hour >= 15 and current_time_et.minute >= 45:
                return True, "Expiration approaching"

            # If expiration has passed (shouldn't happen in normal trading)
            if days_to_expiration < 0:
                return True, "Expiration passed"

        return False, None
