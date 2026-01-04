"""ThrockmortenMD Reddit Credit Spread Laddering Strategy for SPX.

Based on the strategy from u/ThrockmortenMD on Reddit.

Strategy Overview:
- Wait 60 minutes after market open (until 10:30 ET)
- Calculate ATM straddle price to define 1SD and 2SD zones
- Place GTC limit orders to sell 50-wide spreads at 2SD for credit of spread at 1SD
- Deploy additional spreads as ladder gets touched (scaling out)
- Use spread width as hard stop (no manual exits)
- Exit immediately on major catalysts (tariffs, war, etc.)
"""

from typing import Optional, Dict, Tuple, List
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


class ThrockmortonCreditLadderStrategy(OptionsStrategy):
    """
    ThrockmortenMD Credit Spread Laddering Strategy.

    Strategy Logic:
    1. Wait 60 minutes after market open (until 10:30 ET)
    2. Calculate ATM straddle price at 10:30 ET to estimate 1SD and 2SD
    3. Place limit orders to sell 50-wide spreads at 2SD strike
    4. Order price: current credit of same spread at 1SD strike
    5. When 2SD is touched, immediately sell another spread 1SD further out
    6. Use spread width as hard stop - no manual exits
    7. Exit all positions immediately on major catalyst events

    Risk Management:
    - Spread width defines max risk per contract
    - No manual stop losses - trust the math
    - Catalyst-based emergency exits only

    Entry Criteria:
    - Time is >= 10:30 ET (60 min wait period complete)
    - No major economic catalysts scheduled for the day
    - Sufficient options liquidity at target strikes
    - 2SD zone has been touched by price

    Exit Criteria:
    - Natural profit target (spread expires worthless or reaches profit target)
    - Emergency catalyst event detected
    - End of trading day
    - Expiration approaching
    """

    def __init__(
        self,
        spread_width: float = 50.0,  # Width of vertical spread
        wait_period_minutes: int = 60,  # Wait 60 mins after open (until 10:30 ET)
        initial_ladder_count: int = 1,  # Number of spreads to place initially
        ladder_increment: int = 1,  # Additional spreads per touch
        max_ladders: int = 5,  # Maximum total ladder positions
        profit_target_pct: float = 0.7,  # 70% profit target
        min_dte: int = 0,  # Same day expiration allowed
        max_dte: int = 7,  # Up to 1 week out
        num_spreads: int = 1,  # Contracts per ladder
        min_volume: int = 50,
        max_trades_daily: int = 1,  # From BaseStrategyParams
        **kwargs
    ) -> None:
        """
        Initialize ThrockmortenMD Credit Ladder Strategy.

        Args:
            spread_width: Width of vertical spread in dollars (default: $50)
            wait_period_minutes: Minutes to wait after open (default: 60 for 10:30 ET)
            initial_ladder_count: Initial spreads to place (default: 1)
            ladder_increment: Additional spreads per touch (default: 1)
            max_ladders: Maximum ladder positions (default: 5)
            profit_target_pct: Profit target percentage (default: 0.7 = 70%)
            min_dte: Minimum days to expiration (default: 0)
            max_dte: Maximum days to expiration (default: 7)
            num_spreads: Number of contracts per ladder (default: 1)
            min_volume: Minimum option volume for liquidity (default: 50)
            max_trades_daily: From base params, use max_ladders as the effective limit
            **kwargs: Additional parameters passed to OptionsStrategy
        """
        # Use max_ladders as the effective max_trades_daily
        super().__init__(
            name=f"ThrockmortonCreditLadder_{spread_width}",
            max_trades_daily=max_ladders,  # Can add up to max_ladders per day
            observation_period=wait_period_minutes,
            min_dte=min_dte,
            max_dte=max_dte,
            num_spreads=num_spreads,
            min_volume=min_volume,
            profit_target_pct=profit_target_pct,
            **kwargs
        )

        # Strategy-specific parameters
        self.spread_width = spread_width
        self.wait_period_minutes = wait_period_minutes
        self.initial_ladder_count = initial_ladder_count
        self.ladder_increment = ladder_increment
        self.max_ladders = max_ladders

        # State tracking
        self.market_open_time: Optional[datetime] = None
        self.observation_complete: bool = False
        self.atm_straddle_price: Optional[float] = None
        self.one_sd_price: Optional[float] = None  # ATM straddle price (approximates 1SD)
        self.two_sd_price: Optional[float] = None  # 2x ATM straddle (approximates 2SD)
        self.one_sd_strike_high: Optional[float] = None  # Upper 1SD strike
        self.one_sd_strike_low: Optional[float] = None   # Lower 1SD strike
        self.two_sd_strike_high: Optional[float] = None  # Upper 2SD strike
        self.two_sd_strike_low: Optional[float] = None   # Lower 2SD strike
        self.reference_price: Optional[float] = None  # Price at 10:30 ET
        self.current_day: Optional[datetime] = None
        self.ladder_count: int = 0  # Track how many ladders deployed
        self.two_sd_touched: bool = False  # Track if 2SD has been touched
        self.catalyst_detected: bool = False  # Emergency exit flag

    def reset_daily_state(self):
        """Reset state for a new trading day."""
        super().reset_daily_state()
        self.market_open_time = None
        self.observation_complete = False
        self.atm_straddle_price = None
        self.one_sd_price = None
        self.two_sd_price = None
        self.one_sd_strike_high = None
        self.one_sd_strike_low = None
        self.two_sd_strike_high = None
        self.two_sd_strike_low = None
        self.reference_price = None
        self.ladder_count = 0
        self.two_sd_touched = False
        self.catalyst_detected = False

    def calculate_zones(
        self,
        current_price: float,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Dict:
        """
        Calculate 1SD and 2SD zones using ATM straddle price.

        The ATM straddle price (call + put at same strike) approximates
        the 1 standard deviation move. We use this to define zones:
        - 1SD = current_price ± atm_straddle_price
        - 2SD = current_price ± (2 * atm_straddle_price)

        Args:
            current_price: Current underlying price
            options_data: Options chain data
            current_time: Current timestamp

        Returns:
            Dict with zone calculations
        """
        zones = {
            'atm_straddle_price': None,
            'one_sd_high': None,
            'one_sd_low': None,
            'two_sd_high': None,
            'two_sd_low': None,
            'reference_price': current_price
        }

        # Filter options by DTE
        dte_filtered = self._filter_by_dte(
            options_data=options_data,
            current_time=current_time,
            min_dte=self.min_dte,
            max_dte=self.max_dte
        )

        if dte_filtered.empty:
            return zones

        # Get nearest expiration
        nearest_expiration = dte_filtered['expiration_date'].min()
        expiration_options = dte_filtered[
            dte_filtered['expiration_date'] == nearest_expiration
        ]

        # Find ATM strike (closest to current price)
        expiration_options['strike_distance'] = abs(
            expiration_options['strike_price'] - current_price
        )
        atm_strike = expiration_options.loc[
            expiration_options['strike_distance'].idxmin(),
            'strike_price'
        ]

        # Get ATM call and put prices
        atm_call = expiration_options[
            (expiration_options['strike_price'] == atm_strike) &
            (expiration_options['contract_type'] == 'call')
        ]
        atm_put = expiration_options[
            (expiration_options['strike_price'] == atm_strike) &
            (expiration_options['contract_type'] == 'put')
        ]

        if atm_call.empty or atm_put.empty:
            return zones

        # Calculate ATM straddle price (sum of call + put)
        call_price = atm_call.iloc[0]['mark']
        put_price = atm_put.iloc[0]['mark']

        if pd.isna(call_price) or pd.isna(put_price):
            return zones

        atm_straddle = float(call_price + put_price)

        # Calculate zones
        zones['atm_straddle_price'] = atm_straddle
        zones['one_sd_high'] = current_price + atm_straddle
        zones['one_sd_low'] = current_price - atm_straddle
        zones['two_sd_high'] = current_price + (2 * atm_straddle)
        zones['two_sd_low'] = current_price - (2 * atm_straddle)

        return zones

    def analyze_market(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Dict:
        """
        Analyze market conditions and calculate zones.

        Returns:
            Dict with market analysis including:
            - zones_calculated: bool
            - current_price: float
            - two_sd_touched: bool
            - direction: 'call' or 'put' (which side to trade)
        """
        analysis = {
            'zones_calculated': False,
            'current_price': 0.0,
            'two_sd_touched': False,
            'direction': None,
            'observation_complete': self.observation_complete
        }

        if underlying_data.empty:
            return analysis

        current_price = underlying_data['close'].iloc[-1]
        analysis['current_price'] = current_price

        # Check if new trading day
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

        # Wait period: calculate zones at 10:30 ET (60 mins after open)
        if time_since_open >= self.wait_period_minutes and not self.observation_complete:
            # Calculate zones once at 10:30 ET
            zones = self.calculate_zones(current_price, options_data, current_time)

            if zones['atm_straddle_price'] is not None:
                self.atm_straddle_price = zones['atm_straddle_price']
                self.one_sd_price = zones['atm_straddle_price']
                self.two_sd_price = 2 * zones['atm_straddle_price']
                self.one_sd_strike_high = zones['one_sd_high']
                self.one_sd_strike_low = zones['one_sd_low']
                self.two_sd_strike_high = zones['two_sd_high']
                self.two_sd_strike_low = zones['two_sd_low']
                self.reference_price = current_price
                self.observation_complete = True
                analysis['zones_calculated'] = True

                print(f"\n  📊 ZONES CALCULATED at 10:30 ET")
                print(f"     Reference Price: ${self.reference_price:.2f}")
                print(f"     ATM Straddle: ${self.atm_straddle_price:.2f}")
                print(f"     1SD Range: ${self.one_sd_strike_low:.2f} - ${self.one_sd_strike_high:.2f}")
                print(f"     2SD Range: ${self.two_sd_strike_low:.2f} - ${self.two_sd_strike_high:.2f}")

        # After observation, check if 2SD has been touched
        if self.observation_complete:
            analysis['zones_calculated'] = True

            # Check if price has moved to 2SD zone (either direction)
            if current_price >= self.two_sd_strike_high:
                analysis['two_sd_touched'] = True
                analysis['direction'] = 'put'  # Price moved up, sell put spreads
                if not self.two_sd_touched:
                    print(f"\n  🎯 2SD TOUCHED (UPSIDE)")
                    print(f"     Current: ${current_price:.2f} >= ${self.two_sd_strike_high:.2f}")
                    self.two_sd_touched = True

            elif current_price <= self.two_sd_strike_low:
                analysis['two_sd_touched'] = True
                analysis['direction'] = 'call'  # Price moved down, sell call spreads
                if not self.two_sd_touched:
                    print(f"\n  🎯 2SD TOUCHED (DOWNSIDE)")
                    print(f"     Current: ${current_price:.2f} <= ${self.two_sd_strike_low:.2f}")
                    self.two_sd_touched = True

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
        1. Observation period complete (zones calculated at 10:30 ET)
        2. 2SD zone has been touched
        3. Haven't exceeded max ladder count
        4. Sufficient options liquidity
        """
        # Check if observation complete
        if not market_analysis.get('observation_complete', False):
            return False

        # Check if zones calculated
        if not market_analysis.get('zones_calculated', False):
            return False

        # Check if 2SD touched
        if not market_analysis.get('two_sd_touched', False):
            return False

        # Check ladder limit
        if self.ladder_count >= self.max_ladders:
            return False

        # Check options data available
        if options_data.empty:
            return False

        # All conditions met
        direction = market_analysis.get('direction')
        current_price = market_analysis.get('current_price')

        print(f"\n  🚀 LADDER ENTRY SIGNAL!")
        print(f"     Direction: {direction.upper()} spreads")
        print(f"     Current Price: ${current_price:.2f}")
        print(f"     Ladder Count: {self.ladder_count + 1}/{self.max_ladders}")

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
        Construct a credit spread at the 2SD strike.

        For upside 2SD touch: Sell put spreads below current price
        For downside 2SD touch: Sell call spreads above current price

        Args:
            underlying_data: OHLCV data
            options_data: Options chain data
            current_time: Current timestamp
            market_analysis: Market analysis dict
            full_options_data: Full options dataset for validation

        Returns:
            OptionsPosition or None
        """
        current_price = market_analysis.get('current_price', 0)
        direction = market_analysis.get('direction')

        if current_price == 0 or direction is None:
            return None

        # Filter by DTE
        dte_filtered = self._filter_by_dte(
            options_data=options_data,
            current_time=current_time,
            min_dte=self.min_dte,
            max_dte=self.max_dte
        )

        # Filter by option type based on direction
        option_type = 'put' if direction == 'put' else 'call'
        valid_options = dte_filtered[dte_filtered['contract_type'] == option_type]

        if valid_options.empty:
            print(f"  ⚠️  No {option_type} options found in DTE range")
            return None

        # Apply liquidity filters
        liquid_options = self._filter_by_liquidity(
            options_data=valid_options,
            min_volume=self.min_volume,
            max_bid_ask_spread_pct=10.0
        )

        if liquid_options.empty:
            print(f"  ⚠️  No liquid {option_type} options found")
            return None

        # Get nearest expiration
        nearest_expiration = liquid_options['expiration_date'].min()
        expiration_options = liquid_options[
            liquid_options['expiration_date'] == nearest_expiration
        ]

        # Determine strikes based on direction
        if direction == 'put':
            # Sell put spread below current price (at 2SD)
            # Short strike: at or below 2SD low
            # Long strike: short_strike - spread_width
            short_strike_candidates = expiration_options[
                expiration_options['strike_price'] <= self.two_sd_strike_low
            ].sort_values('strike_price', ascending=False)

            if short_strike_candidates.empty:
                return None

            short_strike = short_strike_candidates.iloc[0]['strike_price']
            long_strike = short_strike - self.spread_width

        else:  # direction == 'call'
            # Sell call spread above current price (at 2SD)
            # Short strike: at or above 2SD high
            # Long strike: short_strike + spread_width
            short_strike_candidates = expiration_options[
                expiration_options['strike_price'] >= self.two_sd_strike_high
            ].sort_values('strike_price', ascending=True)

            if short_strike_candidates.empty:
                return None

            short_strike = short_strike_candidates.iloc[0]['strike_price']
            long_strike = short_strike + self.spread_width

        # Find contracts
        short_option = expiration_options[
            expiration_options['strike_price'] == short_strike
        ]
        long_option = expiration_options[
            expiration_options['strike_price'] == long_strike
        ]

        if short_option.empty or long_option.empty:
            return None

        # Get prices
        short_data = short_option.iloc[0]
        long_data = long_option.iloc[0]

        if (pd.isna(short_data['mark']) or pd.isna(long_data['mark']) or
            short_data['mark'] <= 0 or long_data['mark'] <= 0):
            print(f"  ⚠️  Invalid mark prices for selected strikes")
            return None

        # Calculate net credit
        short_price = float(short_data['mark'])
        long_price = float(long_data['mark'])
        net_credit_per_spread = (short_price - long_price) * 100
        net_credit = net_credit_per_spread * self.num_spreads

        # Max risk
        max_risk = self.spread_width * 100 * self.num_spreads

        # Create legs
        if direction == 'put':
            legs = [
                OptionLeg(
                    contract_symbol=short_data['contract_symbol'],
                    option_type=OptionType.PUT,
                    strike_price=float(short_strike),
                    expiration_date=nearest_expiration,
                    quantity=-self.num_spreads,
                    entry_price=short_price
                ),
                OptionLeg(
                    contract_symbol=long_data['contract_symbol'],
                    option_type=OptionType.PUT,
                    strike_price=float(long_strike),
                    expiration_date=nearest_expiration,
                    quantity=self.num_spreads,
                    entry_price=long_price
                )
            ]
            spread_type = SpreadType.VERTICAL_PUT
        else:
            legs = [
                OptionLeg(
                    contract_symbol=short_data['contract_symbol'],
                    option_type=OptionType.CALL,
                    strike_price=float(short_strike),
                    expiration_date=nearest_expiration,
                    quantity=-self.num_spreads,
                    entry_price=short_price
                ),
                OptionLeg(
                    contract_symbol=long_data['contract_symbol'],
                    option_type=OptionType.CALL,
                    strike_price=float(long_strike),
                    expiration_date=nearest_expiration,
                    quantity=self.num_spreads,
                    entry_price=long_price
                )
            ]
            spread_type = SpreadType.VERTICAL_CALL

        # Create position
        position = OptionsPosition(
            position_id=generate_position_id("TCL", current_time),
            spread_type=spread_type,
            legs=legs,
            entry_time=current_time,
            entry_cost=-net_credit,  # Negative for credit received
            underlying_price_at_entry=current_price,
            profit_target_pct=self.profit_target_pct,
            trailing_stop=None  # No trailing stop per strategy rules
        )

        # Increment ladder count
        self.ladder_count += 1

        print(f"\n  ✅ LADDER #{self.ladder_count} DEPLOYED")
        print(f"     Type: {direction.upper()} spread")
        print(f"     Strikes: ${short_strike:.2f} / ${long_strike:.2f}")
        print(f"     Credit: ${net_credit:.2f}")
        print(f"     Max Risk: ${max_risk:.2f}")

        return position

    def should_exit(
        self,
        position: OptionsPosition,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine if we should exit position.

        Exit conditions:
        1. Catalyst detected (emergency exit)
        2. Profit target reached
        3. End of trading day
        4. Expiration approaching

        Note: No trailing stop per strategy rules.
        """
        # Check for catalyst emergency exit
        if self.catalyst_detected:
            return True, "Emergency catalyst exit"

        # Get current underlying price
        underlying_price = underlying_data['close'].iloc[-1] if not underlying_data.empty else None

        # Update position value
        self.update_position_value(position, options_data, underlying_price)

        # Check profit target
        if self.check_profit_target(position):
            return True, "Profit target reached"

        # Check end of day
        import pytz
        et_tz = pytz.timezone('America/New_York')
        if current_time.tzinfo is None:
            current_time_et = pytz.UTC.localize(current_time).astimezone(et_tz)
        else:
            current_time_et = current_time.astimezone(et_tz)

        if current_time_et.hour >= 16:
            return True, "End of trading day"

        # Check expiration approaching
        if position.legs:
            expiration = position.legs[0].expiration_date
            days_to_expiration = (expiration - current_time_et.date()).days

            if days_to_expiration == 0 and current_time_et.hour >= 15 and current_time_et.minute >= 45:
                return True, "Expiration approaching"

            if days_to_expiration < 0:
                return True, "Expiration passed"

        return False, None

    def detect_catalyst(self, news_data: Optional[Dict] = None) -> bool:
        """
        Detect major catalyst events that require emergency exit.

        This is a placeholder for catalyst detection logic.
        In production, this would integrate with news APIs or
        economic calendar data.

        Args:
            news_data: Optional news/calendar data

        Returns:
            True if catalyst detected
        """
        # Placeholder: Would check for:
        # - CPI releases
        # - FOMC meetings
        # - Tariff announcements
        # - War/geopolitical events
        # - Other major market-moving events

        return False
