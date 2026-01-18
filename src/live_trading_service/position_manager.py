"""Position tracking and management for live trading engine."""

import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import defaultdict

from quant_vibe.logging import get_logger
from quant_vibe.strategies.options_base import OptionsPosition
from quant_vibe.utils import now_utc
from quant_vibe.utils.pnl_utils import PnLCalculator


def _to_native_type(value: Any) -> Any:
    """Convert numpy types to native Python types for database serialization."""
    if value is None:
        return None
    elif isinstance(value, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(value)
    elif isinstance(value, (np.floating, np.float64, np.float32, np.float16)):
        return float(value)
    elif isinstance(value, (np.bool_, bool)):
        return bool(value)
    elif isinstance(value, (np.str_, str)):
        return str(value)
    else:
        return value


class PositionManager:
    """Manages open positions and real-time P&L tracking."""

    def __init__(self, state_store=None):
        """Initialize position manager."""
        self.state_store = state_store
        self.logger = get_logger('live_trading')

        # Track open positions
        self.open_positions: Dict[str, OptionsPosition] = {}
        self.positions_by_strategy: Dict[str, List[str]] = defaultdict(list)

        # Track daily statistics
        self.daily_stats = {
            'opened_today': 0,
            'closed_today': 0,
            'total_pnl_today': 0.0,
            'wins_today': 0,
            'losses_today': 0,
        }

        # Capital tracking
        self.total_capital_deployed = 0.0

        self.logger.info("PositionManager initialized")

    def add_position(
        self,
        position: OptionsPosition,
        strategy_name: str,
        fill_price: float
    ) -> bool:
        """Add a newly opened position."""
        self.logger.debug(
            f"add_position() called: position_id={position.position_id}, "
            f"strategy={strategy_name}, fill_price=${fill_price:.2f}"
        )

        try:
            # Update position with actual fill
            position.entry_cost = fill_price
            position.current_value = fill_price

            # Track position
            self.open_positions[position.position_id] = position
            self.positions_by_strategy[strategy_name].append(position.position_id)
            self.logger.debug(f"Position tracked: {len(self.open_positions)} total open positions")

            # Update capital and stats
            self.total_capital_deployed += abs(fill_price)
            self.daily_stats['opened_today'] += 1

            # Persist to database
            self._persist_position(position, strategy_name)

            self.logger.info(
                f"Position added: {position.position_id} "
                f"Strategy: {strategy_name} "
                f"Cost: ${fill_price:.2f}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error adding position: {e}", exc_info=True)
            return False

    def update_position_values(self, options_data: Dict[str, Dict]):
        """Update all position values from current options quotes."""
        self.logger.debug(
            f"update_position_values() called: {len(self.open_positions)} positions, "
            f"{len(options_data)} option quotes"
        )

        for position in self.open_positions.values():
            try:
                new_value = self._calculate_position_value(position, options_data)
                position.current_value = new_value

                # Track highest value for valid (non-None) values
                if new_value is not None:
                    if position.highest_value is None or new_value > position.highest_value:
                        position.highest_value = new_value

            except Exception as e:
                self.logger.error(
                    f"Error updating position {position.position_id}: {e}",
                    exc_info=True
                )
                position.current_value = None

    def _calculate_position_value(
        self,
        position: OptionsPosition,
        options_data: Dict[str, Dict]
    ) -> Optional[float]:
        """Calculate current position value (exit value)."""
        value = 0.0
        missing_quotes = []

        for leg in position.legs:
            quote = options_data.get(leg.contract_symbol)

            if not quote:
                missing_quotes.append(leg.contract_symbol)
                continue

            # Determine exit price based on position direction
            if leg.quantity > 0:
                # Long position: sell at bid
                price = quote.get('bid', quote.get('close', 0))
            else:
                # Short position: buy at ask
                price = quote.get('ask', quote.get('close', 0))

            leg.current_price = price

            # Calculate exit value (cash flow from closing)
            if leg.quantity > 0:
                # Long: selling to close = positive (credit)
                value += price * abs(leg.quantity) * 100
            else:
                # Short: buying to close = negative (debit)
                value -= price * abs(leg.quantity) * 100

        if missing_quotes:
            self.logger.warning(
                f"Missing quotes for position {position.position_id}: {missing_quotes}"
            )
            return None

        return value

    def get_position_pnl(self, position_id: str) -> Optional[float]:
        """Get P&L for a position."""
        position = self.open_positions.get(position_id)
        if not position or position.current_value is None:
            return None

        result = PnLCalculator.calculate_unrealized_pnl(
            position.entry_cost,
            position.current_value
        )
        return result.pnl

    def get_position_pnl_pct(self, position_id: str) -> Optional[float]:
        """Get P&L percentage for a position."""
        position = self.open_positions.get(position_id)
        if not position or position.current_value is None:
            return None

        result = PnLCalculator.calculate_unrealized_pnl(
            position.entry_cost,
            position.current_value
        )
        return result.pnl_pct

    def close_position(
        self,
        position_id: str,
        exit_reason: str,
        exit_value: float
    ) -> bool:
        """Close a position."""
        position = self.open_positions.get(position_id)
        if not position:
            self.logger.error(f"Position {position_id} not found")
            return False

        try:
            # Update position
            position.exit_time = now_utc()
            position.exit_value = exit_value
            position.exit_reason = exit_reason

            # Calculate P&L
            pnl_result = PnLCalculator.calculate_realized_pnl(
                position.entry_cost,
                exit_value
            )

            # Update daily stats
            self.daily_stats['closed_today'] += 1
            self.daily_stats['total_pnl_today'] += pnl_result.pnl

            if pnl_result.is_winner:
                self.daily_stats['wins_today'] += 1
            else:
                self.daily_stats['losses_today'] += 1

            # Update capital
            self.total_capital_deployed -= abs(position.entry_cost)

            # Remove from tracking
            del self.open_positions[position_id]
            for strategy_positions in self.positions_by_strategy.values():
                if position_id in strategy_positions:
                    strategy_positions.remove(position_id)

            # Persist closure
            if self.state_store:
                self.state_store.close_position(
                    position_id=position_id,
                    exit_value=_to_native_type(exit_value),
                    exit_reason=exit_reason
                )

            self.logger.info(
                f"Position closed: {position_id} "
                f"Reason: {exit_reason} "
                f"P&L: {PnLCalculator.format_pnl_display(pnl_result.pnl, pnl_result.pnl_pct)}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Error closing position: {e}", exc_info=True)
            return False

    def get_open_positions(self, strategy_name: Optional[str] = None) -> List[OptionsPosition]:
        """Get open positions."""
        if strategy_name:
            position_ids = self.positions_by_strategy.get(strategy_name, [])
            return [
                self.open_positions[pid]
                for pid in position_ids
                if pid in self.open_positions
            ]
        return list(self.open_positions.values())

    def get_active_positions(self) -> List[OptionsPosition]:
        """Get all active positions (alias for compatibility)."""
        return self.get_open_positions()

    def get_position_count(self, strategy_name: Optional[str] = None) -> int:
        """Get count of open positions."""
        return len(self.get_open_positions(strategy_name))

    def get_total_pnl(self, strategy_name: Optional[str] = None) -> float:
        """Get total unrealized P&L for open positions."""
        positions = self.get_open_positions(strategy_name)
        total = 0.0

        for position in positions:
            pnl = self.get_position_pnl(position.position_id)
            if pnl is not None:
                total += pnl

        return total

    def get_daily_stats(self) -> Dict:
        """Get daily trading statistics."""
        return self.daily_stats.copy()

    def reset_daily_stats(self):
        """Reset daily statistics."""
        self.daily_stats = {
            'opened_today': 0,
            'closed_today': 0,
            'total_pnl_today': 0.0,
            'wins_today': 0,
            'losses_today': 0,
        }
        self.logger.info("Daily stats reset")

    def get_capital_usage(self) -> Dict:
        """Get capital usage statistics."""
        return {
            'total_deployed': self.total_capital_deployed,
            'num_positions': len(self.open_positions),
            'avg_per_position': (
                self.total_capital_deployed / len(self.open_positions)
                if self.open_positions else 0.0
            )
        }

    def reconcile_with_broker(self, broker_positions: List[Dict]) -> Dict:
        """Reconcile positions with broker (not yet implemented)."""
        self.logger.warning("Broker reconciliation not yet implemented")
        return {
            'status': 'not_implemented',
            'mismatches': [],
            'missing_local': [],
            'missing_broker': []
        }

    def _persist_position(
        self,
        position: OptionsPosition,
        strategy_name: str,
        account_hash: Optional[str] = None
    ):
        """Save position to state store."""
        if not self.state_store:
            return

        position_data = {
            'position_id': position.position_id,
            'strategy_name': strategy_name,
            'spread_type': position.spread_type.value,
            'entry_time': position.entry_time,
            'entry_cost': _to_native_type(position.entry_cost),
            'underlying_price_at_entry': _to_native_type(position.underlying_price_at_entry),
            'status': 'open',
            'current_value': _to_native_type(position.current_value),
            'account_hash': account_hash,
            'exit_time': None,
            'exit_value': None,
            'exit_reason': None,
            'legs': [
                {
                    'contract_symbol': leg.contract_symbol,
                    'option_type': leg.option_type.value,
                    'strike': _to_native_type(leg.strike_price),
                    'expiration': (
                        leg.expiration_date.strftime('%Y-%m-%d')
                        if isinstance(leg.expiration_date, datetime)
                        else str(leg.expiration_date)
                    ),
                    'quantity': _to_native_type(leg.quantity),
                    'entry_price': _to_native_type(leg.entry_price),
                }
                for leg in position.legs
            ],
            'metadata': {
                'profit_target_pct': _to_native_type(position.profit_target_pct),
                'stop_loss': _to_native_type(position.stop_loss),
                'trailing_stop': _to_native_type(position.trailing_stop),
            }
        }

        try:
            self.state_store.save_position(position_data)
        except Exception as e:
            self.logger.error(f"Failed to persist position: {e}")

    def load_open_positions_from_db(self):
        """Load open positions from database on startup."""
        if not self.state_store:
            return

        try:
            db_positions = self.state_store.get_open_positions()
            for pos_data in db_positions:
                self.logger.info(f"Loaded position from DB: {pos_data['position_id']}")
            self.logger.info(f"Loaded {len(db_positions)} positions from database")
        except Exception as e:
            self.logger.error(f"Error loading positions from DB: {e}", exc_info=True)