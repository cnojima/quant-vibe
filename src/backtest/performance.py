"""Performance metrics calculation for backtest results."""

from typing import Dict, Any
import pandas as pd
import numpy as np


class PerformanceMetrics:
    """Calculate performance metrics for backtesting results."""

    @staticmethod
    def calculate(portfolio: pd.DataFrame) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics."""
        returns = portfolio["Returns"].dropna()

        return {
            "total_return": (portfolio["Total"].iloc[-1] / portfolio["Total"].iloc[0] - 1),
            "annual_return": PerformanceMetrics._annualized_return(returns),
            "sharpe_ratio": PerformanceMetrics._sharpe_ratio(returns),
            "max_drawdown": PerformanceMetrics._max_drawdown(portfolio["Total"]),
            "volatility": returns.std() * np.sqrt(252),
            "win_rate": PerformanceMetrics._trade_win_rate(portfolio),
        }

    @staticmethod
    def _annualized_return(returns: pd.Series) -> float:
        """Calculate annualized return."""
        if len(returns) == 0:
            return 0.0

        total_return = (1 + returns).prod() - 1
        n_years = len(returns) / 252  # Assuming 252 trading days per year

        if n_years <= 0:
            return 0.0

        return (1 + total_return) ** (1 / n_years) - 1

    @staticmethod
    def _sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio."""
        if len(returns) == 0 or returns.std() == 0:
            return 0.0

        excess_returns = returns - risk_free_rate / 252
        return np.sqrt(252) * excess_returns.mean() / returns.std()

    @staticmethod
    def _max_drawdown(portfolio_value: pd.Series) -> float:
        """Calculate maximum drawdown."""
        peak = portfolio_value.expanding(min_periods=1).max()
        drawdown = (portfolio_value - peak) / peak
        return drawdown.min()

    @staticmethod
    def _trade_win_rate(portfolio: pd.DataFrame) -> float:
        """Calculate trade-based win rate."""
        buy_signals = portfolio[portfolio['Signal'] == 1].index.tolist()
        sell_signals = portfolio[portfolio['Signal'] == -1].index.tolist()

        if not sell_signals:
            return 0.0

        winning_trades = 0
        total_trades = 0
        used_buys = set()

        # Match each sell with its corresponding buy
        for sell_idx in sell_signals:
            # Find the most recent unused buy before this sell
            matching_buy = None
            for buy_idx in reversed(buy_signals):
                if buy_idx < sell_idx and buy_idx not in used_buys:
                    matching_buy = buy_idx
                    break

            if matching_buy is not None:
                # Check if trade was profitable
                if portfolio.loc[sell_idx, 'Total'] > portfolio.loc[matching_buy, 'Total']:
                    winning_trades += 1

                total_trades += 1
                used_buys.add(matching_buy)

        return (winning_trades / total_trades) if total_trades > 0 else 0.0