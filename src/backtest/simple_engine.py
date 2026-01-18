"""Simple backtesting engine for equity strategies."""

from typing import Dict, Any
import pandas as pd
from quant_vibe.strategies.base import Strategy, Signal


class BacktestEngine:
    """Engine for backtesting trading strategies."""

    def __init__(self, initial_capital: float = 100000.0, commission: float = 0.001) -> None:
        """Initialize backtest engine."""
        self.initial_capital = initial_capital
        self.commission = commission
        self.results: Dict[str, Any] = {}

    def run(self, strategy: Strategy, data: pd.DataFrame) -> pd.DataFrame:
        """Run backtest on historical data."""
        # Generate signals
        signals = strategy.generate_signals(data)

        # Initialize portfolio
        portfolio = self._initialize_portfolio(data, signals)

        # Calculate positions and cash flow
        portfolio = self._calculate_positions(portfolio)

        # Calculate portfolio metrics
        portfolio = self._calculate_metrics(portfolio)

        # Store results
        self._store_results(portfolio)

        return portfolio

    def _initialize_portfolio(self, data: pd.DataFrame, signals: pd.Series) -> pd.DataFrame:
        """Initialize portfolio dataframe with basic columns."""
        portfolio = pd.DataFrame(index=data.index)
        portfolio["Price"] = data["Close"]
        portfolio["Signal"] = signals
        portfolio["Position"] = signals.replace({-1: 0}).cumsum()
        portfolio["Shares"] = 0.0
        portfolio["Cash"] = float(self.initial_capital)
        return portfolio

    def _calculate_positions(self, portfolio: pd.DataFrame) -> pd.DataFrame:
        """Calculate share positions and cash flow."""
        cash = self.initial_capital

        for i in range(len(portfolio)):
            current_signal = portfolio["Signal"].iloc[i]
            current_price = portfolio["Price"].iloc[i]

            if current_signal == Signal.BUY.value and cash > 0:
                # Buy with all available cash
                shares = int(cash / (current_price * (1 + self.commission)))
                cost = shares * current_price * (1 + self.commission)
                cash -= cost
                portfolio.loc[portfolio.index[i], "Shares"] = shares
            elif current_signal == Signal.SELL.value and i > 0:
                # Sell all shares
                prev_shares = portfolio["Shares"].iloc[i - 1]
                if prev_shares > 0:
                    proceeds = prev_shares * current_price * (1 - self.commission)
                    cash += proceeds
                    portfolio.loc[portfolio.index[i], "Shares"] = 0
            elif i > 0:
                # Hold position
                portfolio.loc[portfolio.index[i], "Shares"] = portfolio["Shares"].iloc[i - 1]

            # Update cash column
            if i > 0:
                portfolio.loc[portfolio.index[i], "Cash"] = self._calculate_cash_at_index(
                    portfolio, i, cash
                )

        return portfolio

    def _calculate_cash_at_index(self, portfolio: pd.DataFrame, index: int, current_cash: float) -> float:
        """Calculate cash value at specific index."""
        signal = portfolio["Signal"].iloc[index]
        prev_cash = portfolio["Cash"].iloc[index - 1]

        if signal == Signal.BUY.value:
            shares = portfolio["Shares"].iloc[index]
            price = portfolio["Price"].iloc[index]
            return float(prev_cash - shares * price * (1 + self.commission))
        elif signal == Signal.SELL.value:
            prev_shares = portfolio["Shares"].iloc[index - 1]
            price = portfolio["Price"].iloc[index]
            return float(prev_cash + prev_shares * price * (1 - self.commission))

        return float(prev_cash)

    def _calculate_metrics(self, portfolio: pd.DataFrame) -> pd.DataFrame:
        """Calculate portfolio value and returns."""
        portfolio["Holdings"] = portfolio["Shares"] * portfolio["Price"]
        portfolio["Total"] = portfolio["Holdings"] + portfolio["Cash"]
        portfolio["Returns"] = portfolio["Total"].pct_change()
        return portfolio

    def _store_results(self, portfolio: pd.DataFrame) -> None:
        """Store backtest results."""
        self.results = {
            "final_value": portfolio["Total"].iloc[-1],
            "total_return": (portfolio["Total"].iloc[-1] / self.initial_capital - 1) * 100,
            "total_trades": (portfolio["Signal"] != 0).sum(),
        }