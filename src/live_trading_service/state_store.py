"""State persistence for live trading engine."""

import os
import json
from typing import Dict, List, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import numpy as np

from quant_vibe.utils import now_utc
from quant_vibe.logging import get_logger

load_dotenv()


def _json_serialize_safe(obj: Any) -> Any:
    """Convert numpy types to native Python types for JSON serialization."""
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, dict):
        return {k: _json_serialize_safe(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_json_serialize_safe(i) for i in obj]
    else:
        return obj


class StateStore:
    """Manages persistence of trading engine state."""

    def __init__(
        self,
        db_config: Optional[Dict] = None,
        db_profile: Optional[str] = None,
        trading_mode: Optional[str] = None
    ):
        """Initialize state store.

        Args:
            db_config: Database configuration
            db_profile: Database profile ('local' or 'remote')
            trading_mode: Trading mode ('real', 'paper', or None for legacy)
        """
        self._validate_trading_mode(trading_mode)
        self.trading_mode = trading_mode
        self.logger = get_logger('live_trading')

        self._setup_schema()
        self._connect_database(db_config, db_profile)

        if not trading_mode:
            self._ensure_tables_exist()

    def _validate_trading_mode(self, trading_mode: Optional[str]) -> None:
        """Validate trading mode parameter."""
        if trading_mode and trading_mode not in ['real', 'paper']:
            raise ValueError(f"Invalid trading_mode: {trading_mode}. Must be 'real' or 'paper'")

    def _setup_schema(self) -> None:
        """Set up schema and table prefix based on trading mode."""
        if self.trading_mode:
            self.schema = f"{self.trading_mode}_trading"
            self.table_prefix = ""
        else:
            self.schema = "public"
            self.table_prefix = "live_"

    def _get_db_config(self, db_profile: Optional[str]) -> Dict:
        """Get database configuration from environment."""
        use_remote = os.getenv('USE_REMOTE_TIMESCALE', 'false').lower() == 'true'

        if db_profile == 'remote':
            use_remote = True
        elif db_profile == 'local':
            use_remote = False

        if use_remote:
            config = {
                'host': os.getenv('REMOTE_TIMESCALE_HOST', '192.168.100.197'),
                'port': int(os.getenv('REMOTE_TIMESCALE_PORT', '5432')),
                'database': os.getenv('REMOTE_TIMESCALE_DB', 'options_data'),
                'user': os.getenv('REMOTE_TIMESCALE_USER', 'quantvibe'),
                'password': os.getenv('REMOTE_TIMESCALE_PASSWORD', 'quantvibe_dev')
            }
            print(f"Using REMOTE TimescaleDB: {config['host']}:{config['port']}")
        else:
            config = {
                'host': os.getenv('TIMESCALE_HOST', 'localhost'),
                'port': int(os.getenv('TIMESCALE_PORT', '5432')),
                'database': os.getenv('TIMESCALE_DB', 'options_data'),
                'user': os.getenv('TIMESCALE_USER', 'quantvibe'),
                'password': os.getenv('TIMESCALE_PASSWORD', 'quantvibe_dev')
            }
            print(f"Using LOCAL TimescaleDB: {config['host']}:{config['port']}")

        return config

    def _connect_database(self, db_config: Optional[Dict], db_profile: Optional[str]) -> None:
        """Connect to database."""
        if db_config is None:
            db_config = self._get_db_config(db_profile)

        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        if self.trading_mode:
            self.cursor.execute(f"SET search_path TO {self.schema}, public")
            self.conn.commit()
            print(f"Using schema: {self.schema} (trading_mode={self.trading_mode})")

    def _ensure_tables_exist(self):
        """Create tables for state persistence if they don't exist."""
        # Table definitions
        tables = [
            # Engine state table
            f"""CREATE TABLE IF NOT EXISTS {self.table_prefix}engine_state (
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                id SERIAL PRIMARY KEY,
                state TEXT NOT NULL,
                metadata JSONB,
                UNIQUE(timestamp)
            )""",

            # Positions table
            f"""CREATE TABLE IF NOT EXISTS {self.table_prefix}positions (
                position_id TEXT PRIMARY KEY,
                strategy_name TEXT NOT NULL,
                spread_type TEXT NOT NULL,
                entry_time TIMESTAMPTZ NOT NULL,
                entry_cost NUMERIC NOT NULL,
                underlying_price_at_entry NUMERIC NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                current_value NUMERIC,
                exit_time TIMESTAMPTZ,
                exit_value NUMERIC,
                exit_reason TEXT,
                legs JSONB NOT NULL,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""",

            # Orders table
            f"""CREATE TABLE IF NOT EXISTS {self.table_prefix}orders (
                order_id TEXT PRIMARY KEY,
                position_id TEXT REFERENCES {self.table_prefix}positions(position_id),
                strategy_name TEXT NOT NULL,
                order_type TEXT NOT NULL,
                action_type TEXT,
                side TEXT NOT NULL,
                quantity INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                submitted_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                filled_time TIMESTAMPTZ,
                expected_price NUMERIC,
                filled_price NUMERIC,
                filled_quantity INTEGER,
                broker_order_id TEXT,
                error_message TEXT,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""",

            # Strategy state table
            f"""CREATE TABLE IF NOT EXISTS {self.table_prefix}strategy_state (
                strategy_name TEXT PRIMARY KEY,
                state JSONB NOT NULL,
                last_reset TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )""",

            # Events table (with hypertable support)
            f"""CREATE TABLE IF NOT EXISTS {self.table_prefix}events (
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                id SERIAL,
                event_type TEXT NOT NULL,
                strategy_name TEXT,
                position_id TEXT,
                order_id TEXT,
                severity TEXT NOT NULL DEFAULT 'info',
                message TEXT NOT NULL,
                details JSONB,
                PRIMARY KEY (timestamp, id)
            )"""
        ]

        # Create tables
        for table_sql in tables:
            self.cursor.execute(table_sql)
        self.conn.commit()

        # Create indexes
        indexes = [
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}positions_status ON {self.table_prefix}positions(status, strategy_name)",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}events_strategy ON {self.table_prefix}events(strategy_name, timestamp DESC)",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}events_position ON {self.table_prefix}events(position_id, timestamp DESC)",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}events_severity ON {self.table_prefix}events(severity, timestamp DESC)",
            f"CREATE INDEX IF NOT EXISTS idx_{self.table_prefix}events_type ON {self.table_prefix}events(event_type, timestamp DESC)"
        ]

        for index_sql in indexes:
            self.cursor.execute(index_sql)
        self.conn.commit()

        # Try to create hypertable for events (requires TimescaleDB)
        try:
            self.cursor.execute(f"""
                SELECT create_hypertable('{self.table_prefix}events', 'timestamp',
                    migrate_data => TRUE,
                    if_not_exists => TRUE)
            """)
            self.conn.commit()
        except Exception:
            self.conn.rollback()

    # Engine State
    def save_engine_state(self, state: str, metadata: Optional[Dict] = None):
        """Save current engine state."""
        try:
            self.cursor.execute(f"""
                INSERT INTO {self.table_prefix}engine_state (timestamp, state, metadata)
                VALUES (NOW(), %s, %s)
                ON CONFLICT (timestamp) DO UPDATE
                SET state = EXCLUDED.state, metadata = EXCLUDED.metadata
            """, (state, json.dumps(metadata) if metadata else None))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_latest_engine_state(self) -> Optional[Dict]:
        """Get the most recent engine state."""
        self.cursor.execute(f"""
            SELECT * FROM {self.table_prefix}engine_state
            ORDER BY timestamp DESC
            LIMIT 1
        """)
        return self.cursor.fetchone()

    # Positions
    def save_position(self, position_data: Dict):
        """Save or update a position."""
        try:
            params = {
                'position_id': position_data['position_id'],
                'strategy_name': position_data['strategy_name'],
                'spread_type': position_data['spread_type'],
                'entry_time': position_data['entry_time'],
                'entry_cost': position_data['entry_cost'],
                'underlying_price_at_entry': position_data['underlying_price_at_entry'],
                'status': position_data.get('status', 'open'),
                'current_value': position_data.get('current_value'),
                'exit_time': position_data.get('exit_time'),
                'exit_value': position_data.get('exit_value'),
                'exit_reason': position_data.get('exit_reason'),
                'legs': json.dumps(position_data['legs']),
                'metadata': json.dumps(position_data.get('metadata', {})),
                'account_hash': position_data.get('account_hash')
            }

            self.cursor.execute(f"""
                INSERT INTO {self.table_prefix}positions (
                    position_id, strategy_name, spread_type, entry_time,
                    entry_cost, underlying_price_at_entry, status,
                    current_value, exit_time, exit_value, exit_reason,
                    legs, metadata, account_hash
                ) VALUES (
                    %(position_id)s, %(strategy_name)s, %(spread_type)s, %(entry_time)s,
                    %(entry_cost)s, %(underlying_price_at_entry)s, %(status)s,
                    %(current_value)s, %(exit_time)s, %(exit_value)s, %(exit_reason)s,
                    %(legs)s, %(metadata)s, %(account_hash)s
                )
                ON CONFLICT (position_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    current_value = EXCLUDED.current_value,
                    exit_time = EXCLUDED.exit_time,
                    exit_value = EXCLUDED.exit_value,
                    exit_reason = EXCLUDED.exit_reason,
                    legs = EXCLUDED.legs,
                    metadata = EXCLUDED.metadata,
                    account_hash = COALESCE(EXCLUDED.account_hash, {self.table_prefix}positions.account_hash),
                    updated_at = NOW()
                WHERE {self.table_prefix}positions.status != 'closed' OR EXCLUDED.status = 'closed'
            """, params)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_open_positions(self, strategy_name: Optional[str] = None) -> List[Dict]:
        """Get all open positions."""
        if strategy_name:
            self.cursor.execute(f"""
                SELECT * FROM {self.table_prefix}positions
                WHERE status = 'open' AND strategy_name = %s
                ORDER BY entry_time DESC
            """, (strategy_name,))
        else:
            self.cursor.execute(f"""
                SELECT * FROM {self.table_prefix}positions
                WHERE status = 'open'
                ORDER BY entry_time DESC
            """)
        return self.cursor.fetchall()

    def get_all_positions(self) -> List[Dict]:
        """Get all open positions."""
        return self.get_open_positions()

    def close_position(self, position_id: str, exit_value: float, exit_reason: str):
        """Mark a position as closed."""
        try:
            self.cursor.execute(f"""
                UPDATE {self.table_prefix}positions
                SET status = 'closed',
                    exit_time = NOW(),
                    exit_value = %s,
                    exit_reason = %s,
                    updated_at = NOW()
                WHERE position_id = %s
            """, (exit_value, exit_reason, position_id))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def remove_position(self, position_id: str):
        """Remove a position from the database."""
        try:
            self.cursor.execute(f"""
                DELETE FROM {self.table_prefix}positions
                WHERE position_id = %s
            """, (position_id,))
            self.conn.commit()
            self.logger.info(f"Removed position {position_id} from database")
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"Failed to remove position {position_id}: {e}")
            raise

    def get_trades_for_date(self, trade_date, account_hash: Optional[str] = None) -> List[Dict]:
        """Get all closed trades for a specific date."""
        query = f"""
            SELECT
                position_id,
                strategy_name as strategy,
                entry_time,
                exit_time,
                entry_cost,
                exit_value,
                (exit_value - entry_cost) as pnl,
                exit_reason,
                legs,
                metadata,
                account_hash
            FROM {self.table_prefix}positions
            WHERE status = 'closed'
              AND DATE(exit_time) = %s
        """

        params = [trade_date]
        if account_hash:
            query += " AND account_hash = %s"
            params.append(account_hash)

        query += " ORDER BY exit_time ASC"
        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    # Orders
    def clear_broker_sync_orders(self):
        """Clear orders that were synced from broker."""
        try:
            self.cursor.execute(f"""
                DELETE FROM {self.table_prefix}orders
                WHERE strategy_name = 'broker_sync'
            """)
            deleted_count = self.cursor.rowcount
            self.conn.commit()
            return deleted_count
        except Exception:
            self.conn.rollback()
            raise

    def save_order(self, order_data: Dict):
        """Save or update an order."""
        try:
            params = {
                'order_id': order_data.get('order_id', f"unknown_{now_utc().timestamp()}"),
                'position_id': order_data.get('position_id'),
                'strategy_name': order_data.get('strategy_name', 'broker_sync'),
                'order_type': order_data.get('order_type', 'LIMIT'),
                'action_type': order_data.get('action_type', 'opening'),
                'side': order_data.get('side', 'BUY'),
                'quantity': order_data.get('quantity', 1),
                'symbol': order_data.get('symbol', 'UNKNOWN'),
                'status': order_data.get('status', 'pending'),
                'submitted_time': order_data.get('submitted_time', now_utc()),
                'filled_time': order_data.get('filled_time'),
                'expected_price': order_data.get('expected_price'),
                'filled_price': order_data.get('filled_price'),
                'broker_order_id': order_data.get('broker_order_id'),
                'metadata': json.dumps(order_data.get('metadata', {}))
            }

            self.cursor.execute(f"""
                INSERT INTO {self.table_prefix}orders (
                    order_id, position_id, strategy_name, order_type, action_type, side,
                    quantity, symbol, status, submitted_time, filled_time, expected_price,
                    filled_price, broker_order_id, metadata
                ) VALUES (
                    %(order_id)s, %(position_id)s, %(strategy_name)s, %(order_type)s,
                    %(action_type)s, %(side)s, %(quantity)s, %(symbol)s, %(status)s,
                    %(submitted_time)s, %(filled_time)s, %(expected_price)s,
                    %(filled_price)s, %(broker_order_id)s, %(metadata)s
                )
                ON CONFLICT (order_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    action_type = EXCLUDED.action_type,
                    filled_time = COALESCE(EXCLUDED.filled_time, {self.table_prefix}orders.filled_time),
                    filled_price = COALESCE(EXCLUDED.filled_price, {self.table_prefix}orders.filled_price),
                    filled_quantity = COALESCE(EXCLUDED.filled_quantity, {self.table_prefix}orders.filled_quantity),
                    error_message = COALESCE(EXCLUDED.error_message, {self.table_prefix}orders.error_message),
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
            """, params)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def update_order_status(
        self,
        order_id: str,
        status: str,
        filled_price: Optional[float] = None,
        filled_quantity: Optional[int] = None,
        error_message: Optional[str] = None
    ):
        """Update order status."""
        try:
            self.cursor.execute(f"""
                UPDATE {self.table_prefix}orders
                SET status = %s,
                    filled_time = CASE WHEN %s IN ('filled', 'partially_filled')
                                  THEN NOW() ELSE filled_time END,
                    filled_price = COALESCE(%s, filled_price),
                    filled_quantity = COALESCE(%s, filled_quantity),
                    error_message = COALESCE(%s, error_message),
                    updated_at = NOW()
                WHERE order_id = %s
            """, (status, status, filled_price, filled_quantity, error_message, order_id))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # Strategy State
    def save_strategy_state(self, strategy_name: str, state: Dict):
        """Save strategy-specific state."""
        try:
            self.cursor.execute(f"""
                INSERT INTO {self.table_prefix}strategy_state (strategy_name, state, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (strategy_name) DO UPDATE
                SET state = EXCLUDED.state, updated_at = NOW()
            """, (strategy_name, json.dumps(state)))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_strategy_state(self, strategy_name: str) -> Optional[Dict]:
        """Get strategy state."""
        self.cursor.execute(f"""
            SELECT state FROM {self.table_prefix}strategy_state
            WHERE strategy_name = %s
        """, (strategy_name,))
        result = self.cursor.fetchone()
        return result['state'] if result else None

    def get_all_strategy_states(self) -> List[Dict]:
        """Get all strategy states."""
        self.cursor.execute(f"""
            SELECT * FROM {self.table_prefix}strategy_state
            ORDER BY strategy_name
        """)
        return self.cursor.fetchall()

    def reset_strategy_state(self, strategy_name: str):
        """Reset strategy state for daily reset."""
        try:
            self.cursor.execute(f"""
                UPDATE {self.table_prefix}strategy_state
                SET state = '{{}}', last_reset = NOW(), updated_at = NOW()
                WHERE strategy_name = %s
            """, (strategy_name,))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # Events / Audit Log
    def log_event(
        self,
        event_type: str,
        message: str,
        severity: str = 'info',
        strategy_name: Optional[str] = None,
        position_id: Optional[str] = None,
        order_id: Optional[str] = None,
        details: Optional[Dict] = None
    ):
        """Log an event to the audit trail."""
        try:
            details_json = None
            if details:
                safe_details = _json_serialize_safe(details)
                details_json = json.dumps(safe_details)

            self.cursor.execute(f"""
                INSERT INTO {self.table_prefix}events (
                    timestamp, event_type, strategy_name, position_id, order_id,
                    severity, message, details
                ) VALUES (
                    NOW(), %s, %s, %s, %s, %s, %s, %s
                )
            """, (
                event_type, strategy_name, position_id, order_id,
                severity, message, details_json
            ))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def get_recent_events(
        self,
        limit: int = 100,
        severity: Optional[str] = None,
        strategy_name: Optional[str] = None
    ) -> List[Dict]:
        """Get recent events from audit log."""
        query = f"SELECT * FROM {self.table_prefix}events WHERE 1=1"
        params = []

        if severity:
            query += " AND severity = %s"
            params.append(severity)

        if strategy_name:
            query += " AND strategy_name = %s"
            params.append(strategy_name)

        query += " ORDER BY timestamp DESC LIMIT %s"
        params.append(limit)

        self.cursor.execute(query, params)
        return self.cursor.fetchall()

    # Account Balance (for trading mode schemas)
    def get_account_balance(self, account_hash: Optional[str] = None) -> Optional[Dict]:
        """Get current account balance for this trading mode."""
        if not self.trading_mode:
            return None

        if account_hash:
            query = f"""
                SELECT * FROM {self.table_prefix}account_balance
                WHERE account_hash = %s
                ORDER BY timestamp DESC
                LIMIT 1
            """
            params = [account_hash]
        else:
            query = f"""
                SELECT ab.* FROM {self.table_prefix}account_balance ab
                JOIN {self.table_prefix}broker_accounts ba ON ab.account_hash = ba.account_hash
                WHERE ba.is_default = TRUE
                ORDER BY ab.timestamp DESC
                LIMIT 1
            """
            params = []

        self.cursor.execute(query, params)
        result = self.cursor.fetchone()

        if not result:
            # Try to get any balance (backwards compatibility)
            self.cursor.execute(f"""
                SELECT * FROM {self.table_prefix}account_balance
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            result = self.cursor.fetchone()

        return result

    def update_account_balance(
        self,
        cash: float,
        portfolio_value: float,
        account_hash: Optional[str] = None,
        daily_pnl: Optional[float] = None,
        total_trades: Optional[int] = None,
        winning_trades: Optional[int] = None,
        losing_trades: Optional[int] = None,
        buying_power: Optional[float] = None,
        long_option_value: Optional[float] = None,
        short_option_value: Optional[float] = None
    ):
        """Insert a new account balance snapshot for this trading mode."""
        if not self.trading_mode:
            return

        try:
            account_hash = self._resolve_account_hash(account_hash)
            if not account_hash:
                self.logger.warning("No broker accounts found, skipping balance update")
                return

            win_rate = None
            if total_trades and total_trades > 0 and winning_trades is not None:
                win_rate = winning_trades / total_trades

            self.cursor.execute(f"""
                INSERT INTO {self.table_prefix}account_balance (
                    account_hash, timestamp,
                    cash_balance, available_funds, buying_power,
                    liquidation_value, portfolio_value,
                    long_option_market_value, short_option_market_value,
                    total_pnl, daily_pnl, win_rate,
                    is_snapshot
                ) VALUES (
                    %s, NOW(),
                    %s, %s, %s,
                    %s, %s,
                    %s, %s,
                    %s, %s, %s,
                    TRUE
                )
            """, (
                account_hash,
                cash, cash, buying_power or cash * 4,
                portfolio_value, portfolio_value,
                long_option_value or 0, short_option_value or 0,
                portfolio_value - 100000 if portfolio_value else 0,
                daily_pnl or 0, win_rate,
            ))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"Failed to update account balance: {e}")
            raise

    def reset_account_balance(self, initial_capital: float = 100000.0, account_hash: Optional[str] = None):
        """Reset account balance to initial state."""
        if not self.trading_mode:
            return

        try:
            account_hash = self._resolve_account_hash(account_hash)
            if not account_hash:
                self.logger.warning("No broker accounts found, cannot reset balance")
                return

            self.cursor.execute(f"""
                INSERT INTO {self.table_prefix}account_balance (
                    account_hash, timestamp,
                    cash_balance, available_funds, buying_power,
                    liquidation_value, portfolio_value,
                    long_option_market_value, short_option_market_value,
                    total_pnl, daily_pnl, win_rate,
                    is_snapshot
                ) VALUES (
                    %s, NOW(),
                    %s, %s, %s,
                    %s, %s,
                    0, 0,
                    0, 0, NULL,
                    TRUE
                )
            """, (
                account_hash,
                initial_capital, initial_capital, initial_capital * 4,
                initial_capital, initial_capital
            ))
            self.conn.commit()
            self.logger.info(f"Reset account balance to ${initial_capital:,.2f}")
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"Failed to reset account balance: {e}")
            raise

    def _resolve_account_hash(self, account_hash: Optional[str]) -> Optional[str]:
        """Resolve account hash from database if not provided."""
        if account_hash:
            return account_hash

        # Try to get default account
        self.cursor.execute(f"""
            SELECT account_hash FROM {self.table_prefix}broker_accounts
            WHERE is_default = TRUE
            LIMIT 1
        """)
        result = self.cursor.fetchone()

        if result:
            return result['account_hash']

        # Fall back to any account
        self.cursor.execute(f"""
            SELECT account_hash FROM {self.table_prefix}broker_accounts
            LIMIT 1
        """)
        result = self.cursor.fetchone()

        return result['account_hash'] if result else None

    def clear_all_data(self):
        """Clear all trading data for current mode."""
        if self.trading_mode == 'real':
            raise ValueError("Cannot clear real trading data!")

        if not self.trading_mode:
            raise ValueError("Cannot clear data in legacy mode")

        try:
            # Truncate all tables
            for table in ['positions', 'orders', 'strategy_state', 'engine_state']:
                self.cursor.execute(f"TRUNCATE TABLE {self.table_prefix}{table} CASCADE")

            # Delete events (hypertable)
            self.cursor.execute(f"DELETE FROM {self.table_prefix}events")

            # Reset account balance
            self.cursor.execute(f"DELETE FROM {self.table_prefix}account_balance")
            self.cursor.execute(f"""
                INSERT INTO {self.table_prefix}account_balance (id, cash, portfolio_value, total_pnl)
                VALUES (1, 100000.00, 100000.00, 0)
            """)

            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def close(self):
        """Close database connection."""
        self.cursor.close()
        self.conn.close()