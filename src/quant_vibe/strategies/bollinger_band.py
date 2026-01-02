"""
Bollinger Band Strategy - A directional strategy using Bollinger Bands with market orders.

This strategy:
1. Uses Bollinger Bands to determine bullish (call) or bearish (put) direction
   - Price near/below lower band = bullish (buy calls)
   - Price near/above upper band = bearish (buy puts)
2. Finds an option strike 10-15% OTM, targeting contracts priced near $2.00
3. Buys the closest option at ask price (market order simulation)
4. Exits when profit target reached, stop loss hit, or at end of day
5. Maximum trades per day limit enforced
"""

from datetime import datetime, time, timedelta
from typing import Dict, Optional, Any

import pandas as pd
import pytz

from quant_vibe.indicators.technical import calculate_bollinger_bands
from quant_vibe.strategies.options_base import (
    OptionLeg,
    OptionsPosition,
    OptionsStrategy,
    OptionType,
    SpreadType,
)
from live_trading_service.utils import generate_position_id


class BollingerBandStrategy(OptionsStrategy):
    """
    Bollinger Band strategy with market orders for entry and exit.

    Strategy Logic:
    - Use Bollinger Bands to determine direction:
      * Price near/below lower band = bullish (buy calls)
      * Price near/above upper band = bearish (buy puts)
    - Find options with strikes 10-15% OTM, priced near target (~$2)
    - Buy at ask price (market order simulation)
    - Exit when profit target reached or at end of day
    - Max trades per day limit enforced

    This is purely for educational/experimental purposes.
    """

    def __init__(
        self,
        target_price: float = 2.0,
        buy_limit: float = 1.0,
        sell_target: float = 2.0,
        otm_percent_min: float = 0.10,  # 10% OTM minimum
        otm_percent_max: float = 0.15,  # 15% OTM maximum
        price_tolerance: float = 1.0,  # How far from target_price to search
        max_trades_daily: int = 5,
        quantity: int = 10,
        min_dte: int = 0,
        max_dte: int = 45,
        profit_target_pct: float = 1.0,  # 100% profit (buy at 1, sell at 2)
        stop_loss_pct: Optional[float] = 0.50,  # 50% stop loss
        bb_period: int = 20,  # Bollinger Band period
        bb_std: float = 2.0,  # Bollinger Band standard deviations
        bb_threshold: float = 0.0,  # How close to band to trigger (0 = at band)
    ):
        """
        Initialize BollingerBandStrategy.

        Args:
            target_price: Target option price to search near ($2.00 default)
            buy_limit: Reference price for profit calculation (kept for compatibility)
            sell_target: Target price for exit signal ($2.00 default)
            otm_percent_min: Minimum OTM percentage (0.10 = 10%)
            otm_percent_max: Maximum OTM percentage (0.15 = 15%)
            price_tolerance: Search range around target_price (±$1.00 default)
            max_trades_daily: Maximum number of trades per day (5 default)
            quantity: Number of contracts to trade (10 default)
            min_dte: Minimum days to expiration (0 default)
            max_dte: Maximum days to expiration (45 default)
            profit_target_pct: Profit target as percentage (1.0 = 100%)
            stop_loss_pct: Stop loss as percentage (0.50 = 50%)
            bb_period: Bollinger Band moving average period (20 default)
            bb_std: Bollinger Band standard deviations (2.0 default)
            bb_threshold: How close to band to trigger signal (0 = at band)
        """
        super().__init__(name="BollingerBand", max_trades_daily=max_trades_daily)

        self.target_price = target_price
        self.buy_limit = buy_limit
        self.sell_target = sell_target
        self.otm_percent_min = otm_percent_min
        self.otm_percent_max = otm_percent_max
        self.price_tolerance = price_tolerance
        self.quantity = quantity
        self.min_dte = min_dte
        self.max_dte = max_dte
        self.profit_target_pct = profit_target_pct
        self.stop_loss_pct = stop_loss_pct

        # Bollinger Band parameters
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.bb_threshold = bb_threshold

        # Track current day for reset detection
        self.current_day: Optional[datetime] = None

    def _determine_direction_from_bollinger(
        self,
        underlying_data: pd.DataFrame,
    ) -> tuple[Optional[str], Dict[str, Any]]:
        """
        Determine trade direction using Bollinger Bands.

        - Price near/below lower band = bullish (buy calls)
        - Price near/above upper band = bearish (buy puts)
        - Price in middle = no signal

        Args:
            underlying_data: DataFrame with underlying price data (must have 'close' column)

        Returns:
            Tuple of (direction, bb_info) where direction is 'call', 'put', or None
        """
        if underlying_data.empty or len(underlying_data) < self.bb_period:
            return None, {"reason": f"Insufficient data for BB calculation (need {self.bb_period} bars)"}

        # Calculate Bollinger Bands
        close_prices = underlying_data["close"]
        upper_band, middle_band, lower_band = calculate_bollinger_bands(
            close_prices, period=self.bb_period, num_std=self.bb_std
        )

        # Get current values
        current_price = close_prices.iloc[-1]
        current_upper = upper_band.iloc[-1]
        current_middle = middle_band.iloc[-1]
        current_lower = lower_band.iloc[-1]

        # Check for NaN values
        if pd.isna(current_upper) or pd.isna(current_lower) or pd.isna(current_middle):
            return None, {"reason": "Bollinger Band values are NaN"}

        # Calculate band width for threshold
        band_width = current_upper - current_lower
        threshold_distance = band_width * self.bb_threshold

        bb_info = {
            "current_price": current_price,
            "upper_band": current_upper,
            "middle_band": current_middle,
            "lower_band": current_lower,
            "band_width": band_width,
            "price_position": (current_price - current_lower) / band_width if band_width > 0 else 0.5,
        }

        # Determine direction based on price position relative to bands
        if current_price <= current_lower + threshold_distance:
            # Price at or below lower band = bullish signal (buy calls)
            bb_info["signal"] = "bullish"
            bb_info["reason"] = f"Price ${current_price:.2f} at/below lower band ${current_lower:.2f}"
            return "call", bb_info
        elif current_price >= current_upper - threshold_distance:
            # Price at or above upper band = bearish signal (buy puts)
            bb_info["signal"] = "bearish"
            bb_info["reason"] = f"Price ${current_price:.2f} at/above upper band ${current_upper:.2f}"
            return "put", bb_info
        else:
            # Price in the middle = no clear signal
            bb_info["signal"] = "neutral"
            bb_info["reason"] = f"Price ${current_price:.2f} between bands (${current_lower:.2f} - ${current_upper:.2f})"
            return None, bb_info

    def analyze_market(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
    ) -> Dict[str, Any]:
        """
        Analyze market using Bollinger Bands for direction.

        Returns:
            Dict with 'direction' (call/put), 'signal' (bool), and Bollinger Band info
        """
        # Reset daily counter if new day
        if self.current_day is None or self.current_day.date() != current_time.date():
            self.current_day = current_time
            self.trades_today = 0

        # Check if we've hit max trades today
        if self.trades_today >= self.max_trades_daily:
            return {"direction": None, "signal": False, "reason": "Max trades today"}

        # Use Bollinger Bands to determine direction
        direction, bb_info = self._determine_direction_from_bollinger(underlying_data)

        result = {
            "direction": direction,
            "signal": direction is not None,
            "trades_today": self.trades_today,
            "bollinger_bands": bb_info,
        }

        if direction is None:
            result["reason"] = bb_info.get("reason", "No Bollinger Band signal")

        return result

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

        # Get current underlying price
        if underlying_data.empty:
            print(f"[BollingerBand] No underlying data available")
            return None

        current_underlying = underlying_data.iloc[-1]["close"]

        # Calculate DTE range
        target_date = current_time + timedelta(days=self.min_dte)
        max_date = current_time + timedelta(days=self.max_dte)

        # Normalize dates for comparison (expiration_date is timezone-naive)
        target_date = pd.Timestamp(target_date).normalize().tz_localize(None)
        max_date = pd.Timestamp(max_date).normalize().tz_localize(None)

        # Calculate target strike range (10-15% OTM)
        if direction == "call":
            # For calls, OTM means strike > underlying price
            strike_min = current_underlying * (1 + self.otm_percent_min)
            strike_max = current_underlying * (1 + self.otm_percent_max)
        else:
            # For puts, OTM means strike < underlying price
            strike_min = current_underlying * (1 - self.otm_percent_max)
            strike_max = current_underlying * (1 - self.otm_percent_min)

        # Early return if no data
        if options_data.empty:
            print(f"[BollingerBand] No options data available")
            return None

        # Check for required columns
        if 'contract_type' not in options_data.columns:
            print(f"[BollingerBand] ERROR: 'contract_type' column missing from options data")
            return None

        if 'expiration_date' not in options_data.columns:
            print(f"[BollingerBand] ERROR: 'expiration_date' column missing from options data")
            return None

        # Filter options by type, DTE, and strike range
        options_filtered = options_data[
            (options_data["contract_type"] == direction)
            & (options_data["expiration_date"] >= target_date)
            & (options_data["expiration_date"] <= max_date)
            & (options_data["strike_price"] >= strike_min)
            & (options_data["strike_price"] <= strike_max)
        ].copy()

        if options_filtered.empty:
            # Fallback: expand search to any OTM option
            if direction == "call":
                options_filtered = options_data[
                    (options_data["contract_type"] == direction)
                    & (options_data["expiration_date"] >= target_date)
                    & (options_data["expiration_date"] <= max_date)
                    & (options_data["strike_price"] > current_underlying)
                ].copy()
            else:
                options_filtered = options_data[
                    (options_data["contract_type"] == direction)
                    & (options_data["expiration_date"] >= target_date)
                    & (options_data["expiration_date"] <= max_date)
                    & (options_data["strike_price"] < current_underlying)
                ].copy()

        if options_filtered.empty:
            print(f"[BollingerBand] No {direction} options found in DTE range {self.min_dte}-{self.max_dte} days, strike range ${strike_min:.2f}-${strike_max:.2f}")
            return None

        # Find options with ask price near target_price
        # We want to buy options around the target price range
        price_min = self.target_price - self.price_tolerance
        price_max = self.target_price + self.price_tolerance

        price_filtered = options_filtered[
            (options_filtered["ask"] >= price_min)
            & (options_filtered["ask"] <= price_max)
        ].copy()

        if not price_filtered.empty:
            options_filtered = price_filtered

        # Sort by how close to target price and pick the closest one
        options_filtered["price_diff"] = abs(
            options_filtered["ask"] - self.target_price
        )
        options_filtered = options_filtered.sort_values("price_diff")

        # Pick the closest one to target price
        selected = options_filtered.iloc[0]

        # Create position ID
        position_id = generate_position_id(
            strategy_prefix="BB",
            current_time=current_time,
            counter=self.trades_today + 1
        )

        # Use the ask price as entry price
        # This is a market order - we buy at ask price
        entry_price = selected["ask"]

        leg = OptionLeg(
            contract_symbol=selected["contract_symbol"],
            option_type=option_type,
            strike_price=selected["strike_price"],
            expiration_date=selected["expiration_date"],
            quantity=self.quantity,
            entry_price=entry_price,
        )

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
            profit_target=self.profit_target_pct,
            stop_loss=self.stop_loss_pct,
        )

        # Increment trades counter
        self.trades_today += 1

        return position

    def should_exit(
        self,
        position: OptionsPosition,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
    ) -> tuple[bool, Optional[str]]:
        """
        Check if we should exit the position.

        Exit conditions:
        1. Profit target reached (based on profit_target_pct from position)
        2. Stop loss hit (if configured)
        3. End of day (4 PM ET)
        4. Expiration day

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

        # Calculate current P&L and mark price
        # current_value = quantity * price * 100 (multiplier)
        # entry_cost = quantity * entry_price * 100
        pnl = position.current_value - position.entry_cost
        pnl_pct = pnl / abs(position.entry_cost) if position.entry_cost != 0 else 0

        # Validate pnl_pct - skip if NaN
        if pd.isna(pnl_pct):
            return False, None

        mark_price = position.current_value / (abs(position.legs[0].quantity) * 100)

        # Check profit target (from position.profit_target)
        if pnl_pct >= position.profit_target:
            # Override position value to use bid price (what we'd actually get when selling)
            # This prevents P&L distortion from wide bid/ask spreads
            leg = position.legs[0]
            leg_data = options_data[options_data['contract_symbol'] == leg.contract_symbol]
            if not leg_data.empty:
                bid_price = leg_data.iloc[0]['bid']
                if not pd.isna(bid_price) and bid_price > 0:
                    position.current_value = bid_price * leg.quantity * 100
                    position.legs[0].current_price = bid_price
                    # Recalculate P&L with actual bid price
                    pnl = position.current_value - position.entry_cost
                    pnl_pct = pnl / abs(position.entry_cost) if position.entry_cost != 0 else 0

            return True, f"Profit target ({position.profit_target*100:.0f}%) reached - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        # Check stop loss if configured (from position.stop_loss)
        # stop_loss should be positive (e.g., 0.30 for 30% stop)
        # pnl_pct is negative when losing (e.g., -0.30 for -30% loss)
        if position.stop_loss is not None:
            if pnl_pct <= -abs(position.stop_loss):
                # Use bid price for exit value
                leg = position.legs[0]
                leg_data = options_data[options_data['contract_symbol'] == leg.contract_symbol]
                if not leg_data.empty:
                    bid_price = leg_data.iloc[0]['bid']
                    if not pd.isna(bid_price) and bid_price > 0:
                        position.current_value = bid_price * leg.quantity * 100
                        position.legs[0].current_price = bid_price
                        pnl = position.current_value - position.entry_cost
                        pnl_pct = pnl / abs(position.entry_cost) if position.entry_cost != 0 else 0

                return True, f"Stop loss ({abs(position.stop_loss)*100:.0f}%) hit - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        # Exit at end of day (4 PM ET) or if it's expiration day
        # Options expire at 4 PM on expiration date
        # Convert current_time to Eastern Time for proper comparison
        eastern = pytz.timezone('US/Eastern')
        current_time_et = current_time.astimezone(eastern)
        exit_time = time(16, 0)
        leg = position.legs[0]

        if current_time_et.time() >= exit_time:
            # Use bid price for exit value
            leg_data = options_data[options_data['contract_symbol'] == leg.contract_symbol]
            if not leg_data.empty:
                bid_price = leg_data.iloc[0]['bid']
                if not pd.isna(bid_price) and bid_price > 0:
                    position.current_value = bid_price * leg.quantity * 100
                    position.legs[0].current_price = bid_price
                    pnl = position.current_value - position.entry_cost
                    pnl_pct = pnl / abs(position.entry_cost) if position.entry_cost != 0 else 0

            return True, f"End of day exit - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        # Force exit if past expiration date (should not happen in normal flow)
        if current_time.date() > leg.expiration_date.date():
            # Use bid price for exit value
            leg_data = options_data[options_data['contract_symbol'] == leg.contract_symbol]
            if not leg_data.empty:
                bid_price = leg_data.iloc[0]['bid']
                if not pd.isna(bid_price) and bid_price > 0:
                    position.current_value = bid_price * leg.quantity * 100
                    position.legs[0].current_price = bid_price
                    pnl = position.current_value - position.entry_cost
                    pnl_pct = pnl / abs(position.entry_cost) if position.entry_cost != 0 else 0

            return True, f"Past expiration - P&L: ${pnl:.2f} ({pnl_pct*100:.1f}%)"

        return False, None

    def get_strategy_name(self) -> str:
        """Return strategy name."""
        return "BollingerBand"

    def get_description(self) -> str:
        """Return strategy description."""
        return (
            f"Bollinger Band ({self.bb_period}, {self.bb_std}) strategy: "
            f"buy {self.quantity} contracts "
            f"{self.otm_percent_min*100:.0f}-{self.otm_percent_max*100:.0f}% OTM "
            f"near ${self.target_price:.2f}, "
            f"target {self.profit_target_pct*100:.0f}% profit, "
            f"max {self.max_trades_daily} trades/day"
        )
