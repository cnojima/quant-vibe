"""
Unit tests for PnL calculation utilities.
"""

import pytest
import numpy as np
import pandas as pd
from decimal import Decimal
from datetime import datetime

from quant_vibe.utils.pnl_utils import (
    PnLCalculator,
    PnLResult,
    PnLType
)


class TestPnLCalculator:
    """Test PnL calculation functions."""

    def test_basic_pnl_profit(self):
        """Test basic P&L calculation with profit."""
        result = PnLCalculator.calculate_pnl(1000.0, 1200.0)

        assert result.pnl == 200.0
        assert result.pnl_pct == 20.0
        assert result.pnl_type == PnLType.REALIZED
        assert result.is_winner is True

    def test_basic_pnl_loss(self):
        """Test basic P&L calculation with loss."""
        result = PnLCalculator.calculate_pnl(1000.0, 800.0)

        assert result.pnl == -200.0
        assert result.pnl_pct == -20.0
        assert result.pnl_type == PnLType.REALIZED
        assert result.is_winner is False

    def test_credit_spread_profit(self):
        """Test P&L for credit spread (negative entry cost)."""
        # Received $500 credit, bought back for $200
        result = PnLCalculator.calculate_pnl(-500.0, -200.0)

        assert result.pnl == 300.0  # We kept $300 of the credit
        assert result.pnl_pct == 60.0
        assert result.is_winner is True

    def test_credit_spread_loss(self):
        """Test P&L for credit spread with loss."""
        # Received $500 credit, bought back for $700
        result = PnLCalculator.calculate_pnl(-500.0, -700.0)

        assert result.pnl == -200.0  # We lost $200
        assert result.pnl_pct == -40.0
        assert result.is_winner is False

    def test_decimal_input(self):
        """Test P&L calculation with Decimal input."""
        result = PnLCalculator.calculate_pnl(
            Decimal('1000.50'),
            Decimal('1100.75')
        )

        assert result.pnl == 100.25
        # Percentage is rounded to 4 decimal places: (100.25 / 1000.50) * 100 = 10.0200
        assert result.pnl_pct == pytest.approx(10.02, rel=1e-4)

    def test_none_input(self):
        """Test P&L calculation with None values."""
        result = PnLCalculator.calculate_pnl(None, 1000.0)
        assert result.pnl == 1000.0
        assert result.pnl_pct is None  # Can't calculate percentage with 0 entry

        result = PnLCalculator.calculate_pnl(1000.0, None)
        assert result.pnl == -1000.0
        assert result.pnl_pct == -100.0

    def test_zero_entry_cost(self):
        """Test P&L calculation with zero entry cost."""
        result = PnLCalculator.calculate_pnl(0.0, 100.0)
        assert result.pnl == 100.0
        assert result.pnl_pct is None  # Can't divide by zero

    def test_unrealized_pnl(self):
        """Test unrealized P&L calculation."""
        result = PnLCalculator.calculate_unrealized_pnl(1000.0, 1150.0)

        assert result.pnl == 150.0
        assert result.pnl_pct == 15.0
        assert result.pnl_type == PnLType.UNREALIZED
        assert result.is_winner is True

    def test_realized_pnl(self):
        """Test realized P&L calculation."""
        result = PnLCalculator.calculate_realized_pnl(1000.0, 900.0)

        assert result.pnl == -100.0
        assert result.pnl_pct == -10.0
        assert result.pnl_type == PnLType.REALIZED
        assert result.is_winner is False

    def test_options_entry_cost_debit_spread(self):
        """Test options entry cost for debit spread."""
        legs = [
            {'action': 'BUY', 'price': 5.0, 'quantity': 1},  # Buy $5
            {'action': 'SELL', 'price': 3.0, 'quantity': 1}  # Sell $3
        ]

        cost = PnLCalculator.calculate_options_entry_cost(legs)
        assert cost == 200.0  # Net debit of $2 * 100

    def test_options_entry_cost_credit_spread(self):
        """Test options entry cost for credit spread."""
        legs = [
            {'action': 'SELL', 'price': 5.0, 'quantity': 1},  # Sell $5
            {'action': 'BUY', 'price': 2.0, 'quantity': 1}   # Buy $2
        ]

        cost = PnLCalculator.calculate_options_entry_cost(legs)
        assert cost == -300.0  # Net credit of $3 * 100

    def test_options_entry_cost_multiple_contracts(self):
        """Test options entry cost with multiple contracts."""
        legs = [
            {'action': 'BUY', 'price': 5.0, 'quantity': 10},  # Buy 10 contracts
        ]

        cost = PnLCalculator.calculate_options_entry_cost(legs)
        assert cost == 5000.0  # $5 * 10 * 100

    def test_options_exit_value(self):
        """Test options exit value calculation."""
        legs = [
            {'action': 'BUY', 'exit_price': 2.0, 'quantity': 1},  # Bought, now selling
            {'action': 'SELL', 'exit_price': 1.0, 'quantity': 1}  # Sold, now buying back
        ]

        value = PnLCalculator.calculate_options_exit_value(legs)
        assert value == 100.0  # Net of $1 * 100

    def test_aggregate_pnl_empty(self):
        """Test aggregate P&L with empty trades."""
        stats = PnLCalculator.aggregate_pnl([])

        assert stats['total_pnl'] == 0.0
        assert stats['num_trades'] == 0
        assert stats['win_rate'] == 0.0
        assert stats['profit_factor'] == 0.0

    def test_aggregate_pnl_mixed_trades(self):
        """Test aggregate P&L with mixed trades."""
        trades = [
            {'pnl': 100.0},
            {'pnl': -50.0},
            {'pnl': 200.0},
            {'pnl': -75.0},
            {'pnl': 150.0}
        ]

        stats = PnLCalculator.aggregate_pnl(trades)

        assert stats['total_pnl'] == 325.0
        assert stats['num_trades'] == 5
        assert stats['num_winners'] == 3
        assert stats['num_losers'] == 2
        assert stats['win_rate'] == 60.0
        assert stats['avg_win'] == 150.0
        assert stats['avg_loss'] == -62.5
        assert stats['avg_pnl'] == 65.0
        assert stats['largest_win'] == 200.0
        assert stats['largest_loss'] == -75.0
        # Profit factor = total_wins / total_losses = 450 / 125 = 3.6
        assert stats['profit_factor'] == pytest.approx(3.6, rel=1e-2)

    def test_aggregate_pnl_all_winners(self):
        """Test aggregate P&L with all winning trades."""
        trades = [
            {'pnl': 100.0},
            {'pnl': 200.0},
            {'pnl': 150.0}
        ]

        stats = PnLCalculator.aggregate_pnl(trades)

        assert stats['total_pnl'] == 450.0
        assert stats['num_winners'] == 3
        assert stats['num_losers'] == 0
        assert stats['win_rate'] == 100.0
        assert stats['profit_factor'] == PnLCalculator.MAX_PROFIT_FACTOR  # Max value instead of infinity

    def test_aggregate_pnl_different_field_names(self):
        """Test aggregate P&L with different field names."""
        trades = [
            {'realized_pnl': 100.0},
            {'profit_loss': -50.0},
            {'pnl': 75.0}
        ]

        stats = PnLCalculator.aggregate_pnl(trades)

        assert stats['total_pnl'] == 125.0
        assert stats['num_trades'] == 3

    def test_sharpe_ratio_basic(self):
        """Test Sharpe ratio calculation."""
        returns = [0.01, 0.02, -0.01, 0.015, -0.005, 0.01, 0.02]
        sharpe = PnLCalculator.calculate_sharpe_ratio(returns)

        # Should be positive since mean return is positive
        assert sharpe > 0
        assert isinstance(sharpe, float)

    def test_sharpe_ratio_with_risk_free(self):
        """Test Sharpe ratio with risk-free rate."""
        returns = [0.02, 0.03, 0.01, 0.025, 0.015]
        sharpe = PnLCalculator.calculate_sharpe_ratio(returns, risk_free_rate=0.02)

        assert isinstance(sharpe, float)

    def test_sharpe_ratio_insufficient_data(self):
        """Test Sharpe ratio with insufficient data."""
        assert PnLCalculator.calculate_sharpe_ratio([]) == 0.0
        assert PnLCalculator.calculate_sharpe_ratio([0.01]) == 0.0

    def test_sharpe_ratio_zero_volatility(self):
        """Test Sharpe ratio with zero volatility."""
        returns = [0.01, 0.01, 0.01, 0.01]
        sharpe = PnLCalculator.calculate_sharpe_ratio(returns)
        assert sharpe == 0.0  # Zero std dev

    def test_sharpe_ratio_pandas_series(self):
        """Test Sharpe ratio with pandas Series input."""
        returns = pd.Series([0.01, 0.02, -0.01, 0.015])
        sharpe = PnLCalculator.calculate_sharpe_ratio(returns)
        assert isinstance(sharpe, float)

    def test_max_drawdown_basic(self):
        """Test max drawdown calculation."""
        equity_curve = [10000, 11000, 10500, 12000, 11000, 10000, 11500]
        dd_value, dd_pct = PnLCalculator.calculate_max_drawdown(equity_curve)

        assert dd_value == -2000.0  # From 12000 to 10000
        assert dd_pct == pytest.approx(-16.6667, rel=1e-4)  # -2000/12000 * 100

    def test_max_drawdown_no_drawdown(self):
        """Test max drawdown with monotonically increasing curve."""
        equity_curve = [10000, 11000, 12000, 13000, 14000]
        dd_value, dd_pct = PnLCalculator.calculate_max_drawdown(equity_curve)

        assert dd_value == 0.0
        assert dd_pct == 0.0

    def test_max_drawdown_pandas_series(self):
        """Test max drawdown with pandas Series."""
        equity_curve = pd.Series([10000, 11000, 9000, 10000])
        dd_value, dd_pct = PnLCalculator.calculate_max_drawdown(equity_curve)

        assert dd_value == -2000.0  # From 11000 to 9000
        assert dd_pct == pytest.approx(-18.1818, rel=1e-4)

    def test_max_drawdown_insufficient_data(self):
        """Test max drawdown with insufficient data."""
        dd_value, dd_pct = PnLCalculator.calculate_max_drawdown([])
        assert dd_value == 0.0
        assert dd_pct == 0.0

        dd_value, dd_pct = PnLCalculator.calculate_max_drawdown([10000])
        assert dd_value == 0.0
        assert dd_pct == 0.0

    def test_return_metrics(self):
        """Test return metrics calculation."""
        metrics = PnLCalculator.calculate_return_metrics(10000, 12000, num_periods=252)

        assert metrics['total_return'] == 2000.0
        assert metrics['total_return_pct'] == 20.0
        assert metrics['cagr'] == 20.0  # 1 year period

    def test_return_metrics_multi_year(self):
        """Test return metrics over multiple years."""
        metrics = PnLCalculator.calculate_return_metrics(10000, 14641, num_periods=504)  # 2 years

        assert metrics['total_return'] == 4641.0
        assert metrics['total_return_pct'] == 46.41
        assert metrics['cagr'] == pytest.approx(21.0, rel=1e-2)  # (1.4641^0.5 - 1) * 100

    def test_return_metrics_zero_initial(self):
        """Test return metrics with zero initial capital."""
        metrics = PnLCalculator.calculate_return_metrics(0, 1000)

        assert metrics['total_return'] == 0.0
        assert metrics['total_return_pct'] == 0.0
        assert metrics['cagr'] == 0.0

    def test_position_pnl_batch(self):
        """Test batch P&L calculation for positions."""
        positions = pd.DataFrame({
            'entry_cost': [1000.0, -500.0, 2000.0],
            'exit_value': [1200.0, -300.0, None],
            'current_value': [None, None, 2100.0]
        })

        result = PnLCalculator.calculate_position_pnl_batch(positions)

        # First position: closed with profit
        assert result.iloc[0]['pnl'] == 200.0
        assert result.iloc[0]['pnl_pct'] == 20.0

        # Second position: credit spread closed with profit
        assert result.iloc[1]['pnl'] == 200.0
        assert result.iloc[1]['pnl_pct'] == 40.0

        # Third position: open with small profit
        assert result.iloc[2]['pnl'] == 100.0
        assert result.iloc[2]['pnl_pct'] == 5.0

    def test_position_pnl_batch_custom_columns(self):
        """Test batch P&L with custom column names."""
        positions = pd.DataFrame({
            'cost': [1000.0],
            'value': [1100.0]
        })

        result = PnLCalculator.calculate_position_pnl_batch(
            positions,
            entry_col='cost',
            current_col='value'
        )

        assert result.iloc[0]['pnl'] == 100.0
        assert result.iloc[0]['pnl_pct'] == 10.0

    def test_pnl_result_to_dict(self):
        """Test PnLResult to_dict method."""
        result = PnLResult(
            pnl=100.0,
            pnl_pct=10.0,
            pnl_type=PnLType.REALIZED,
            is_winner=True
        )

        d = result.to_dict()
        assert d['pnl'] == 100.0
        assert d['pnl_pct'] == 10.0
        assert d['pnl_type'] == 'realized'
        assert d['is_winner'] is True

    def test_format_pnl_display(self):
        """Test P&L display formatting."""
        # Positive P&L with percentage
        display = PnLCalculator.format_pnl_display(150.50, 15.5)
        assert display == "+$150.50 (+15.50%)"

        # Negative P&L with percentage
        display = PnLCalculator.format_pnl_display(-75.25, -7.5)
        assert display == "-$75.25 (-7.50%)"

        # Zero P&L
        display = PnLCalculator.format_pnl_display(0.0, 0.0)
        assert display == "$0.00 (0.00%)"

        # Without percentage
        display = PnLCalculator.format_pnl_display(1000.0)
        assert display == "+$1,000.00"

        # Without sign
        display = PnLCalculator.format_pnl_display(500.0, include_sign=False)
        assert display == "$500.00"

    def test_precision_constants(self):
        """Test that precision constants are properly set."""
        assert PnLCalculator.DOLLAR_PRECISION == 2
        assert PnLCalculator.PERCENT_PRECISION == 4
        assert PnLCalculator.RATIO_PRECISION == 3

    def test_edge_cases(self):
        """Test various edge cases."""
        # Very large numbers
        result = PnLCalculator.calculate_pnl(1e9, 1.1e9)
        assert result.pnl == 100000000.0
        assert result.pnl_pct == 10.0

        # Very small numbers
        result = PnLCalculator.calculate_pnl(0.01, 0.02)
        assert result.pnl == 0.01
        assert result.pnl_pct == 100.0

        # Negative to positive
        result = PnLCalculator.calculate_pnl(-100, 100)
        assert result.pnl == 200.0
        assert result.pnl_pct == 200.0