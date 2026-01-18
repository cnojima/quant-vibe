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
from datetime import datetime
import pandas as pd
import numpy as np
import pytz

from quant_vibe.strategies.options_base import OptionsStrategy, OptionsPosition
from quant_vibe.logging import get_logger
from quant_vibe.utils.pnl_utils import PnLCalculator

logger = get_logger(__name__)


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
        progress_callback: Optional[callable] = None,
    ) -> None:
        """
        Initialize options backtest engine.

        Args:
            initial_capital: Starting capital
            max_positions: Maximum concurrent positions (default: 1)
            log_trades: Whether to log trade entries/exits (default: True)
            progress_callback: Optional callback function(progress_pct, message, current_metrics)
        """
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.log_trades = log_trades
        self.progress_callback = progress_callback

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
        print(f"Options Contracts: {options_data['option_ticker'].nunique():,}")
        print(f"{'='*70}\n")

        # Initialize tracking
        cash = self.initial_capital
        current_day = None
        total_timestamps = len(timestamps)
        last_progress_report = 0

        # Main backtest loop - iterate through each timestamp
        for i, current_time in enumerate(timestamps):
            # Report progress every 5%
            progress_pct = (i / total_timestamps) * 100
            if progress_pct - last_progress_report >= 5.0 and self.progress_callback:
                portfolio_value = cash
                if strategy.active_position and strategy.active_position.current_value:
                    portfolio_value += strategy.active_position.current_value

                current_metrics = {
                    "timestamp": current_time.isoformat(),
                    "portfolio_value": float(portfolio_value),
                    "cash": float(cash),
                    "total_trades": len(self.trades),
                    "active_position": strategy.active_position is not None,
                }

                self.progress_callback(
                    progress_pct,
                    f"Processing {current_time.strftime('%Y-%m-%d %H:%M')}",
                    current_metrics
                )
                last_progress_report = progress_pct

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

                # Get current underlying price for intrinsic value calculation
                underlying_price = underlying_slice['close'].iloc[-1] if not underlying_slice.empty else None

                # Update position value (pass underlying_price for intrinsic value calculation)
                strategy.update_position_value(position, options_slice, underlying_price)

                # Check exit conditions
                should_exit, exit_reason = strategy.should_exit(
                    position,
                    underlying_slice,
                    options_slice,
                    current_time
                )

                if should_exit:
                    # Get current underlying price
                    underlying_price = underlying_slice['close'].iloc[-1] if not underlying_slice.empty else None

                    self._close_position(
                        strategy,
                        position,
                        current_time,
                        exit_reason,
                        cash,
                        underlying_price
                    )
                    # Update cash with exit value
                    # current_value is positive for debit spreads (we sell it)
                    # current_value is negative for credit spreads (we buy it back)
                    # So adding it works correctly for both cases
                    cash += float(position.exit_value)

            # Step 3: Check for new entry (if no active position)
            if strategy.active_position is None:
                if strategy.should_enter(
                    underlying_slice,
                    options_slice,
                    current_time,
                    market_analysis
                ):
                    # Construct spread - pass full options_data for completeness checks
                    new_position = strategy.construct_spread(
                        underlying_slice,
                        options_slice,
                        current_time,
                        market_analysis,
                        full_options_data=options_data  # Pass full dataset
                    )

                    if new_position is not None:
                        # Store entry trigger information
                        entry_trigger = self._format_entry_trigger(market_analysis)

                        # Check if we have enough capital
                        # For debit spreads: entry_cost > 0 (we pay)
                        # For credit spreads: entry_cost < 0 (we receive), but need to reserve max risk
                        if new_position.entry_cost >= 0:
                            # Debit spread - we pay entry_cost
                            required_capital = new_position.entry_cost
                        else:
                            # Credit spread - we receive credit but need to reserve max risk
                            # Max risk = spread_width * 100 * num_spreads
                            # For now, reserve the absolute value of entry cost as collateral
                            required_capital = abs(new_position.entry_cost)

                        if required_capital <= cash:
                            # Enter position
                            strategy.active_position = new_position
                            strategy.positions.append(new_position)
                            # Store entry trigger on position for later reference
                            new_position.entry_trigger = entry_trigger
                            # Update cash based on actual entry cost (negative = receive, positive = pay)
                            cash -= float(new_position.entry_cost)

                            if self.log_trades:
                                self._log_position_entry(new_position, cash)
                        else:
                            print(f"  ⚠️  Insufficient capital: need ${required_capital:.2f}, have ${cash:.2f}")

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
            print("\n⚠️  Closing position at end of backtest period")
            # Get final underlying price
            final_underlying_price = underlying_data['close'].iloc[-1] if not underlying_data.empty else None

            # Save position reference before closing (active_position will be set to None)
            position = strategy.active_position

            # Update position value with final market data before closing
            final_options_data = options_data[options_data.index == end_date]
            if not final_options_data.empty:
                strategy.update_position_value(position, final_options_data, final_underlying_price)

            self._close_position(
                strategy,
                position,
                end_date,
                "End of backtest",
                cash,
                final_underlying_price
            )
            cash += float(position.exit_value)

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
        resampled['open'] = data['open'].resample(freq).first()
        resampled['high'] = data['high'].resample(freq).max()
        resampled['low'] = data['low'].resample(freq).min()
        resampled['close'] = data['close'].resample(freq).last()

        if 'volume' in data.columns:
            resampled['volume'] = data['volume'].resample(freq).sum()

        return resampled.dropna()

    def _close_position(
        self,
        strategy: OptionsStrategy,
        position: OptionsPosition,
        current_time: datetime,
        exit_reason: str,
        current_cash: float,
        underlying_price: Optional[float] = None
    ) -> None:
        """Close a position and record the trade.

        Args:
            strategy: Strategy instance
            position: Position to close
            current_time: Exit timestamp
            exit_reason: Reason for exit
            current_cash: Current cash balance
            underlying_price: Current underlying price at exit
        """
        strategy.close_position(position, current_time, exit_reason, underlying_price)

        # Record trade
        # Handle case where exit_value is None (missing market data)
        if position.exit_value is None:
            # Use entry_cost as fallback (assume position closed at break-even)
            position.exit_value = position.entry_cost

        # Use centralized PnL calculator
        pnl_result = PnLCalculator.calculate_realized_pnl(
            position.entry_cost,
            position.exit_value
        )
        pnl = pnl_result.pnl
        pnl_pct = pnl_result.pnl_pct if pnl_result.pnl_pct is not None else 0.0

        # Build leg details for trade record
        leg_details = []
        for leg in position.legs:
            leg_info = {
                'action': 'BUY' if leg.quantity > 0 else 'SELL',
                'quantity': abs(leg.quantity),
                'contract_symbol': leg.contract_symbol,
                'option_type': leg.option_type.value,
                'strike_price': leg.strike_price,
                'entry_price': leg.entry_price,
                'exit_price': getattr(leg, 'exit_price', None),
                'expiration_date': leg.expiration_date
            }
            leg_details.append(leg_info)

        # Use Trade model field names (see src/quant_vibe/models/market_data.py)
        trade_record = {
            'trade_id': position.position_id,  # Use position_id as trade_id for now
            'position_id': position.position_id,
            'strategy_name': strategy.name,  # Add strategy name
            'spread_type': position.spread_type.value,
            'entry_time': position.entry_time,
            'exit_time': position.exit_time,
            'entry_premium': position.entry_cost,  # Renamed from entry_cost
            'exit_premium': position.exit_value,  # Renamed from exit_value
            'pnl': pnl,
            'pnl_pct': pnl_pct,  # Renamed from pnl_percent
            'entry_trigger': getattr(position, 'entry_trigger', 'N/A'),
            'exit_reason': exit_reason,
            'entry_underlying_price': position.underlying_price_at_entry,  # Renamed from underlying_entry
            'exit_underlying_price': getattr(position, 'underlying_price_at_exit', None),  # Renamed from underlying_exit
            'max_risk': abs(position.entry_cost),  # Add max_risk (entry cost for credit spreads)
            'legs': leg_details,
            'max_profit': getattr(position, 'max_profit', None),
            'peak_value': getattr(position, 'peak_value', None),
            # Deprecated fields for backward compatibility (can be removed after CSV migration)
            'duration_minutes': (position.exit_time - position.entry_time).total_seconds() / 60,
        }

        self.trades.append(trade_record)

        if self.log_trades:
            self._log_position_exit(position, exit_reason, current_cash)

    def _format_entry_trigger(self, market_analysis: Dict) -> str:
        """Format entry trigger information from market analysis.

        Args:
            market_analysis: Market analysis dict from strategy

        Returns:
            Human-readable entry trigger description
        """
        trigger_parts = []

        # Direction and momentum
        direction = market_analysis.get('direction', 'N/A')
        if direction != 'N/A':
            trigger_parts.append(f"{direction.capitalize()} direction")

        # Pullback signal
        if market_analysis.get('pullback_signal', False):
            current_price = market_analysis.get('current_price', 0)
            pullback_threshold = market_analysis.get('pullback_threshold', 0)
            if current_price > 0 and pullback_threshold > 0:
                pullback_amount = pullback_threshold - current_price
                trigger_parts.append(f"Pullback ${abs(pullback_amount):.2f}")

        # Observation complete
        if market_analysis.get('observation_complete', False):
            trigger_parts.append("Observation period complete")

        return " | ".join(trigger_parts) if trigger_parts else "Strategy entry signal"

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
        logger.debug("\n  ✅ POSITION OPENED")
        logger.debug(f"     Position ID: {position.position_id}")
        logger.debug(f"     Spread Type: {position.spread_type.value}")
        logger.debug(f"     Entry Time: {self._format_time_et(position.entry_time)}")
        logger.debug(f"     Entry Cost: ${position.entry_cost:.2f}")
        logger.debug(f"     Underlying Price: ${position.underlying_price_at_entry:.2f}")
        logger.debug(f"     Cash Remaining: ${cash_after:,.2f}")

        # Log legs
        for i, leg in enumerate(position.legs, 1):
            action = "BUY" if leg.quantity > 0 else "SELL"
            logger.debug(f"     Leg {i}: {action} {abs(leg.quantity)} {leg.option_type.value} @ ${leg.strike_price:.2f} for ${leg.entry_price:.2f}")

    def _log_position_exit(self, position: OptionsPosition, exit_reason: str, cash_after: float) -> None:
        """Log position exit details."""
        # Use centralized PnL calculator
        pnl_result = PnLCalculator.calculate_realized_pnl(
            position.entry_cost,
            position.exit_value
        )
        duration = (position.exit_time - position.entry_time).total_seconds() / 60

        emoji = "🟢" if pnl_result.is_winner else "🔴"
        logger.debug(f"\n  {emoji} POSITION CLOSED")
        logger.debug(f"     Position ID: {position.position_id}")
        logger.debug(f"     Exit Time: {self._format_time_et(position.exit_time)}")
        logger.debug(f"     Exit Reason: {exit_reason}")
        logger.debug(f"     Duration: {duration:.0f} minutes")
        logger.debug(f"     Entry Cost: ${position.entry_cost:.2f}")
        logger.debug(f"     Exit Value: ${position.exit_value:.2f}")
        logger.debug(f"     P&L: {PnLCalculator.format_pnl_display(pnl_result.pnl, pnl_result.pnl_pct)}")
        logger.debug(f"     Cash After: ${cash_after:,.2f}")

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

        # Trade statistics using centralized PnL aggregation
        pnl_stats = PnLCalculator.aggregate_pnl(self.trades)

        num_trades = pnl_stats['num_trades']
        win_rate = pnl_stats['win_rate']
        avg_win = pnl_stats['avg_win']
        avg_loss = pnl_stats['avg_loss']
        winning_trades = [t for t in self.trades if t['pnl'] > 0]
        losing_trades = [t for t in self.trades if t['pnl'] < 0]

        # Equity curve stats
        if not equity_df.empty:
            equity_df['returns'] = equity_df['portfolio_value'].pct_change()

            # Drawdown calculation using centralized calculator
            max_drawdown_value, max_drawdown = PnLCalculator.calculate_max_drawdown(
                equity_df['portfolio_value']
            )

            # Sharpe ratio using centralized calculator (390 minutes per day * 252 days)
            sharpe_ratio = PnLCalculator.calculate_sharpe_ratio(
                equity_df['returns'].dropna(),
                periods_per_year=252 * 390
            )
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
            'num_winning_trades': pnl_stats['num_winners'],
            'num_losing_trades': pnl_stats['num_losers'],
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': pnl_stats['profit_factor'],
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'equity_curve': equity_df,
            'trades': trades_df,
            'positions': strategy.positions,
        }

        # Print summary
        print(f"\n{'='*70}")
        print("BACKTEST RESULTS")
        print(f"{'='*70}")
        print(f"Strategy: {strategy.name}")
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Final Capital: ${final_cash:,.2f}")
        print(f"Total Return: ${final_cash - self.initial_capital:+,.2f} ({total_return:+.2f}%)")
        print("\nTrade Statistics:")
        print(f"  Total Trades: {num_trades}")
        print(f"  Winning Trades: {len(winning_trades)} ({win_rate:.1f}%)")
        print(f"  Losing Trades: {len(losing_trades)}")
        print(f"  Average Win: ${avg_win:,.2f}")
        print(f"  Average Loss: ${avg_loss:,.2f}")
        print(f"  Profit Factor: {self.results['profit_factor']:.2f}")
        print("\nRisk Metrics:")
        print(f"  Max Drawdown: {max_drawdown:.2f}%")
        print(f"  Sharpe Ratio: {sharpe_ratio:.2f}")
        print(f"{'='*70}\n")
