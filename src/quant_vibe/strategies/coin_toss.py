"""
Coin Toss Strategy - A naive strategy that randomly picks direction.

This strategy:
1. Randomly picks bullish (call) or bearish (put) direction
2. Looks for options priced near target price (e.g., $2.00 ± $0.50)
3. Buys the closest option at ask price (market order simulation)
4. Exits when sell target is reached or at end of day
5. Maximum trades per day limit enforced
"""

import random
from datetime import datetime, time
from typing import Dict, Optional, Any

import pandas as pd
import pytz

from quant_vibe.strategies.options_base import (
    OptionLeg,
    OptionsPosition,
    OptionsStrategy,
    OptionType,
    SpreadType,
)
from quant_vibe.utils import generate_position_id
from quant_vibe.utils.pnl_utils import PnLCalculator
from quant_vibe.logging import get_logger

logger = get_logger(__name__)


class CoinTossStrategy(OptionsStrategy):
    """
    Extremely naive strategy that randomly picks direction and trades options.

    Strategy Logic:
    - Randomly choose call or put (coin toss)
    - Find options with ask price near target price (within tolerance)
    - Buy at ask price (market order simulation)
    - Exit when sell target reached or at end of day
    - Max trades per day limit enforced

    This is purely for educational/experimental purposes and not a viable trading strategy.
    """

    def __init__(
        self,
        target_price: float = 2.0,
        buy_limit: float = 1.0,
        sell_target: float = 2.0,
        price_tolerance: float = 0.50,  # How far from target_price to search
        max_trades_daily: int = 5,
        quantity: int = 10,
        min_dte: int = 0,
        max_dte: int = 45,
        profit_target_pct: float = 1.0,  # 100% profit (buy at 1, sell at 2)
        stop_loss_pct: Optional[float] = None,
        observation_period: Optional[int] = None,  # Accepted for compatibility, not used
        **kwargs  # Accept any additional parameters from optimizer
    ):
        """
        Initialize CoinTossStrategy.

        Args:
            target_price: Target option price to search near ($2.00 default)
            buy_limit: Reference price - not used for filtering (kept for compatibility)
            sell_target: Target price for exit signal ($2.00 default)
            price_tolerance: Search range around target_price (±$0.50 default)
            max_trades_daily: Maximum number of trades per day (5 default)
            quantity: Number of contracts to trade (10 default)
            min_dte: Minimum days to expiration (0 default)
            max_dte: Maximum days to expiration (45 default)
            profit_target_pct: Profit target as percentage (1.0 = 100%)
            stop_loss_pct: Stop loss as percentage (None = no stop loss)
            observation_period: Observation period in minutes (accepted for compatibility, not used by this strategy)
            **kwargs: Additional parameters (silently ignored)
        """
        super().__init__(
            name="CoinToss",
            max_trades_daily=max_trades_daily,
            observation_period=observation_period,
            quantity=quantity,
            min_dte=min_dte,
            max_dte=max_dte,
            profit_target_pct=profit_target_pct,
            stop_loss_pct=stop_loss_pct,
            **kwargs,
        )

        # Strategy-specific parameters (not in base class)
        self.target_price = target_price
        self.buy_limit = buy_limit
        self.sell_target = sell_target
        self.price_tolerance = price_tolerance

        # Track current day for reset detection
        self.current_day: Optional[datetime] = None

        # Random seed for reproducibility in backtesting
        random.seed(42)

    def analyze_market(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
    ) -> Dict[str, Any]:
        """
        Analyze market - in this case, just flip a coin for direction.

        Returns:
            Dict with 'direction' (call/put) and 'signal' (bool)
        """
        # Reset daily counter if new day
        if self.current_day is None or self.current_day.date() != current_time.date():
            self.current_day = current_time
            self.trades_today = 0

        # Check if we've hit max trades today
        if self.trades_today >= self.max_trades_daily:
            return {"direction": None, "signal": False, "reason": "Max trades today"}

        # Flip a coin: heads = call, tails = put
        coin_flip = random.choice(["call", "put"])

        return {
            "direction": coin_flip,
            "signal": True,
            "trades_today": self.trades_today,
        }

    def should_enter(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        market_analysis: Dict[str, Any],
    ) -> bool:
        """
        Check if we should enter a position.

        Returns:
            True if we should enter (have signal and no active position)
        """
        # Don't enter if we already have a position
        if self.active_position is not None:
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
        Construct a single-leg position (buy call or put).

        Args:
            underlying_data: OHLCV data for underlying
            options_data: Filtered options data for current time
            current_time: Current timestamp
            market_analysis: Market analysis from analyze_market()
            full_options_data: Complete options dataset (optional, for advanced filtering)

        Returns:
            OptionsPosition with one leg, or None if no suitable option found
        """
        direction = market_analysis.get("direction")
        if direction not in ["call", "put"]:
            return None

        option_type = OptionType.CALL if direction == "call" else OptionType.PUT

        # Early return if no data
        if options_data.empty:
            logger.info("[CoinToss] No options data available")
            return None

        # Check for required columns
        if 'contract_type' not in options_data.columns:
            logger.info("[CoinToss] ERROR: 'contract_type' column missing from options data")
            return None

        if 'expiration_date' not in options_data.columns:
            logger.info("[CoinToss] ERROR: 'expiration_date' column missing from options data")
            return None

        # Filter by contract type first
        options_by_type = options_data[options_data["contract_type"] == direction].copy()

        # Filter by DTE using base class helper (handles date type conversion)
        options_filtered = self._filter_by_dte(
            options_by_type,
            current_time,
            self.min_dte,
            self.max_dte
        )

        if options_filtered.empty:
            logger.info(f"[CoinToss] No {direction} options found in DTE range {self.min_dte}-{self.max_dte} days")
            return None

        # Find options with ask price near target_price
        # We want to buy options around the target price range
        price_min = self.target_price - self.price_tolerance
        price_max = self.target_price + self.price_tolerance

        options_filtered = options_filtered[
            (options_filtered["ask"] >= price_min)
            & (options_filtered["ask"] <= price_max)
        ].copy()

        if options_filtered.empty:
            logger.info(f"[CoinToss] No {direction} options found in price range ${price_min:.2f}-${price_max:.2f} (target: ${self.target_price:.2f} ± ${self.price_tolerance:.2f})")
            return None

        # Sort by how close to target price and pick the closest one
        options_filtered["price_diff"] = abs(
            options_filtered["ask"] - self.target_price
        )
        options_filtered = options_filtered.sort_values("price_diff")

        # Pick the closest one to target price
        selected = options_filtered.iloc[0]

        # Create position ID with timestamp to ensure uniqueness
        position_id = generate_position_id(
            strategy_prefix="COIN",
            current_time=current_time,
            counter=self.trades_today + 1
        )

        # Use the ask price as entry price
        # This is a "naive" strategy - we just buy at market (ask price)
        entry_price = selected["ask"]

        leg = OptionLeg(
            option_ticker=selected["option_ticker"],
            option_type=option_type,
            strike_price=selected["strike_price"],
            expiration_date=selected["expiration_date"],
            quantity=self.quantity,
            entry_price=entry_price,
        )

        # Get current underlying price
        if not underlying_data.empty:
            current_underlying = underlying_data.iloc[-1]["close"]
        else:
            current_underlying = 0.0

        # Entry cost is the debit paid (positive for long positions)
        # Include 100x multiplier to match how current_value is calculated
        entry_cost = entry_price * self.quantity * 100

        position = OptionsPosition(
            position_id=position_id,
            spread_type=SpreadType.SINGLE,
            legs=[leg],
            entry_time=current_time,
            entry_cost=entry_cost,
            underlying_price_at_entry=current_underlying,
            profit_target_pct=self.profit_target_pct,
            stop_loss=self.stop_loss_pct,
        )

        # Increment trades counter
        self.trades_today += 1

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
        1. Profit target reached (based on profit_target_pct from position)
        2. End of day (4 PM ET)
        3. Expiration day

        Note: Absolute stop loss is automatically checked by base class.

        Returns:
            (should_exit, exit_reason)
        """
        # Get current underlying price for intrinsic value calculation
        underlying_price = underlying_data['close'].iloc[-1] if not underlying_data.empty else None

        # Update position value (with underlying price for fallback intrinsic value)
        self.update_position_value(position, options_data, underlying_price)

        # Validate position value - skip exit check if data is invalid
        if position.current_value is None or pd.isna(position.current_value):
            return False, None

        # Skip profit/loss checks if we don't have valid market data (using fallback pricing)
        # This prevents false stop loss triggers due to missing/estimated data
        if not position.has_valid_market_data:
            return False, None

        # Calculate current P&L using centralized calculator
        pnl_result = PnLCalculator.calculate_unrealized_pnl(
            position.entry_cost,
            position.current_value
        )
        pnl = pnl_result.pnl
        pnl_pct = pnl_result.pnl_pct / 100 if pnl_result.pnl_pct is not None else 0

        # Validate pnl_pct - skip if NaN
        if pd.isna(pnl_pct):
            return False, None

        mark_price = position.current_value / (abs(position.legs[0].quantity) * 100)

        # Check profit target (from position.profit_target)
        if pnl_pct >= position.profit_target_pct:
            # Override position value to use bid price (what we'd actually get when selling)
            # This prevents P&L distortion from wide bid/ask spreads
            leg = position.legs[0]
            leg_data = options_data[options_data['option_ticker'] == leg.option_ticker]
            if not leg_data.empty:
                bid_price = leg_data.iloc[0]['bid']
                if not pd.isna(bid_price) and bid_price > 0:
                    # Use correct sign convention: long position selling = positive value
                    position.current_value = bid_price * abs(leg.quantity) * 100
                    position.legs[0].current_price = bid_price

            # Calculate final P&L with actual bid price (do this AFTER the override)
            pnl_result = PnLCalculator.calculate_unrealized_pnl(
                position.entry_cost,
                position.current_value
            )
            pnl = pnl_result.pnl
            pnl_pct = pnl_result.pnl_pct / 100 if pnl_result.pnl_pct is not None else 0

            return True, f"Profit target ({position.profit_target_pct*100:.0f}%) reached - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        # Note: Stop loss check removed - now handled by base class automatically

        # Exit at end of day (4 PM ET) or if it's expiration day
        # Options expire at 4 PM on expiration date
        # Convert current_time to Eastern Time for proper comparison
        eastern = pytz.timezone('US/Eastern')
        current_time_et = current_time.astimezone(eastern)
        exit_time = time(16, 0)
        leg = position.legs[0]

        if current_time_et.time() >= exit_time:
            # Use bid price for exit value
            leg_data = options_data[options_data['option_ticker'] == leg.option_ticker]
            if not leg_data.empty:
                bid_price = leg_data.iloc[0]['bid']
                if not pd.isna(bid_price) and bid_price > 0:
                    # Use correct sign convention: long position selling = positive value
                    position.current_value = bid_price * abs(leg.quantity) * 100
                    position.legs[0].current_price = bid_price

            # Calculate final P&L with actual bid price (do this AFTER the override)
            pnl_result = PnLCalculator.calculate_unrealized_pnl(
                position.entry_cost,
                position.current_value
            )
            pnl = pnl_result.pnl
            pnl_pct = pnl_result.pnl_pct / 100 if pnl_result.pnl_pct is not None else 0

            return True, f"End of day exit - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        # Force exit if past expiration date (should not happen in normal flow)
        # expiration_date is now a date object (not datetime)
        if current_time.date() > leg.expiration_date:
            # Use bid price for exit value
            leg_data = options_data[options_data['option_ticker'] == leg.option_ticker]
            if not leg_data.empty:
                bid_price = leg_data.iloc[0]['bid']
                if not pd.isna(bid_price) and bid_price > 0:
                    # Use correct sign convention: long position selling = positive value
                    position.current_value = bid_price * abs(leg.quantity) * 100
                    position.legs[0].current_price = bid_price

            # Calculate final P&L with actual bid price (do this AFTER the override)
            pnl_result = PnLCalculator.calculate_unrealized_pnl(
                position.entry_cost,
                position.current_value
            )
            pnl = pnl_result.pnl
            pnl_pct = pnl_result.pnl_pct / 100 if pnl_result.pnl_pct is not None else 0

            return True, f"Past expiration - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        return False, None

    def get_strategy_name(self) -> str:
        """Return strategy name."""
        return "CoinToss"

    def get_description(self) -> str:
        """Return strategy description."""
        return (
            f"Naive coin toss strategy: randomly pick {self.quantity} contracts "
            f"near ${self.target_price:.2f}, buy at ${self.buy_limit:.2f}, "
            f"sell at ${self.sell_target:.2f}, max {self.max_trades_daily} trades/day"
        )
