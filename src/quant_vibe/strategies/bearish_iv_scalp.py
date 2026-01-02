"""Bearish IV Scalp Strategy for 0DTE SPXW Options.

This strategy capitalizes on elevated implied volatility during bearish market
conditions by selling vertical call spreads on same-day expiration (0DTE) SPXW options.

The key insight is that during bearish sell-offs, call option IV often spikes due to
hedging demand, creating opportunities to sell premium that may quickly decay as
volatility normalizes.
"""

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


class BearishIVScalpStrategy(OptionsStrategy):
    """
    Bearish IV Scalp Strategy for 0DTE SPXW.

    Strategy Logic:
    1. Monitor market for bearish momentum + elevated IV
    2. Wait for IV spike on call options (typically during sell-offs)
    3. Sell vertical call spread (credit spread)
    4. Quick scalp exit: 30-50% profit target or tight trailing stop
    5. Close all positions before end of day (0DTE management)

    Spread Structure:
    - Sell 1 call at lower strike (closer to ATM)
    - Buy 1 call at higher strike (further OTM, for protection)
    - Receive net credit on entry

    Entry Criteria:
    - Bearish market momentum (price declining)
    - Elevated IV (> threshold)
    - IV spike detected (recent increase)
    - 0DTE options available
    - Sufficient liquidity

    Exit Criteria:
    - Profit target reached (30-50% of max profit)
    - Tight trailing stop (3-5%)
    - End of day (by 3:45 PM ET for 0DTE)
    - Stop loss (50-75% of max loss)

    Risk Management:
    - 0DTE only (same-day expiration)
    - Maximum 1-2 trades per day
    - Position sizing: 5-10 spreads per entry
    - Stop loss: 50-75% of max risk
    """

    def __init__(
        self,
        spread_width: float = 10.0,  # Tighter spreads for 0DTE scalping
        observation_period: int = 15,  # Quick observation (15 mins)
        iv_threshold: float = 0.15,  # Minimum IV (15%)
        iv_spike_pct: float = 0.10,  # IV must increase by 10% from recent avg
        profit_target_min: float = 0.30,  # 30% profit target
        profit_target_max: float = 0.50,  # 50% profit target
        trailing_stop_pct: float = 0.03,  # Tight 3% trailing stop
        stop_loss_pct: float = 0.75,  # Stop loss at 75% of max risk
        min_dte: int = 0,  # 0DTE only
        max_dte: int = 0,  # 0DTE only
        num_spreads: int = 5,  # Smaller size for scalping
        min_volume: int = 20,  # Lower volume requirement for 0DTE
        min_bid_ask_spread_pct: float = 15.0,  # Wider spreads acceptable for 0DTE
        max_trades_daily: int = 2,  # Allow 1-2 scalps per day
        momentum_lookback: int = 5,  # Bars to look back for momentum
        iv_lookback: int = 30,  # Bars to look back for IV average
    ) -> None:
        """
        Initialize Bearish IV Scalp Strategy.

        Args:
            spread_width: Width of the vertical spread (default: $10)
            observation_period: Minutes to observe market before trading (default: 15)
            iv_threshold: Minimum IV level required (default: 0.15 = 15%)
            iv_spike_pct: Required IV increase from recent avg (default: 0.10 = 10%)
            profit_target_min: Minimum profit target percentage (default: 0.30 = 30%)
            profit_target_max: Maximum profit target percentage (default: 0.50 = 50%)
            trailing_stop_pct: Trailing stop percentage (default: 0.03 = 3%)
            stop_loss_pct: Stop loss percentage (default: 0.75 = 75% of max risk)
            min_dte: Minimum days to expiration (default: 0)
            max_dte: Maximum days to expiration (default: 0)
            num_spreads: Number of spreads to open per signal (default: 5)
            min_volume: Minimum volume per contract (default: 20)
            min_bid_ask_spread_pct: Maximum bid/ask spread percentage (default: 15%)
            max_trades_daily: Maximum trades per day (default: 2)
            momentum_lookback: Bars to analyze for momentum (default: 5)
            iv_lookback: Bars to analyze for IV average (default: 30)
        """
        super().__init__(
            name=f"BearishIVScalp_{spread_width}",
            max_trades_daily=max_trades_daily
        )
        self.spread_width = spread_width
        self.observation_period = observation_period
        self.iv_threshold = iv_threshold
        self.iv_spike_pct = iv_spike_pct
        self.profit_target_min = profit_target_min
        self.profit_target_max = profit_target_max
        self.trailing_stop_pct = trailing_stop_pct
        self.stop_loss_pct = stop_loss_pct
        self.min_dte = min_dte
        self.max_dte = max_dte
        self.num_spreads = num_spreads
        self.min_volume = min_volume
        self.min_bid_ask_spread_pct = min_bid_ask_spread_pct
        self.momentum_lookback = momentum_lookback
        self.iv_lookback = iv_lookback

        # State tracking
        self.market_open_time: Optional[datetime] = None
        self.is_bearish: bool = False
        self.observation_complete: bool = False
        self.current_day: Optional[datetime] = None
        self.last_monitoring_log_time: Optional[datetime] = None
        self.monitoring_log_interval: int = 15  # Log every 15 minutes

    def reset_daily_state(self):
        """Reset state for a new trading day."""
        super().reset_daily_state()
        self.market_open_time = None
        self.is_bearish = False
        self.observation_complete = False
        self.last_monitoring_log_time = None

    def _calculate_iv_metrics(
        self,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Dict:
        """
        Calculate IV metrics for entry signal.

        Returns:
            Dict with:
            - current_iv: Current average IV for ATM calls
            - recent_avg_iv: Average IV over lookback period
            - iv_spike: Boolean indicating IV spike
            - iv_change_pct: Percentage change in IV
        """
        metrics = {
            'current_iv': None,
            'recent_avg_iv': None,
            'iv_spike': False,
            'iv_change_pct': 0.0
        }

        if options_data.empty:
            return metrics

        # Get ATM call options (within 2% of current price)
        # First, get current underlying price
        if 'underlying_price' in options_data.columns:
            current_price = options_data['underlying_price'].iloc[-1]
        else:
            # Estimate from ATM option strikes
            current_price = options_data['strike_price'].median()

        atm_range = current_price * 0.02  # ±2%
        atm_calls = options_data[
            (options_data['contract_type'] == 'call') &
            (options_data['strike_price'] >= current_price - atm_range) &
            (options_data['strike_price'] <= current_price + atm_range) &
            (options_data['implied_volatility'].notna()) &
            (options_data['implied_volatility'] > 0)
        ]

        if atm_calls.empty:
            return metrics

        # Current IV (average of ATM calls)
        current_iv = atm_calls['implied_volatility'].mean()
        metrics['current_iv'] = current_iv

        # Recent average IV (over lookback period)
        lookback_time = current_time - timedelta(minutes=self.iv_lookback)

        # Get historical ATM call IV
        if isinstance(options_data.index, pd.DatetimeIndex):
            historical_data = options_data[options_data.index >= lookback_time]
        else:
            historical_data = options_data[
                options_data['timestamp'] >= lookback_time
            ]

        historical_atm = historical_data[
            (historical_data['option_type'] == 'CALL') &
            (historical_data['strike_price'] >= current_price - atm_range) &
            (historical_data['strike_price'] <= current_price + atm_range) &
            (historical_data['implied_volatility'].notna()) &
            (historical_data['implied_volatility'] > 0)
        ]

        if not historical_atm.empty:
            recent_avg_iv = historical_atm['implied_volatility'].mean()
            metrics['recent_avg_iv'] = recent_avg_iv

            # Check for IV spike
            if recent_avg_iv > 0:
                iv_change_pct = (current_iv - recent_avg_iv) / recent_avg_iv
                metrics['iv_change_pct'] = iv_change_pct

                # IV spike if current > threshold AND increased by spike_pct
                if (current_iv >= self.iv_threshold and
                    iv_change_pct >= self.iv_spike_pct):
                    metrics['iv_spike'] = True

        return metrics

    def analyze_market(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Dict:
        """
        Analyze market conditions for bearish momentum and IV spike.

        Returns:
            Dict with keys:
            - direction: 'bullish', 'bearish', or 'neutral'
            - momentum: float (rate of price change)
            - current_price: current underlying price
            - current_iv: current average IV
            - iv_spike: bool (IV spike detected)
            - entry_signal: bool (ready to enter)
        """
        analysis = {
            'direction': 'neutral',
            'momentum': 0.0,
            'current_price': 0.0,
            'current_iv': None,
            'recent_avg_iv': None,
            'iv_spike': False,
            'iv_change_pct': 0.0,
            'entry_signal': False,
            'observation_complete': self.observation_complete,
        }

        if underlying_data.empty:
            return analysis

        current_price = underlying_data['close'].iloc[-1]
        analysis['current_price'] = current_price

        # Check if this is a new trading day
        current_day = current_time.date()
        if self.current_day is None or current_day != self.current_day:
            self.reset_daily_state()
            self.current_day = current_day

        # Determine market open time (9:30 AM ET)
        if self.market_open_time is None:
            import pytz
            market_date = current_time.date()

            if hasattr(current_time, 'tz') and current_time.tz is not None:
                et_tz = pytz.timezone('America/New_York')
                market_open_et = et_tz.localize(
                    datetime.combine(market_date, datetime.strptime("09:30", "%H:%M").time())
                )
                self.market_open_time = market_open_et.astimezone(pytz.UTC)
            else:
                self.market_open_time = datetime.combine(
                    market_date,
                    datetime.strptime("09:30", "%H:%M").time()
                )

        # Calculate time since market open
        time_since_open = (current_time - self.market_open_time).total_seconds() / 60

        # Observation period - determine market direction
        if time_since_open <= self.observation_period and not self.observation_complete:
            # Get recent momentum (last N bars)
            if len(underlying_data) >= self.momentum_lookback:
                recent_data = underlying_data.tail(self.momentum_lookback)
                price_change = recent_data['close'].iloc[-1] - recent_data['close'].iloc[0]
                momentum = price_change / len(recent_data)

                analysis['momentum'] = momentum

                # Bearish if price declining
                if price_change < 0 and momentum < 0:
                    analysis['direction'] = 'bearish'
                    self.is_bearish = True
                elif price_change > 0 and momentum > 0:
                    analysis['direction'] = 'bullish'
                    self.is_bearish = False

            # Complete observation
            if time_since_open >= self.observation_period - 1:
                self.observation_complete = True

                print(f"\n  📊 OBSERVATION COMPLETE (after {self.observation_period} mins)")
                print(f"     Direction: {analysis['direction'].upper()}")
                print(f"     Momentum: {analysis.get('momentum', 0):.4f} pts/bar")
                print(f"     Current Price: ${current_price:.2f}")

                if self.is_bearish:
                    print(f"     → Monitoring for IV spike on bearish day")
                else:
                    print(f"     → No entry - market not bearish")

        # After observation - check for IV spike on bearish days
        elif self.observation_complete and self.is_bearish:
            analysis['direction'] = 'bearish'

            # Calculate IV metrics
            iv_metrics = self._calculate_iv_metrics(options_data, current_time)
            analysis.update(iv_metrics)

            # Periodic monitoring log
            should_log = False
            if self.last_monitoring_log_time is None:
                should_log = True
            else:
                minutes_since_last_log = (
                    current_time - self.last_monitoring_log_time
                ).total_seconds() / 60
                if minutes_since_last_log >= self.monitoring_log_interval:
                    should_log = True

            if should_log:
                print(f"  📍 {current_time.strftime('%H:%M')} - Monitoring IV")
                print(f"     Current Price: ${current_price:.2f}")
                if iv_metrics['current_iv'] is not None:
                    print(f"     Current IV: {iv_metrics['current_iv']:.2%}")
                if iv_metrics['recent_avg_iv'] is not None:
                    print(f"     Recent Avg IV: {iv_metrics['recent_avg_iv']:.2%}")
                    print(f"     IV Change: {iv_metrics['iv_change_pct']:+.2%}")
                self.last_monitoring_log_time = current_time

            # Entry signal if IV spike detected
            if iv_metrics['iv_spike']:
                analysis['entry_signal'] = True

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
        1. Observation period complete
        2. Market is bearish
        3. IV spike detected
        4. No active position
        5. Haven't exceeded daily trade limit
        6. Sufficient options liquidity
        """
        # Don't enter if active position
        if self.active_position is not None:
            return False

        # Don't enter if exceeded daily limit
        if not self.can_enter_new_position():
            return False

        # Must complete observation
        if not market_analysis.get('observation_complete', False):
            return False

        # Must be bearish
        if market_analysis.get('direction') != 'bearish':
            return False

        # Must have IV spike
        if not market_analysis.get('iv_spike', False):
            return False

        # Check options data availability
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

        current_price = market_analysis.get('current_price', 0)
        current_iv = market_analysis.get('current_iv')
        iv_change = market_analysis.get('iv_change_pct', 0)

        print(f"\n  🎯 IV SPIKE SIGNAL - BEARISH ENTRY!")
        print(f"     Current Price: ${current_price:.2f}")
        if current_iv is not None:
            print(f"     Current IV: {current_iv:.2%}")
            print(f"     IV Change: {iv_change:+.2%}")
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
        Construct a bearish vertical call spread.

        Spread structure:
        - Sell 1 call at lower strike (closer to ATM)
        - Buy 1 call at higher strike (further OTM, for protection)

        This is a CREDIT spread - we receive premium on entry.
        """
        current_price = market_analysis.get('current_price', 0)

        if current_price == 0:
            return None

        # Filter for 0DTE options only
        # Expiration is today
        today = pd.Timestamp(current_time.date()).tz_localize(None)

        # Filter for CALL options expiring today
        # contract_type is 'call' (lowercase enum value)
        valid_options = options_data[
            (options_data['expiration_date'] == today) &
            (options_data['contract_type'] == 'call')
        ]

        if valid_options.empty:
            print(f"  ⚠️  No 0DTE call options found for {today}")
            return None

        # Apply liquidity filters
        liquid_options = valid_options[valid_options['volume'] >= self.min_volume]

        if liquid_options.empty:
            print(f"  ⚠️  No options with volume >= {self.min_volume}")
            return None

        # Bid/ask spread filter
        if 'bid' in liquid_options.columns and 'ask' in liquid_options.columns:
            liquid_options = liquid_options.copy()
            liquid_options['bid_ask_spread_pct'] = (
                (liquid_options['ask'] - liquid_options['bid']) /
                liquid_options['mark'] * 100
            )

            liquid_options = liquid_options[
                liquid_options['bid_ask_spread_pct'] <= self.min_bid_ask_spread_pct
            ]

            if liquid_options.empty:
                print(f"  ⚠️  No options with bid/ask spread <= {self.min_bid_ask_spread_pct}%")
                return None

        valid_options = liquid_options

        # Find strike for short call (lower strike, closer to ATM)
        # Look for strike just above current price (slightly OTM)
        short_strike_candidates = valid_options[
            valid_options['strike_price'] >= current_price
        ].sort_values('strike_price', ascending=True)

        if short_strike_candidates.empty:
            print(f"  ⚠️  No call strikes above current price ${current_price:.2f}")
            return None

        short_strike = short_strike_candidates.iloc[0]['strike_price']
        long_strike = short_strike + self.spread_width

        # Find the contracts
        short_call = valid_options[
            valid_options['strike_price'] == short_strike
        ]

        long_call = valid_options[
            valid_options['strike_price'] == long_strike
        ]

        if short_call.empty or long_call.empty:
            print(f"  ⚠️  Could not find both legs of spread")
            print(f"     Short {short_strike} CALL: {'found' if not short_call.empty else 'MISSING'}")
            print(f"     Long {long_strike} CALL: {'found' if not long_call.empty else 'MISSING'}")
            return None

        # Get prices
        short_call_data = short_call.iloc[0]
        long_call_data = long_call.iloc[0]

        # Validate prices
        if (pd.isna(short_call_data['mark']) or
            pd.isna(long_call_data['mark']) or
            short_call_data['mark'] <= 0 or
            long_call_data['mark'] <= 0):
            print(f"  ⚠️  Invalid mark prices for selected strikes")
            return None

        # Log selected contracts
        print(f"\n  📋 Selected 0DTE Contracts:")
        print(f"     Short {short_strike} CALL:")
        print(f"       Volume: {short_call_data['volume']:.0f}")
        if 'bid' in short_call_data and 'ask' in short_call_data:
            spread_pct = (
                (short_call_data['ask'] - short_call_data['bid']) /
                short_call_data['mark'] * 100
            )
            print(f"       Bid/Ask: ${short_call_data['bid']:.2f}/${short_call_data['ask']:.2f} "
                  f"(spread: {spread_pct:.2f}%)")
        print(f"       Mark: ${short_call_data['mark']:.2f}")
        if 'implied_volatility' in short_call_data:
            print(f"       IV: {short_call_data['implied_volatility']:.2%}")

        print(f"     Long {long_strike} CALL:")
        print(f"       Volume: {long_call_data['volume']:.0f}")
        if 'bid' in long_call_data and 'ask' in long_call_data:
            spread_pct = (
                (long_call_data['ask'] - long_call_data['bid']) /
                long_call_data['mark'] * 100
            )
            print(f"       Bid/Ask: ${long_call_data['bid']:.2f}/${long_call_data['ask']:.2f} "
                  f"(spread: {spread_pct:.2f}%)")
        print(f"       Mark: ${long_call_data['mark']:.2f}")
        if 'implied_volatility' in long_call_data:
            print(f"       IV: {long_call_data['implied_volatility']:.2%}")

        # Validate data completeness
        contract_symbols = [
            short_call_data['contract_symbol'],
            long_call_data['contract_symbol']
        ]

        data_for_validation = full_options_data if full_options_data is not None else options_data

        is_valid, completeness = self.validate_data_completeness(
            contract_symbols=contract_symbols,
            options_data=data_for_validation,
            current_time=current_time,
            lookback_minutes=30,  # Shorter lookback for 0DTE
            min_completeness_pct=80.0  # Lower threshold for 0DTE
        )

        print(f"\n  📊 Data Completeness Check:")
        for symbol, pct in completeness.items():
            strike = short_strike if symbol == short_call_data['contract_symbol'] else long_strike
            status = "✅" if pct >= 80.0 else "❌"
            print(f"     {status} {strike} CALL: {pct:.1f}% coverage")

        if not is_valid:
            print(f"  ⚠️  Skipping trade - insufficient data completeness (need ≥80% for 0DTE)")
            return None

        # Calculate net credit
        short_call_price = short_call_data['mark']
        long_call_price = long_call_data['mark']
        net_credit_per_spread = (short_call_price - long_call_price) * 100
        net_credit = net_credit_per_spread * self.num_spreads

        # Max risk
        max_risk = self.spread_width * 100 * self.num_spreads

        print(f"\n  💰 Spread Economics:")
        print(f"     Net Credit: ${net_credit:,.2f}")
        print(f"     Max Risk: ${max_risk:,.2f}")
        print(f"     Return on Risk: {(net_credit / max_risk * 100):.2f}%")

        # Create legs
        legs = [
            OptionLeg(
                contract_symbol=short_call_data['contract_symbol'],
                option_type=OptionType.CALL,
                strike_price=short_strike,
                expiration_date=today,
                quantity=-self.num_spreads,  # Short (sell)
                entry_price=short_call_price
            ),
            OptionLeg(
                contract_symbol=long_call_data['contract_symbol'],
                option_type=OptionType.CALL,
                strike_price=long_strike,
                expiration_date=today,
                quantity=self.num_spreads,  # Long (buy)
                entry_price=long_call_price
            )
        ]

        # Create position
        position = OptionsPosition(
            position_id=generate_position_id("BIVS", current_time),
            spread_type=SpreadType.VERTICAL_CALL,
            legs=legs,
            entry_time=current_time,
            entry_cost=-net_credit,  # Negative (credit received)
            underlying_price_at_entry=current_price,
            profit_target=self.profit_target_max,
            trailing_stop=self.trailing_stop_pct,
            stop_loss=self.stop_loss_pct
        )

        # Increment trade counter
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
        1. Profit target reached (30-50%)
        2. Tight trailing stop (3%)
        3. Stop loss hit (75% of max risk)
        4. End of day (3:45 PM ET for 0DTE)
        """
        # Get underlying price
        underlying_price = underlying_data['close'].iloc[-1] if not underlying_data.empty else None

        # Update position value
        self.update_position_value(position, options_data, underlying_price)

        # Check profit target
        if self.check_profit_target(position):
            return True, "Profit target reached"

        # Check trailing stop
        if self.check_trailing_stop(position):
            return True, "Trailing stop triggered"

        # Check stop loss
        if self.check_stop_loss(position):
            return True, "Stop loss hit"

        # 0DTE management - close before end of day
        import pytz
        et_tz = pytz.timezone('America/New_York')
        if current_time.tzinfo is None:
            current_time_et = pytz.UTC.localize(current_time).astimezone(et_tz)
        else:
            current_time_et = current_time.astimezone(et_tz)

        # Close at 3:45 PM ET (15 mins before close)
        if current_time_et.hour >= 15 and current_time_et.minute >= 45:
            return True, "0DTE - end of day approaching"

        return False, None
