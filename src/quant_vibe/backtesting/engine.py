"""Backtesting engine."""

from typing import Dict, Any

import pandas as pd

from ..strategies.base import Strategy, Signal


class BacktestEngine:
    """Engine for backtesting trading strategies."""

    def __init__(
        self,
        initial_capital: float = 100000.0,
        commission: float = 0.001,
    ) -> None:
        """
        Initialize backtest engine.

        Args:
            initial_capital: Starting capital
            commission: Commission rate per trade (e.g., 0.001 = 0.1%)
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.results: Dict[str, Any] = {}

    def run(self, strategy: Strategy, data: pd.DataFrame) -> pd.DataFrame:
        """
        Run backtest on historical data.

        Args:
            strategy: Trading strategy to test
            data: Market data DataFrame

        Returns:
            DataFrame with backtest results including positions and portfolio value
        """
        # Generate signals
        signals = strategy.generate_signals(data)

        # Initialize portfolio
        portfolio = pd.DataFrame(index=data.index)
        portfolio["Price"] = data["Close"]
        portfolio["Signal"] = signals
        portfolio["Position"] = signals.replace({-1: 0}).cumsum()

        # Calculate positions (shares held)
        portfolio["Shares"] = 0.0
        cash = self.initial_capital

        for i in range(len(portfolio)):
            if portfolio["Signal"].iloc[i] == Signal.BUY.value and cash > 0:
                # Buy with all available cash
                price = portfolio["Price"].iloc[i]
                shares = int(cash / (price * (1 + self.commission)))
                cost = shares * price * (1 + self.commission)
                cash -= cost
                portfolio.loc[portfolio.index[i], "Shares"] = shares
            elif portfolio["Signal"].iloc[i] == Signal.SELL.value:
                # Sell all shares
                prev_shares = portfolio["Shares"].iloc[i - 1] if i > 0 else 0
                if prev_shares > 0:
                    price = portfolio["Price"].iloc[i]
                    proceeds = prev_shares * price * (1 - self.commission)
                    cash += proceeds
                    portfolio.loc[portfolio.index[i], "Shares"] = 0
            else:
                # Hold position
                if i > 0:
                    portfolio.loc[portfolio.index[i], "Shares"] = portfolio["Shares"].iloc[
                        i - 1
                    ]

        # Calculate portfolio value
        portfolio["Holdings"] = portfolio["Shares"] * portfolio["Price"]
        portfolio["Cash"] = float(self.initial_capital)
        for i in range(1, len(portfolio)):
            if portfolio["Signal"].iloc[i] == Signal.BUY.value:
                cost = portfolio["Shares"].iloc[i] * portfolio["Price"].iloc[i]
                portfolio.loc[portfolio.index[i], "Cash"] = float(
                    portfolio["Cash"].iloc[i - 1] - cost * (1 + self.commission)
                )
            elif portfolio["Signal"].iloc[i] == Signal.SELL.value:
                proceeds = portfolio["Shares"].iloc[i - 1] * portfolio["Price"].iloc[i]
                portfolio.loc[portfolio.index[i], "Cash"] = float(
                    portfolio["Cash"].iloc[i - 1] + proceeds * (1 - self.commission)
                )
            else:
                portfolio.loc[portfolio.index[i], "Cash"] = float(portfolio["Cash"].iloc[i - 1])

        portfolio["Total"] = portfolio["Holdings"] + portfolio["Cash"]
        portfolio["Returns"] = portfolio["Total"].pct_change()

        self.results = {
            "final_value": portfolio["Total"].iloc[-1],
            "total_return": (portfolio["Total"].iloc[-1] / self.initial_capital - 1) * 100,
            "total_trades": (portfolio["Signal"] != 0).sum(),
        }

        return portfolio
