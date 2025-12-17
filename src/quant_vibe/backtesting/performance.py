"""Performance metrics calculation."""

from typing import Dict, Any

import pandas as pd
import numpy as np


class PerformanceMetrics:
    """Calculate performance metrics for backtesting results."""

    @staticmethod
    def calculate(portfolio: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate comprehensive performance metrics.

        Args:
            portfolio: Backtest results DataFrame

        Returns:
            Dictionary of performance metrics
        """
        returns = portfolio["Returns"].dropna()

        metrics = {
            "total_return": (portfolio["Total"].iloc[-1] / portfolio["Total"].iloc[0] - 1),
            "annual_return": PerformanceMetrics._annualized_return(returns),
            "sharpe_ratio": PerformanceMetrics._sharpe_ratio(returns),
            "max_drawdown": PerformanceMetrics._max_drawdown(portfolio["Total"]),
            "volatility": returns.std() * np.sqrt(252),
            "win_rate": PerformanceMetrics._trade_win_rate(portfolio),
        }

        return metrics

    @staticmethod
    def _annualized_return(returns: pd.Series) -> float:
        """Calculate annualized return."""
        total_return = (1 + returns).prod() - 1
        n_years = len(returns) / 252  # Assuming 252 trading days per year
        return ((1 + total_return) ** (1 / n_years) - 1) if n_years > 0 else 0.0

    @staticmethod
    def _sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio."""
        excess_returns = returns - risk_free_rate / 252
        return (
            np.sqrt(252) * excess_returns.mean() / returns.std() if returns.std() > 0 else 0.0
        )

    @staticmethod
    def _max_drawdown(portfolio_value: pd.Series) -> float:
        """Calculate maximum drawdown."""
        peak = portfolio_value.expanding(min_periods=1).max()
        drawdown = (portfolio_value - peak) / peak
        return drawdown.min()

    @staticmethod
    def _win_rate(returns: pd.Series) -> float:
        """Calculate win rate (percentage of positive returns)."""
        positive_returns = (returns > 0).sum()
        total_returns = len(returns)
        return (positive_returns / total_returns * 100) if total_returns > 0 else 0.0
    
    @staticmethod
    def _trade_win_rate(portfolio: pd.DataFrame) -> float:
        """
        Calculate trade-based win rate.
        
        Win rate = (Number of profitable closed trades) / (Total closed trades) * 100
        A trade is considered closed when we exit a position (SELL signal).
        """
        buy_signals = portfolio[portfolio['Signal'] == 1].index.tolist()
        sell_signals = portfolio[portfolio['Signal'] == -1].index.tolist()
        
        if len(sell_signals) == 0:
            return 0.0
        
        winning_trades = 0
        total_trades = 0
        used_buys = set()
        
        # For each sell signal, find the corresponding buy
        for sell_idx in sell_signals:
            # Find the most recent buy before this sell that hasn't been used
            matching_buy = None
            for buy_idx in reversed(buy_signals):
                if buy_idx < sell_idx and buy_idx not in used_buys:
                    matching_buy = buy_idx
                    break
            
            if matching_buy is not None:
                # Get portfolio values at buy and sell
                buy_value = portfolio.loc[matching_buy, 'Total']
                sell_value = portfolio.loc[sell_idx, 'Total']
                
                # Check if trade was profitable
                if sell_value > buy_value:
                    winning_trades += 1
                
                total_trades += 1
                used_buys.add(matching_buy)
        
        return (winning_trades / total_trades) if total_trades > 0 else 0.0
