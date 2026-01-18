"""
Centralized PnL calculation utilities.

This module provides standardized PnL calculations to ensure consistency
across the entire codebase. All PnL calculations should use these functions
instead of implementing their own logic.
"""

from typing import Optional, List, Dict, Tuple, Union, Any
from decimal import Decimal
import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class PnLType(Enum):
    """Type of PnL calculation."""
    REALIZED = "realized"
    UNREALIZED = "unrealized"


@dataclass
class PnLResult:
    """Standardized PnL calculation result."""
    pnl: float
    pnl_pct: Optional[float]
    pnl_type: PnLType
    is_winner: bool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'pnl': self.pnl,
            'pnl_pct': self.pnl_pct,
            'pnl_type': self.pnl_type.value,
            'is_winner': self.is_winner
        }


class PnLCalculator:
    """Centralized PnL calculation logic."""

    # Standard precision for different values
    DOLLAR_PRECISION = 2
    PERCENT_PRECISION = 4
    RATIO_PRECISION = 3

    # Maximum profit factor value (for database compatibility with NUMERIC(10,4))
    # Used when all trades are winners (no losses)
    MAX_PROFIT_FACTOR = 999.9999

    @classmethod
    def calculate_pnl(
        cls,
        entry_cost: Union[float, Decimal, None],
        exit_value: Union[float, Decimal, None],
        pnl_type: PnLType = PnLType.REALIZED
    ) -> PnLResult:
        """
        Calculate P&L with standardized logic.

        Formula: P&L = exit_value - entry_cost
        - Positive entry_cost = debit (we paid)
        - Negative entry_cost = credit (we received)

        Args:
            entry_cost: Entry cost (positive=debit, negative=credit)
            exit_value: Exit value or current value
            pnl_type: Type of PnL (realized/unrealized)

        Returns:
            PnLResult with calculated values
        """
        # Convert to float for consistency, handle None
        entry = float(entry_cost) if entry_cost is not None else 0.0
        exit = float(exit_value) if exit_value is not None else 0.0

        # Basic PnL
        pnl = exit - entry

        # Percentage (based on absolute entry cost)
        pnl_pct = None
        if entry != 0:
            pnl_pct = (pnl / abs(entry)) * 100

        return PnLResult(
            pnl=round(pnl, cls.DOLLAR_PRECISION),
            pnl_pct=round(pnl_pct, cls.PERCENT_PRECISION) if pnl_pct is not None else None,
            pnl_type=pnl_type,
            is_winner=pnl > 0
        )

    @classmethod
    def calculate_unrealized_pnl(
        cls,
        entry_cost: Union[float, Decimal, None],
        current_value: Union[float, Decimal, None]
    ) -> PnLResult:
        """Calculate unrealized P&L for open positions."""
        return cls.calculate_pnl(entry_cost, current_value, PnLType.UNREALIZED)

    @classmethod
    def calculate_realized_pnl(
        cls,
        entry_cost: Union[float, Decimal, None],
        exit_value: Union[float, Decimal, None]
    ) -> PnLResult:
        """Calculate realized P&L for closed positions."""
        return cls.calculate_pnl(entry_cost, exit_value, PnLType.REALIZED)

    @classmethod
    def calculate_options_entry_cost(
        cls,
        legs: List[Dict[str, Any]],
        multiplier: int = 100
    ) -> float:
        """
        Calculate total entry cost for options position.

        Args:
            legs: List of leg dictionaries with price, quantity, action
            multiplier: Options multiplier (default 100)

        Returns:
            Total entry cost (positive=debit, negative=credit)
        """
        total = 0.0

        for leg in legs:
            price = float(leg.get('price', 0))
            quantity = abs(int(leg.get('quantity', 0)))
            action = leg.get('action', '').upper()

            # Determine sign based on action
            # BUY/LONG = we pay (positive cost)
            # SELL/SHORT = we receive (negative cost)
            if action in ['BUY', 'LONG', 'BUY_TO_OPEN']:
                total += price * quantity * multiplier
            elif action in ['SELL', 'SHORT', 'SELL_TO_OPEN']:
                total -= price * quantity * multiplier

        return round(total, cls.DOLLAR_PRECISION)

    @classmethod
    def calculate_options_exit_value(
        cls,
        legs: List[Dict[str, Any]],
        multiplier: int = 100
    ) -> float:
        """
        Calculate total exit value for options position.

        Args:
            legs: List of leg dictionaries with exit_price, quantity, action
            multiplier: Options multiplier (default 100)

        Returns:
            Total exit value
        """
        total = 0.0

        for leg in legs:
            exit_price = float(leg.get('exit_price', 0))
            quantity = abs(int(leg.get('quantity', 0)))
            action = leg.get('action', '').upper()

            # Reverse of entry: if we bought, we sell; if we sold, we buy back
            if action in ['BUY', 'LONG', 'BUY_TO_OPEN']:
                # We bought to open, sell to close
                total += exit_price * quantity * multiplier
            elif action in ['SELL', 'SHORT', 'SELL_TO_OPEN']:
                # We sold to open, buy to close
                total -= exit_price * quantity * multiplier

        return round(total, cls.DOLLAR_PRECISION)

    @classmethod
    def aggregate_pnl(cls, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate P&L statistics from trades.

        Args:
            trades: List of trade dictionaries with 'pnl' field

        Returns:
            Dict with aggregated statistics
        """
        if not trades:
            return cls._empty_stats()

        # Extract PnL values, handling various field names
        pnls = []
        for trade in trades:
            # Try different field names
            pnl = trade.get('pnl') or trade.get('realized_pnl') or trade.get('profit_loss', 0)
            pnls.append(float(pnl))

        winners = [p for p in pnls if p > 0]
        losers = [p for p in pnls if p < 0]

        total_wins = sum(winners) if winners else 0
        total_losses = abs(sum(losers)) if losers else 0

        # Calculate profit factor
        # Note: Use MAX_PROFIT_FACTOR instead of infinity for database compatibility
        profit_factor = None
        if total_losses > 0:
            profit_factor = round(total_wins / total_losses, cls.RATIO_PRECISION)
        elif total_wins > 0:
            # All winners, no losses - use maximum representable value
            profit_factor = cls.MAX_PROFIT_FACTOR
        else:
            profit_factor = 0.0

        return {
            'total_pnl': round(sum(pnls), cls.DOLLAR_PRECISION),
            'num_trades': len(trades),
            'num_winners': len(winners),
            'num_losers': len(losers),
            'win_rate': round(len(winners) / len(trades) * 100, cls.PERCENT_PRECISION) if trades else 0.0,
            'avg_win': round(np.mean(winners), cls.DOLLAR_PRECISION) if winners else 0.0,
            'avg_loss': round(np.mean(losers), cls.DOLLAR_PRECISION) if losers else 0.0,
            'avg_pnl': round(np.mean(pnls), cls.DOLLAR_PRECISION) if pnls else 0.0,
            'largest_win': round(max(winners), cls.DOLLAR_PRECISION) if winners else 0.0,
            'largest_loss': round(min(losers), cls.DOLLAR_PRECISION) if losers else 0.0,
            'profit_factor': profit_factor
        }

    @classmethod
    def calculate_sharpe_ratio(
        cls,
        returns: Union[pd.Series, np.ndarray, List[float]],
        risk_free_rate: float = 0.0,
        periods_per_year: int = 252
    ) -> float:
        """
        Calculate Sharpe ratio with consistent methodology.

        Args:
            returns: Series of returns (as percentages or decimals)
            risk_free_rate: Annual risk-free rate (as decimal, e.g., 0.02 for 2%)
            periods_per_year: Trading periods per year (252 for daily, 52 for weekly)

        Returns:
            Annualized Sharpe ratio
        """
        if isinstance(returns, pd.Series):
            returns = returns.values
        elif isinstance(returns, list):
            returns = np.array(returns)

        if len(returns) < 2:
            return 0.0

        # Convert to numpy array if needed
        returns = np.array(returns)

        # Remove any NaN or infinite values
        returns = returns[np.isfinite(returns)]

        if len(returns) < 2:
            return 0.0

        # Calculate excess returns
        period_rf_rate = risk_free_rate / periods_per_year
        excess_returns = returns - period_rf_rate

        # Calculate Sharpe ratio
        mean_excess = np.mean(excess_returns)
        std_excess = np.std(excess_returns, ddof=1)  # Use sample standard deviation

        if std_excess == 0:
            return 0.0

        sharpe = mean_excess / std_excess

        # Annualize
        annualized_sharpe = sharpe * np.sqrt(periods_per_year)

        return round(annualized_sharpe, cls.RATIO_PRECISION)

    @classmethod
    def calculate_max_drawdown(
        cls,
        equity_curve: Union[pd.Series, List[float], np.ndarray]
    ) -> Tuple[float, float]:
        """
        Calculate maximum drawdown from equity curve.

        Args:
            equity_curve: Series or list of portfolio values

        Returns:
            Tuple of (max_drawdown_value, max_drawdown_pct)
        """
        if isinstance(equity_curve, list):
            equity_curve = pd.Series(equity_curve)
        elif isinstance(equity_curve, np.ndarray):
            equity_curve = pd.Series(equity_curve)

        if len(equity_curve) < 2:
            return 0.0, 0.0

        # Calculate running maximum
        cummax = equity_curve.expanding().max()

        # Calculate drawdown
        drawdown = equity_curve - cummax

        # Find maximum drawdown
        max_dd_value = float(drawdown.min())

        # Calculate percentage drawdown
        with np.errstate(divide='ignore', invalid='ignore'):
            pct_drawdown = (drawdown / cummax) * 100
            pct_drawdown = pct_drawdown[np.isfinite(pct_drawdown)]

        max_dd_pct = float(pct_drawdown.min()) if len(pct_drawdown) > 0 else 0.0

        return (
            round(max_dd_value, cls.DOLLAR_PRECISION),
            round(max_dd_pct, cls.PERCENT_PRECISION)
        )

    @classmethod
    def calculate_return_metrics(
        cls,
        initial_capital: float,
        final_capital: float,
        num_periods: Optional[int] = None
    ) -> Dict[str, float]:
        """
        Calculate various return metrics.

        Args:
            initial_capital: Starting capital
            final_capital: Ending capital
            num_periods: Number of periods for CAGR calculation

        Returns:
            Dict with return metrics
        """
        if initial_capital <= 0:
            return {
                'total_return': 0.0,
                'total_return_pct': 0.0,
                'cagr': 0.0
            }

        total_return = final_capital - initial_capital
        total_return_pct = (total_return / initial_capital) * 100

        # Calculate CAGR if periods provided
        cagr = 0.0
        if num_periods and num_periods > 0:
            years = num_periods / 252  # Assuming daily periods
            if years > 0:
                cagr = (((final_capital / initial_capital) ** (1 / years)) - 1) * 100

        return {
            'total_return': round(total_return, cls.DOLLAR_PRECISION),
            'total_return_pct': round(total_return_pct, cls.PERCENT_PRECISION),
            'cagr': round(cagr, cls.PERCENT_PRECISION)
        }

    @classmethod
    def calculate_position_pnl_batch(
        cls,
        positions: pd.DataFrame,
        entry_col: str = 'entry_cost',
        exit_col: str = 'exit_value',
        current_col: str = 'current_value'
    ) -> pd.DataFrame:
        """
        Calculate P&L for multiple positions in a DataFrame.

        Args:
            positions: DataFrame with position data
            entry_col: Column name for entry cost
            exit_col: Column name for exit value (for closed positions)
            current_col: Column name for current value (for open positions)

        Returns:
            DataFrame with added pnl and pnl_pct columns
        """
        df = positions.copy()

        # Determine if position is closed or open
        has_exit = df[exit_col].notna() if exit_col in df.columns else pd.Series([False] * len(df))

        # Calculate P&L based on position status
        df['pnl'] = 0.0
        df['pnl_pct'] = 0.0

        # Closed positions
        if has_exit.any():
            closed_mask = has_exit
            df.loc[closed_mask, 'pnl'] = df.loc[closed_mask, exit_col] - df.loc[closed_mask, entry_col]

        # Open positions
        if current_col in df.columns:
            open_mask = ~has_exit & df[current_col].notna()
            df.loc[open_mask, 'pnl'] = df.loc[open_mask, current_col] - df.loc[open_mask, entry_col]

        # Calculate percentage
        nonzero_entry = df[entry_col] != 0
        df.loc[nonzero_entry, 'pnl_pct'] = (df.loc[nonzero_entry, 'pnl'] / df.loc[nonzero_entry, entry_col].abs()) * 100

        # Round values
        df['pnl'] = df['pnl'].round(cls.DOLLAR_PRECISION)
        df['pnl_pct'] = df['pnl_pct'].round(cls.PERCENT_PRECISION)

        return df

    @classmethod
    def _empty_stats(cls) -> Dict[str, Any]:
        """Return empty statistics dictionary."""
        return {
            'total_pnl': 0.0,
            'num_trades': 0,
            'num_winners': 0,
            'num_losers': 0,
            'win_rate': 0.0,
            'avg_win': 0.0,
            'avg_loss': 0.0,
            'avg_pnl': 0.0,
            'largest_win': 0.0,
            'largest_loss': 0.0,
            'profit_factor': 0.0
        }

    @classmethod
    def format_pnl_display(
        cls,
        pnl: float,
        pnl_pct: Optional[float] = None,
        include_sign: bool = True
    ) -> str:
        """
        Format P&L for display.

        Args:
            pnl: P&L value
            pnl_pct: P&L percentage
            include_sign: Whether to include + sign for positive values

        Returns:
            Formatted string for display
        """
        # Format dollar amount
        if include_sign and pnl > 0:
            pnl_str = f"+${pnl:,.2f}"
        elif pnl < 0:
            pnl_str = f"-${abs(pnl):,.2f}"
        else:
            pnl_str = f"${pnl:,.2f}"

        # Add percentage if provided
        if pnl_pct is not None:
            if include_sign and pnl_pct > 0:
                pct_str = f"+{pnl_pct:.2f}%"
            else:
                pct_str = f"{pnl_pct:.2f}%"
            return f"{pnl_str} ({pct_str})"

        return pnl_str