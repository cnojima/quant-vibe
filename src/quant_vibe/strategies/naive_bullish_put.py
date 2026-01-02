"""Naive Bullish Vertical Put Spread Strategy - Opens at Market Open."""

from typing import Optional, Dict, Tuple
from datetime import datetime, timedelta
import pandas as pd
import pytz

from .options_base import (
    OptionsStrategy,
    OptionsPosition,
    OptionLeg,
    OptionType,
    SpreadType
)
from quant_vibe.utils import generate_position_id


class NaiveBullishPutStrategy(OptionsStrategy):
    """
    Naive Bullish Vertical Put Spread Strategy.

    Simple strategy for UI testing:
    - Opens a vertical put spread at market open (9:30 AM ET)
    - Uses $20 spread width
    - Targets 50% profit
    - Exits at end of day or profit target

    This is a simplified version to test how multi-leg spreads
    appear in the Admin UI.
    """

    def __init__(
        self,
        spread_width: float = 20.0,
        profit_target: float = 0.5,  # 50%
        min_dte: int = 7,
        max_dte: int = 45,
        num_spreads: int = 10,
        max_trades_daily: int = 1,
    ) -> None:
        """
        Initialize Naive Bullish Put Strategy.

        Args:
            spread_width: Width of the vertical spread (default: $20)
            profit_target: Profit target percentage (default: 0.5 = 50%)
            min_dte: Minimum days to expiration (default: 7)
            max_dte: Maximum days to expiration (default: 45)
            num_spreads: Number of spreads to open (default: 10)
            max_trades_daily: Maximum trades per day (default: 1)
        """
        super().__init__(name=f"NaiveBullishPut_{spread_width}", max_trades_daily=max_trades_daily)
        self.spread_width = spread_width
        self.profit_target = profit_target
        self.min_dte = min_dte
        self.max_dte = max_dte
        self.num_spreads = num_spreads

        # State tracking
        self.market_open_time: Optional[datetime] = None
        self.has_entered_today: bool = False
        self.current_day: Optional[datetime] = None

    def reset_daily_state(self):
        """Reset state for a new trading day."""
        super().reset_daily_state()
        self.market_open_time = None
        self.has_entered_today = False

    def analyze_market(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Dict:
        """Simple market analysis - just track if market is open."""
        print(f"\nNBP 🔍 [ANALYZE_MARKET] Called at {current_time}")

        analysis = {
            'market_open': False,
            'current_price': 0.0,
        }

        if underlying_data.empty:
            print(f"NBP ⚠️  [ANALYZE_MARKET] No underlying data available")
            return analysis

        current_price = underlying_data['close'].iloc[-1]
        analysis['current_price'] = current_price
        print(f"NBP 💰 [ANALYZE_MARKET] Current price: ${current_price:.2f}")

        # Check if new trading day
        current_day = current_time.date()
        if self.current_day is None or current_day != self.current_day:
            print(f"NBP 📅 [ANALYZE_MARKET] New trading day detected: {current_day}")
            self.reset_daily_state()
            self.current_day = current_day

        # Determine market open time (9:30 AM ET)
        if self.market_open_time is None:
            et_tz = pytz.timezone('America/New_York')
            market_date = current_time.date()

            if hasattr(current_time, 'tz') and current_time.tz is not None:
                market_open_et = et_tz.localize(
                    datetime.combine(market_date, datetime.strptime("09:30", "%H:%M").time())
                )
                self.market_open_time = market_open_et.astimezone(pytz.UTC)
            else:
                self.market_open_time = datetime.combine(
                    market_date,
                    datetime.strptime("09:30", "%H:%M").time()
                )
            print(f"NBP ⏰ [ANALYZE_MARKET] Market open time set to: {self.market_open_time}")

        # Check if market just opened (within 5 minutes)
        time_since_open = (current_time - self.market_open_time).total_seconds() / 60
        print(f"NBP ⏱️  [ANALYZE_MARKET] Time since market open: {time_since_open:.2f} minutes")

        if 0 <= time_since_open <= 5:
            analysis['market_open'] = True
            print(f"NBP ✅ [ANALYZE_MARKET] Market IS OPEN (within 5 min window)")
        else:
            print(f"NBP ❌ [ANALYZE_MARKET] Market NOT open (outside 5 min window)")

        return analysis

    def should_enter(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        market_analysis: Dict
    ) -> bool:
        """
        Enter at market open if we haven't traded today.
        """
        print(f"\nNBP 🚦 [SHOULD_ENTER] Called at {current_time}")
        print(f"NBP    Active position: {self.active_position is not None}")
        print(f"NBP    Has entered today: {self.has_entered_today}")
        print(f"NBP    Can enter new position: {self.can_enter_new_position()}")
        print(f"NBP    Daily trades: {self.daily_trade_count}/{self.max_trades_daily}")

        # Don't enter if we have an active position
        if self.active_position is not None:
            print(f"NBP ❌ [SHOULD_ENTER] Already have active position")
            return False

        # Don't enter if we've already traded today
        if self.has_entered_today:
            print(f"NBP ❌ [SHOULD_ENTER] Already entered today")
            return False

        if not self.can_enter_new_position():
            print(f"NBP ❌ [SHOULD_ENTER] Cannot enter new position (daily limit reached)")
            return False

        # Enter at market open
        market_open = market_analysis.get('market_open', False)
        print(f"NBP    Market open status: {market_open}")
        if not market_open:
            print(f"NBP ❌ [SHOULD_ENTER] Market not open")
            return False

        # Check if we have options data
        if options_data.empty:
            print(f"NBP ⚠️  [SHOULD_ENTER] No options data available")
            return False

        print(f"NBP    Options data rows: {len(options_data)}")

        current_price = market_analysis.get('current_price', 0)
        print(f"\nNBP 🎯 [SHOULD_ENTER] ✅ ENTRY SIGNAL - Market Open")
        print(f"NBP    Current Price: ${current_price:.2f}")

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
        Construct a simple bullish vertical put spread.

        Spread structure:
        - Sell 1 put at higher strike (closer to ATM)
        - Buy 1 put at lower strike (further OTM)
        """
        print(f"\nNBP 🏗️  [CONSTRUCT_SPREAD] Called at {current_time}")

        current_price = market_analysis.get('current_price', 0)
        print(f"NBP    Current price: ${current_price:.2f}")

        if current_price == 0:
            print(f"NBP ❌ [CONSTRUCT_SPREAD] Invalid current price")
            return None

        # Filter options for appropriate expiration
        target_date = current_time + timedelta(days=self.min_dte)
        max_date = current_time + timedelta(days=self.max_dte)

        target_date = pd.Timestamp(target_date).normalize().tz_localize(None)
        max_date = pd.Timestamp(max_date).normalize().tz_localize(None)

        print(f"NBP    DTE range: {self.min_dte}-{self.max_dte} days")
        print(f"NBP    Target expiration: {target_date} to {max_date}")

        # Filter for PUT options within DTE range
        valid_options = options_data[
            (options_data['expiration_date'] >= target_date) &
            (options_data['expiration_date'] <= max_date) &
            (options_data['contract_type'] == 'put')
        ]

        print(f"NBP    Total options in data: {len(options_data)}")
        print(f"NBP    Valid PUT options in DTE range: {len(valid_options)}")

        if valid_options.empty:
            print(f"NBP ❌ [CONSTRUCT_SPREAD] No options found in DTE range {self.min_dte}-{self.max_dte}")
            return None

        # Get the nearest expiration
        nearest_expiration = valid_options['expiration_date'].min()
        expiration_options = valid_options[
            valid_options['expiration_date'] == nearest_expiration
        ]
        print(f"NBP    Nearest expiration: {nearest_expiration}")
        print(f"NBP    Options at nearest expiration: {len(expiration_options)}")

        # Find strike for short put (just below current price)
        short_strike_candidates = expiration_options[
            expiration_options['strike_price'] <= current_price
        ].sort_values('strike_price', ascending=False)

        print(f"NBP    Short strike candidates: {len(short_strike_candidates)}")

        if short_strike_candidates.empty:
            print(f"NBP ❌ [CONSTRUCT_SPREAD] No short strike candidates found")
            return None

        short_strike = short_strike_candidates.iloc[0]['strike_price']
        long_strike = short_strike - self.spread_width

        print(f"NBP    Selected strikes: Short=${short_strike}, Long=${long_strike}")

        # Find the contracts
        short_put = expiration_options[
            expiration_options['strike_price'] == short_strike
        ]
        long_put = expiration_options[
            expiration_options['strike_price'] == long_strike
        ]

        if short_put.empty or long_put.empty:
            print(f"NBP ❌ [CONSTRUCT_SPREAD] Cannot find both strikes: ${short_strike} and ${long_strike}")
            print(f"NBP    Short put found: {not short_put.empty}, Long put found: {not long_put.empty}")
            return None

        short_put_data = short_put.iloc[0]
        long_put_data = long_put.iloc[0]

        # Check for valid prices
        if (pd.isna(short_put_data['mark']) or
            pd.isna(long_put_data['mark']) or
            short_put_data['mark'] <= 0 or
            long_put_data['mark'] <= 0):
            print(f"NBP ❌ [CONSTRUCT_SPREAD] Invalid mark prices")
            print(f"NBP    Short mark: ${short_put_data['mark']}, Long mark: ${long_put_data['mark']}")
            return None

        print(f"\nNBP 📋 [CONSTRUCT_SPREAD] Opening Spread:")
        print(f"NBP    SELL {self.num_spreads}x {short_strike} PUT @ ${short_put_data['mark']:.2f}")
        print(f"NBP    BUY  {self.num_spreads}x {long_strike} PUT @ ${long_put_data['mark']:.2f}")

        # Calculate net credit
        short_put_price = short_put_data['mark']
        long_put_price = long_put_data['mark']
        net_credit_per_spread = (short_put_price - long_put_price) * 100
        net_credit = net_credit_per_spread * self.num_spreads

        print(f"NBP    Net Credit: ${net_credit:.2f} (per spread: ${net_credit_per_spread:.2f})")

        # Create legs
        legs = [
            OptionLeg(
                contract_symbol=short_put_data['contract_symbol'],
                option_type=OptionType.PUT,
                strike_price=short_strike,
                expiration_date=nearest_expiration,
                quantity=-self.num_spreads,  # Short (sell)
                entry_price=short_put_price
            ),
            OptionLeg(
                contract_symbol=long_put_data['contract_symbol'],
                option_type=OptionType.PUT,
                strike_price=long_strike,
                expiration_date=nearest_expiration,
                quantity=self.num_spreads,  # Long (buy)
                entry_price=long_put_price
            )
        ]

        # Create position (credit spread has negative entry_cost)
        position_id = generate_position_id("NBP", current_time)
        position = OptionsPosition(
            position_id=position_id,
            spread_type=SpreadType.VERTICAL_PUT,
            legs=legs,
            entry_time=current_time,
            entry_cost=-net_credit,  # Negative = we receive credit
            underlying_price_at_entry=current_price,
            profit_target=self.profit_target,
        )

        print(f"NBP ✅ [CONSTRUCT_SPREAD] Position created: {position_id}")

        # Mark that we've entered today
        self.has_entered_today = True
        self.increment_daily_trade_count()
        print(f"NBP    Daily trades now: {self.daily_trade_count}/{self.max_trades_daily}")

        return position

    def should_exit(
        self,
        position: OptionsPosition,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Exit at profit target or end of day.
        """
        print(f"\nNBP 🚪 [SHOULD_EXIT] Called at {current_time}")
        print(f"NBP    Position ID: {position.position_id}")

        # Get current underlying price
        underlying_price = underlying_data['close'].iloc[-1] if not underlying_data.empty else None
        print(f"NBP    Current underlying price: ${underlying_price:.2f}" if underlying_price else "NBP    No underlying price")

        # Update position value
        self.update_position_value(position, options_data, underlying_price)
        print(f"NBP    Position current value: ${position.current_value:.2f}")
        print(f"NBP    Position P&L: ${position.current_pnl:.2f}")
        if position.current_value != 0:
            pnl_pct = (position.current_pnl / abs(position.entry_cost)) * 100
            print(f"NBP    P&L %: {pnl_pct:.2f}%")

        # Check profit target
        if self.check_profit_target(position):
            print(f"NBP ✅ [SHOULD_EXIT] Profit target reached!")
            return True, "Profit target reached"

        # Check if end of day (4:00 PM ET)
        et_tz = pytz.timezone('America/New_York')
        if current_time.tzinfo is None:
            current_time_et = pytz.UTC.localize(current_time).astimezone(et_tz)
        else:
            current_time_et = current_time.astimezone(et_tz)

        print(f"NBP    Current time ET: {current_time_et.strftime('%H:%M:%S')}")

        if current_time_et.hour >= 16:
            print(f"NBP ✅ [SHOULD_EXIT] End of trading day")
            return True, "End of trading day"

        # Close early if expiring today
        if position.legs:
            expiration = position.legs[0].expiration_date
            days_to_expiration = (expiration.date() - current_time_et.date()).days
            print(f"NBP    DTE: {days_to_expiration}")

            if days_to_expiration == 0 and current_time_et.hour >= 15 and current_time_et.minute >= 45:
                print(f"NBP ✅ [SHOULD_EXIT] Expiration approaching")
                return True, "Expiration approaching"

        print(f"NBP ❌ [SHOULD_EXIT] No exit conditions met")
        return False, None
