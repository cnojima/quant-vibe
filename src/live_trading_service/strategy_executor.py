"""Strategy execution for live trading.

Manages the execution of trading strategies on live streaming data.
Coordinates between strategies, order management, and position tracking.
"""

from datetime import datetime, time
from typing import Dict, List, Optional, Any
import pandas as pd
import pytz

from quant_vibe.logging import setup_normalized_logging, get_logger

# from quant_vibe.logging.unified_logging import get_logger
from quant_vibe.strategies.options_base import OptionsStrategy, OptionsPosition
from quant_vibe.notifications import TradingNotifier
from .order_manager import OrderManager
from .position_manager import PositionManager
from .state_store import StateStore

# logger = setup_normalized_logging(
#     app_name="live_trading_strategy",
# )
logger = get_logger('live_trading_strategy_executor')

class StrategyExecutor:
    """Executes trading strategies on live streaming data."""

    def __init__(
        self,
        strategies: List[OptionsStrategy],
        order_manager: OrderManager,
        position_manager: PositionManager,
        state_store: StateStore,
        underlying_ticker: str = "SPX",
        enabled: bool = True,
        notifier: Optional[TradingNotifier] = None,
    ):
        """
        Initialize strategy executor.

        Args:
            strategies: List of strategy instances to execute
            order_manager: Order manager for submitting orders
            position_manager: Position manager for tracking positions
            state_store: State store for persistence
            underlying_ticker: Underlying ticker symbol (default: SPX)
            enabled: Whether strategy execution is enabled (default: True)
            notifier: Trading notifier for push notifications (optional)
        """
        self.strategies = {strategy.name: strategy for strategy in strategies}
        self.order_manager = order_manager
        self.position_manager = position_manager
        self.state_store = state_store
        self.underlying_ticker = underlying_ticker
        self.enabled = enabled
        self.notifier = notifier

        # Track last bar time to detect new bars
        self.last_bar_time: Optional[datetime] = None

        # Track last daily reset time
        self.last_reset_date: Optional[datetime] = None

        # Track latest options data for exit orders
        self.latest_options_data: Dict[str, Dict] = {}

        # Strategy performance tracking
        self.strategy_stats: Dict[str, Dict[str, Any]] = {
            name: {
                'positions_opened': 0,
                'positions_closed': 0,
                'total_pnl': 0.0,
                'wins': 0,
                'losses': 0,
                'last_entry_time': None,
                'last_exit_time': None,
            }
            for name in self.strategies.keys()
        }

        logger.info(f"StrategyExecutor initialized with {len(self.strategies)} strategies")
        for name in self.strategies.keys():
            logger.info(f"  - {name}")

    def enable(self):
        """Enable strategy execution."""
        self.enabled = True
        logger.info("Strategy execution ENABLED")

    def disable(self):
        """Disable strategy execution."""
        self.enabled = False
        logger.info("Strategy execution DISABLED")

    def on_bar(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
    ):
        """
        Process a new bar of data.

        This is the main execution loop called on each new bar of streaming data.

        Args:
            underlying_data: OHLCV data for underlying (historical + current)
            options_data: Options chain data (current snapshot)
            current_time: Current timestamp
        """
        # logger.debug(f"on_bar() called: time={current_time}, enabled={self.enabled}, underlying_bars={len(underlying_data)}, options_contracts={len(options_data)}")

        # Skip if disabled
        if not self.enabled:
            logger.info("Skipping: strategy execution disabled")
            return

        # Skip if this is the same bar we already processed
        if self.last_bar_time == current_time:
            # logger.debug(f"Skipping: already processed bar at {current_time}")
            return

        self.last_bar_time = current_time
        logger.info(f"Processing new bar at {current_time}")

        # Update latest options data for exit orders
        # Convert DataFrame to dict format {option_ticker: {bid, ask, close, ...}}
        if not options_data.empty:
            options_dict = {}
            for _, row in options_data.iterrows():
                symbol = row.get('option_ticker')
                if symbol:
                    options_dict[symbol] = row.to_dict()
            self.latest_options_data = options_dict

        # Check for daily reset
        self._check_daily_reset(current_time)

        # Log bar received
        logger.debug(f"Processing bar at {current_time}")

        # Execute each strategy
        for strategy_name, strategy in self.strategies.items():
            try:
                self._execute_strategy(
                    strategy_name=strategy_name,
                    strategy=strategy,
                    underlying_data=underlying_data,
                    options_data=options_data,
                    current_time=current_time,
                )
            except Exception as e:
                logger.error(f"Error executing strategy {strategy_name}: {e}", exc_info=True)
                self.state_store.log_event(
                    event_type="strategy_error",
                    message=f"Error in {strategy_name}: {str(e)}",
                    severity="error",
                    strategy_name=strategy_name,
                )

    def _execute_strategy(
        self,
        strategy_name: str,
        strategy: OptionsStrategy,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
    ):
        """
        Execute a single strategy.

        Args:
            strategy_name: Name of the strategy
            strategy: Strategy instance
            underlying_data: OHLCV data for underlying
            options_data: Options chain data
            current_time: Current timestamp
        """
        logger.debug(f"Executing strategy: {strategy_name}, has_position={strategy.active_position is not None}")

        # Step 1: Analyze market
        market_analysis = strategy.analyze_market(
            underlying_data=underlying_data,
            options_data=options_data,
            current_time=current_time,
        )
        logger.debug(f"{strategy_name} market analysis: {market_analysis}")

        # Step 2: Check for entry signals
        if strategy.active_position is None:
            should_enter = strategy.should_enter(
                underlying_data=underlying_data,
                options_data=options_data,
                current_time=current_time,
                market_analysis=market_analysis,
            )
            logger.debug(f"{strategy_name} entry check: should_enter={should_enter}")

            if should_enter:
                self._handle_entry(
                    strategy_name=strategy_name,
                    strategy=strategy,
                    underlying_data=underlying_data,
                    options_data=options_data,
                    current_time=current_time,
                    market_analysis=market_analysis,
                )

        # Step 3: Check for exit signals on active positions
        else:
            should_exit, exit_reason = strategy.should_exit(
                position=strategy.active_position,
                underlying_data=underlying_data,
                options_data=options_data,
                current_time=current_time,
            )
            logger.debug(f"{strategy_name} exit check: should_exit={should_exit}, reason={exit_reason}")

            if should_exit:
                self._handle_exit(
                    strategy_name=strategy_name,
                    strategy=strategy,
                    position=strategy.active_position,
                    exit_reason=exit_reason,
                    current_time=current_time,
                )

    def _handle_entry(
        self,
        strategy_name: str,
        strategy: OptionsStrategy,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        market_analysis: Dict,
    ):
        """
        Handle entry signal.

        Args:
            strategy_name: Name of the strategy
            strategy: Strategy instance
            underlying_data: OHLCV data for underlying
            options_data: Options chain data
            current_time: Current timestamp
            market_analysis: Market analysis from strategy
        """
        logger.info(f"[{strategy_name}] Entry signal at {current_time}")

        # Construct spread
        position = strategy.construct_spread(
            underlying_data=underlying_data,
            options_data=options_data,
            current_time=current_time,
            market_analysis=market_analysis,
            full_options_data=options_data,  # Pass full dataset for validation
        )

        if position is None:
            logger.warning(f"[{strategy_name}] Failed to construct spread")
            self.state_store.log_event(
                event_type="entry_failed",
                message="Failed to construct spread",
                severity="warning",
                strategy_name=strategy_name,
            )
            return

        # Convert options_data DataFrame to dict format for order manager
        # Format: {symbol: {bid, ask, ...}}
        options_dict = {}
        for _, row in options_data.iterrows():
            symbol = row.get('option_ticker')
            if symbol:
                options_dict[symbol] = row.to_dict()

        # Pre-register position in database BEFORE submitting order
        # This ensures foreign key constraint is satisfied when order is persisted
        self.position_manager.add_position(
            position=position,
            strategy_name=strategy_name,
            fill_price=position.entry_cost,  # Initial value, will be updated after fill
        )

        # Submit order
        success, message, order = self.order_manager.submit_position_entry(
            position=position,
            options_data=options_dict,
            strategy_name=strategy_name,
        )

        if not success:
            logger.error(f"[{strategy_name}] Order submission failed: {message}")
            # Remove the position since order failed
            self.position_manager.close_position(
                position_id=position.position_id,
                exit_reason="order_failed",
                exit_value=0.0
            )
            self.state_store.log_event(
                event_type="order_failed",
                message=f"Order submission failed: {message}",
                severity="error",
                strategy_name=strategy_name,
            )
            return

        # Update position with actual fill price from order
        if order and order.filled_total_price:
            position.entry_cost = order.filled_total_price
            position.current_value = order.filled_total_price
            # Re-persist with updated fill price
            self.position_manager._persist_position(position, strategy_name)

        # Update strategy state
        strategy.active_position = position
        strategy.positions.append(position)

        # Update stats
        self.strategy_stats[strategy_name]['positions_opened'] += 1
        self.strategy_stats[strategy_name]['last_entry_time'] = current_time

        # Log event
        self.state_store.log_event(
            event_type="position_opened",
            message=f"Opened position {position.position_id}",
            severity="info",
            strategy_name=strategy_name,
            position_id=position.position_id,
            details={
                'entry_cost': float(position.entry_cost),
                'underlying_price': float(position.underlying_price_at_entry),
                'spread_type': position.spread_type.value,
                'num_legs': len(position.legs),
            }
        )

        logger.info(
            f"[{strategy_name}] Position opened: {position.position_id}, "
            f"Cost: ${position.entry_cost:.2f}"
        )

        # Send notification
        if self.notifier:
            try:
                self.notifier.on_position_opened(
                    strategy=strategy_name,
                    symbol=position.position_id,
                    entry_price=position.entry_cost,
                    metadata={
                        'underlying_price': position.underlying_price_at_entry,
                        'spread_type': position.spread_type.value,
                        'num_legs': len(position.legs),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send position opened notification: {e}")

    def _handle_exit(
        self,
        strategy_name: str,
        strategy: OptionsStrategy,
        position: OptionsPosition,
        exit_reason: Optional[str],
        current_time: datetime,
    ):
        """
        Handle exit signal.

        Args:
            strategy_name: Name of the strategy
            strategy: Strategy instance
            position: Position to exit
            exit_reason: Reason for exit
            current_time: Current timestamp
        """
        logger.info(f"[{strategy_name}] Exit signal for {position.position_id}: {exit_reason}")

        # Submit exit order
        success, message, order = self.order_manager.submit_position_exit(
            position=position,
            options_data=self.latest_options_data,
            strategy_name=strategy_name,
        )

        if not success or order is None:
            logger.error(f"[{strategy_name}] Exit order submission failed: {message}")
            self.state_store.log_event(
                event_type="exit_order_failed",
                message=f"Exit order failed for {position.position_id}: {message}",
                severity="error",
                strategy_name=strategy_name,
                position_id=position.position_id,
            )
            return

        # Update position with exit details
        # NOTE: filled_total_price uses accounting convention (sell = negative),
        # but exit_value needs to be positive for P&L calculation (exit_value - entry_cost)
        # For closing a long position (selling), we negate to get positive value
        # For closing a short position (buying), we negate to get negative value
        position.exit_value = -order.filled_total_price
        position.exit_time = current_time
        position.exit_reason = exit_reason

        # Close position
        self.position_manager.close_position(
            position_id=position.position_id,
            exit_value=position.exit_value,
            exit_reason=exit_reason,
        )

        # Update strategy state
        strategy.active_position = None

        # Calculate P&L
        pnl = position.pnl
        is_win = bool(pnl > 0 if pnl is not None else False)

        # Update stats
        self.strategy_stats[strategy_name]['positions_closed'] += 1
        self.strategy_stats[strategy_name]['total_pnl'] += pnl if pnl else 0.0
        self.strategy_stats[strategy_name]['last_exit_time'] = current_time
        if is_win:
            self.strategy_stats[strategy_name]['wins'] += 1
        else:
            self.strategy_stats[strategy_name]['losses'] += 1

        # Log event
        self.state_store.log_event(
            event_type="position_closed",
            message=f"Closed position {position.position_id}: {exit_reason}",
            severity="info",
            strategy_name=strategy_name,
            position_id=position.position_id,
            details={
                'entry_cost': float(position.entry_cost),
                'exit_value': float(position.exit_value),
                'pnl': float(pnl) if pnl else 0.0,
                'pnl_percent': float(position.pnl_percent) if position.pnl_percent else 0.0,
                'exit_reason': str(exit_reason),
                'is_win': is_win,
            }
        )

        logger.info(
            f"[{strategy_name}] Position closed: {position.position_id}, "
            f"P&L: ${pnl:.2f} ({position.pnl_percent*100:.1f}%), "
            f"Reason: {exit_reason}"
        )

        # Send notification
        if self.notifier:
            try:
                pnl_pct = position.pnl_percent if position.pnl_percent else 0.0
                self.notifier.on_position_closed(
                    strategy=strategy_name,
                    symbol=position.position_id,
                    pnl=pnl if pnl else 0.0,
                    pnl_pct=pnl_pct,
                    metadata={
                        'entry_cost': position.entry_cost,
                        'exit_value': position.exit_value,
                        'exit_reason': exit_reason,
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to send position closed notification: {e}")

    def _check_daily_reset(self, current_time: datetime):
        """
        Check if we need to reset daily state.

        Resets at market open (9:30 AM ET).

        Args:
            current_time: Current timestamp
        """
        # Convert to ET
        et_tz = pytz.timezone('America/New_York')
        if current_time.tzinfo is None:
            current_time_et = pytz.UTC.localize(current_time).astimezone(et_tz)
        else:
            current_time_et = current_time.astimezone(et_tz)

        current_date = current_time_et.date()

        # Check if this is a new trading day
        if self.last_reset_date is None or current_date != self.last_reset_date:
            # Check if we're past market open (9:30 AM ET)
            market_open = time(9, 30)
            if current_time_et.time() >= market_open:
                self._perform_daily_reset(current_date)

    def _perform_daily_reset(self, current_date):
        """
        Perform daily reset for all strategies.

        Args:
            current_date: Current date
        """
        logger.info(f"Performing daily reset for {current_date}")

        for strategy_name, strategy in self.strategies.items():
            # Reset strategy state
            strategy.reset_daily_state()

            # Save to database
            self.state_store.reset_strategy_state(strategy_name)

            logger.info(f"  - Reset {strategy_name}")

        self.last_reset_date = current_date

        # Log event
        self.state_store.log_event(
            event_type="daily_reset",
            message=f"Daily reset completed for {current_date}",
            severity="info",
        )

    def get_strategy_stats(self, strategy_name: Optional[str] = None) -> Dict:
        """
        Get performance statistics for strategies.

        Args:
            strategy_name: Name of strategy (None for all strategies)

        Returns:
            Dictionary of statistics
        """
        if strategy_name:
            return self.strategy_stats.get(strategy_name, {})
        return self.strategy_stats

    def get_active_positions(self) -> List[OptionsPosition]:
        """
        Get all active positions across all strategies.

        Returns:
            List of active positions
        """
        positions = []
        for strategy in self.strategies.values():
            if strategy.active_position is not None:
                positions.append(strategy.active_position)
        return positions

    def update_strategies(self, new_strategies: List[OptionsStrategy]):
        """
        Update the strategy list without closing existing positions.

        This allows hot-reloading of strategies from config changes.
        Existing positions are preserved and transferred to matching strategies.

        Args:
            new_strategies: New list of strategy instances

        Note:
            - Strategies with active positions are preserved
            - New strategies are added
            - Removed strategies are gracefully handled (positions kept)
        """
        logger.info(f"Updating strategies (current: {len(self.strategies)}, new: {len(new_strategies)})")

        # Build new strategy dict
        new_strategy_dict = {strategy.name: strategy for strategy in new_strategies}

        # Transfer active positions from old strategies to new ones
        for old_name, old_strategy in self.strategies.items():
            if old_strategy.active_position is not None:
                if old_name in new_strategy_dict:
                    # Strategy still exists, transfer position
                    logger.info(f"  Transferring active position from {old_name}")
                    new_strategy_dict[old_name].active_position = old_strategy.active_position
                    new_strategy_dict[old_name].positions = old_strategy.positions
                else:
                    # Strategy removed but has active position - keep old strategy instance
                    logger.warning(f"  Keeping removed strategy {old_name} (has active position)")
                    new_strategy_dict[old_name] = old_strategy

        # Update strategies
        self.strategies = new_strategy_dict

        # Update stats for new strategies
        for name in new_strategy_dict.keys():
            if name not in self.strategy_stats:
                self.strategy_stats[name] = {
                    'positions_opened': 0,
                    'positions_closed': 0,
                    'total_pnl': 0.0,
                    'wins': 0,
                    'losses': 0,
                    'last_entry_time': None,
                    'last_exit_time': None,
                }

        logger.info(f"  Strategies updated: {list(self.strategies.keys())}")

    def force_close_all_positions(self, reason: str = "Manual close"):
        """
        Force close all active positions.

        Args:
            reason: Reason for closing positions
        """
        logger.warning(f"Force closing all positions: {reason}")

        current_time = datetime.now(pytz.UTC)

        for strategy_name, strategy in self.strategies.items():
            if strategy.active_position is not None:
                self._handle_exit(
                    strategy_name=strategy_name,
                    strategy=strategy,
                    position=strategy.active_position,
                    exit_reason=reason,
                    current_time=current_time,
                )

        logger.info("All positions closed")
