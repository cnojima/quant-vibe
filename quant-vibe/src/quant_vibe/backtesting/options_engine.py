"""Options Backtesting Engine.

This module provides backtesting capabilities specifically designed for options strategies.
It handles:
- Options-specific position tracking
- Spread construction and management
- Time decay and expiration
- Options pricing (mark = mid of bid/ask)
- Position P&L calculation
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import pytz

from ..strategies.options_base import OptionsStrategy, OptionsPosition


class OptionsBacktestEngine:
    """Engine for backtesting options trading strategies.

    This engine is designed to work with:
    - Options strategies that implement the OptionsStrategy base class
    - High-frequency options data (1-minute bars with greeks)
    - Underlying price data for analysis
    """

    def __init__(
        self,
        initial_capital: float = 100000.0,
        max_positions: int = 1,
        log_trades: bool = True,
    ) -> None:
        """
        Initialize options backtest engine.

        Args:
            initial_capital: Starting capital
            max_positions: Maximum concurrent positions (default: 1)
            log_trades: Whether to log trade entries/exits (default: True)
        """
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.log_trades = log_trades

        # Performance tracking
        self.results: Dict[str, Any] = {}
        self.equity_curve: List[Dict[str, Any]] = []
        self.trades: List[Dict[str, Any]] = []

    def run(
        self,
        strategy: OptionsStrategy,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        resample_underlying: str = "1min",
    ) -> Dict[str, Any]:
        """
        Run backtest on historical options data.

        Args:
            strategy: Options strategy to test (implements OptionsStrategy)
            underlying_data: OHLCV data for underlying asset (e.g., SPX daily bars)
            options_data: Options chain data with OHLCV, greeks, quotes
            start_date: Start date for backtest (defaults to first data point)
            end_date: End date for backtest (defaults to last data point)
            resample_underlying: How to resample underlying data (default: '1min')

        Returns:
            Dictionary with backtest results including trades, equity curve, metrics
        """
        # Validate data
        if underlying_data.empty:
            raise ValueError("underlying_data cannot be empty")
        if options_data.empty:
            raise ValueError("options_data cannot be empty")

        # Ensure index is datetime
        if not isinstance(underlying_data.index, pd.DatetimeIndex):
            raise ValueError("underlying_data must have DatetimeIndex")
        if 'timestamp' not in options_data.columns:
            raise ValueError("options_data must have 'timestamp' column")

        # Set date range
        if start_date is None:
            start_date = underlying_data.index[0]
        if end_date is None:
            end_date = underlying_data.index[-1]

        # Make dates timezone-aware if options data is timezone-aware
        if 'timestamp' in options_data.columns and not options_data.empty:
            if hasattr(options_data['timestamp'].iloc[0], 'tz') and options_data['timestamp'].iloc[0].tz is not None:
                # Options data is timezone-aware, make start/end dates timezone-aware too
                import pytz
                if start_date.tzinfo is None:
                    start_date = pytz.UTC.localize(start_date)
                if end_date.tzinfo is None:
                    end_date = pytz.UTC.localize(end_date)

                # Also make underlying data index timezone-aware
                if underlying_data.index.tz is None:
                    underlying_data.index = underlying_data.index.tz_localize('UTC')

        # Filter data to date range
        underlying_data = underlying_data.loc[start_date:end_date]
        options_data = options_data[
            (options_data['timestamp'] >= start_date) &
            (options_data['timestamp'] <= end_date)
        ]

        # Resample underlying data to match options timeframe if needed
        if resample_underlying:
            underlying_data = self._resample_ohlcv(underlying_data, resample_underlying)

        # Get unique timestamps from options data
        timestamps = sorted(options_data['timestamp'].unique())

        print(f"\n{'='*70}")
        print(f"OPTIONS BACKTEST: {strategy.name}")
        print(f"{'='*70}")
        print(f"Date Range: {start_date.date()} to {end_date.date()}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Underlying Data Points: {len(underlying_data):,}")
        print(f"Options Timestamps: {len(timestamps):,}")
        print(f"Options Contracts: {options_data['contract_symbol'].nunique():,}")
        print(f"{'='*70}\n")

        # Initialize tracking
        cash = self.initial_capital
        current_day = None

        # Main backtest loop - iterate through each timestamp
        for i, current_time in enumerate(timestamps):
            # Get data up to current time
            underlying_slice = underlying_data[underlying_data.index <= current_time]
            options_slice = options_data[options_data['timestamp'] == current_time]

            if underlying_slice.empty:
                continue

            # Check if we've moved to a new day
            current_date = current_time.date()
            if current_day is None or current_date != current_day:
                if hasattr(strategy, 'reset_daily_state'):
                    strategy.reset_daily_state()
                current_day = current_date
                print(f"\n📅 {current_date.strftime('%Y-%m-%d')} ({current_date.strftime('%A')})")

            # Step 1: Analyze market conditions
            market_analysis = strategy.analyze_market(
                underlying_slice,
                options_slice,
                current_time
            )

            # Step 2: Manage existing position (if any)
            if strategy.active_position is not None:
                position = strategy.active_position

                # Update position value
                strategy.update_position_value(position, options_slice)

                # Check exit conditions
                should_exit, exit_reason = strategy.should_exit(
                    position,
                    underlying_slice,
                    options_slice,
                    current_time
                )

                if should_exit:
                    self._close_position(
                        strategy,
                        position,
                        current_time,
                        exit_reason,
                        cash
                    )
                    # Update cash with exit value
                    cash += position.exit_value

            # Step 3: Check for new entry (if no active position)
            if strategy.active_position is None:
                if strategy.should_enter(
                    underlying_slice,
                    options_slice,
                    current_time,
                    market_analysis
                ):
                    # Construct spread
                    new_position = strategy.construct_spread(
                        underlying_slice,
                        options_slice,
                        current_time,
                        market_analysis
                    )

                    if new_position is not None:
                        # Check if we have enough capital
                        entry_cost = abs(new_position.entry_cost)
                        if entry_cost <= cash:
                            # Enter position
                            strategy.active_position = new_position
                            strategy.positions.append(new_position)
                            cash -= entry_cost

                            if self.log_trades:
                                self._log_position_entry(new_position, cash)
                        else:
                            print(f"  ⚠️  Insufficient capital: need ${entry_cost:.2f}, have ${cash:.2f}")

            # Step 4: Record equity snapshot
            portfolio_value = cash
            if strategy.active_position is not None:
                if strategy.active_position.current_value is not None:
                    portfolio_value += strategy.active_position.current_value

            self.equity_curve.append({
                'timestamp': current_time,
                'cash': cash,
                'portfolio_value': portfolio_value,
                'active_position': strategy.active_position is not None
            })

        # Close any remaining positions at end of backtest
        if strategy.active_position is not None:
            print(f"\n⚠️  Closing position at end of backtest period")
            self._close_position(
                strategy,
                strategy.active_position,
                end_date,
                "End of backtest",
                cash
            )
            cash += strategy.active_position.exit_value

        # Calculate final results
        self._calculate_results(strategy, cash)

        return self.results

    def _resample_ohlcv(self, data: pd.DataFrame, freq: str) -> pd.DataFrame:
        """Resample OHLCV data to a different frequency.

        Args:
            data: DataFrame with OHLC columns
            freq: Frequency string (e.g., '1min', '5min', '1H')

        Returns:
            Resampled DataFrame
        """
        resampled = pd.DataFrame()
        resampled['Open'] = data['Open'].resample(freq).first()
        resampled['High'] = data['High'].resample(freq).max()
        resampled['Low'] = data['Low'].resample(freq).min()
        resampled['Close'] = data['Close'].resample(freq).last()

        if 'Volume' in data.columns:
            resampled['Volume'] = data['Volume'].resample(freq).sum()

        return resampled.dropna()

    def _close_position(
        self,
        strategy: OptionsStrategy,
        position: OptionsPosition,
        current_time: datetime,
        exit_reason: str,
        current_cash: float
    ) -> None:
        """Close a position and record the trade.

        Args:
            strategy: Strategy instance
            position: Position to close
            current_time: Exit timestamp
            exit_reason: Reason for exit
            current_cash: Current cash balance
        """
        strategy.close_position(position, current_time, exit_reason)

        # Record trade
        pnl = position.exit_value - position.entry_cost
        pnl_pct = (pnl / abs(position.entry_cost)) * 100 if position.entry_cost != 0 else 0

        trade_record = {
            'position_id': position.position_id,
            'spread_type': position.spread_type.value,
            'entry_time': position.entry_time,
            'exit_time': position.exit_time,
            'entry_cost': position.entry_cost,
            'exit_value': position.exit_value,
            'pnl': pnl,
            'pnl_percent': pnl_pct,
            'exit_reason': exit_reason,
            'duration_minutes': (position.exit_time - position.entry_time).total_seconds() / 60,
            'underlying_entry': position.underlying_price_at_entry,
        }

        self.trades.append(trade_record)

        if self.log_trades:
            self._log_position_exit(position, exit_reason, current_cash)

    def _format_time_et(self, dt: datetime) -> str:
        """Format datetime in Eastern Time for display."""
        et_tz = pytz.timezone('America/New_York')
        if dt.tzinfo is None:
            # Assume UTC if naive
            dt = pytz.UTC.localize(dt)
        dt_et = dt.astimezone(et_tz)
        return dt_et.strftime('%Y-%m-%d %H:%M:%S %Z')

    def _log_position_entry(self, position: OptionsPosition, cash_after: float) -> None:
        """Log position entry details."""
        print(f"\n  ✅ POSITION OPENED")
        print(f"     Position ID: {position.position_id}")
        print(f"     Spread Type: {position.spread_type.value}")
        print(f"     Entry Time: {self._format_time_et(position.entry_time)}")
        print(f"     Entry Cost: ${position.entry_cost:.2f}")
        print(f"     Underlying Price: ${position.underlying_price_at_entry:.2f}")
        print(f"     Cash Remaining: ${cash_after:,.2f}")

        # Log legs
        for i, leg in enumerate(position.legs, 1):
            action = "BUY" if leg.quantity > 0 else "SELL"
            print(f"     Leg {i}: {action} {abs(leg.quantity)} {leg.option_type.value} @ ${leg.strike_price:.2f} for ${leg.entry_price:.2f}")

    def _log_position_exit(self, position: OptionsPosition, exit_reason: str, cash_after: float) -> None:
        """Log position exit details."""
        pnl = position.exit_value - position.entry_cost
        pnl_pct = (pnl / abs(position.entry_cost)) * 100 if position.entry_cost != 0 else 0
        duration = (position.exit_time - position.entry_time).total_seconds() / 60

        emoji = "🟢" if pnl >= 0 else "🔴"
        print(f"\n  {emoji} POSITION CLOSED")
        print(f"     Position ID: {position.position_id}")
        print(f"     Exit Time: {self._format_time_et(position.exit_time)}")
        print(f"     Exit Reason: {exit_reason}")
        print(f"     Duration: {duration:.0f} minutes")
        print(f"     Entry Cost: ${position.entry_cost:.2f}")
        print(f"     Exit Value: ${position.exit_value:.2f}")
        print(f"     P&L: ${pnl:+.2f} ({pnl_pct:+.2f}%)")
        print(f"     Cash After: ${cash_after:,.2f}")

    def _calculate_results(self, strategy: OptionsStrategy, final_cash: float) -> None:
        """Calculate and store backtest results.

        Args:
            strategy: Strategy instance
            final_cash: Final cash balance
        """
        # Convert equity curve to DataFrame
        equity_df = pd.DataFrame(self.equity_curve)
        trades_df = pd.DataFrame(self.trades) if self.trades else pd.DataFrame()

        # Calculate metrics
        total_return = ((final_cash / self.initial_capital) - 1) * 100

        # Trade statistics
        num_trades = len(self.trades)
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        losing_trades = [t for t in self.trades if t['pnl'] < 0]

        win_rate = (len(winning_trades) / num_trades * 100) if num_trades > 0 else 0
        avg_win = np.mean([t['pnl'] for t in winning_trades]) if winning_trades else 0
        avg_loss = np.mean([t['pnl'] for t in losing_trades]) if losing_trades else 0

        # Equity curve stats
        if not equity_df.empty:
            equity_df['returns'] = equity_df['portfolio_value'].pct_change()

            # Drawdown calculation
            equity_df['cummax'] = equity_df['portfolio_value'].cummax()
            equity_df['drawdown'] = (equity_df['portfolio_value'] - equity_df['cummax']) / equity_df['cummax'] * 100
            max_drawdown = equity_df['drawdown'].min()

            # Sharpe ratio (annualized, assuming 252 trading days)
            if equity_df['returns'].std() > 0:
                sharpe_ratio = (equity_df['returns'].mean() / equity_df['returns'].std()) * np.sqrt(252 * 390)  # 390 minutes per day
            else:
                sharpe_ratio = 0
        else:
            max_drawdown = 0
            sharpe_ratio = 0

        self.results = {
            'strategy_name': strategy.name,
            'initial_capital': self.initial_capital,
            'final_capital': final_cash,
            'total_return': total_return,
            'total_return_pct': total_return,
            'num_trades': num_trades,
            'num_winning_trades': len(winning_trades),
            'num_losing_trades': len(losing_trades),
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': abs(avg_win / avg_loss) if avg_loss != 0 else 0,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'equity_curve': equity_df,
            'trades': trades_df,
            'positions': strategy.positions,
        }

        # Print summary
        print(f"\n{'='*70}")
        print(f"BACKTEST RESULTS")
        print(f"{'='*70}")
        print(f"Strategy: {strategy.name}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Final Capital: ${final_cash:,.2f}")
        print(f"Total Return: ${final_cash - self.initial_capital:+,.2f} ({total_return:+.2f}%)")
        print(f"\nTrade Statistics:")
        print(f"  Total Trades: {num_trades}")
        print(f"  Winning Trades: {len(winning_trades)} ({win_rate:.1f}%)")
        print(f"  Losing Trades: {len(losing_trades)}")
        print(f"  Average Win: ${avg_win:,.2f}")
        print(f"  Average Loss: ${avg_loss:,.2f}")
        print(f"  Profit Factor: {self.results['profit_factor']:.2f}")
        print(f"\nRisk Metrics:")
        print(f"  Max Drawdown: {max_drawdown:.2f}%")
        print(f"  Sharpe Ratio: {sharpe_ratio:.2f}")
        print(f"{'='*70}\n")