"""State persistence for live trading engine.

Provides database-backed state storage to enable:
- Engine restart without losing track of positions
- Audit trail of all decisions and actions
- Recovery from failures
"""

import os
import json
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import numpy as np
from quant_vibe.utils import now_utc
from quant_vibe.logging import get_logger

load_dotenv()


def _json_serialize_safe(obj):
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
        """
        Initialize state store.

        Args:
            db_config: Database configuration (defaults to TimescaleDB config from .env)
            db_profile: Database profile to use ('local' or 'remote').
                       If None, auto-detects from USE_REMOTE_TIMESCALE env var.
            trading_mode: Trading mode ('real', 'paper', 'replay', or None for legacy public schema)
        """
        # Validate trading mode
        if trading_mode is not None and trading_mode not in ['real', 'paper']:
            raise ValueError(f"Invalid trading_mode: {trading_mode}. Must be 'real' or 'paper' (or None for legacy)")

        self.trading_mode = trading_mode
        self.logger = get_logger('live_trading')

        # Set schema based on trading mode
        if trading_mode:
            self.schema = f"{trading_mode}_trading"
            self.table_prefix = ""  # Tables in mode schemas don't have live_ prefix
        else:
            self.schema = "public"
            self.table_prefix = "live_"  # Legacy tables in public schema have live_ prefix

        if db_config is None:
            # Determine which database to use
            use_remote = os.getenv('USE_REMOTE_TIMESCALE', 'false').lower() == 'true'

            # Allow manual override via db_profile parameter
            if db_profile == 'remote':
                use_remote = True
            elif db_profile == 'local':
                use_remote = False

            # Use remote or local TimescaleDB config from environment
            if use_remote:
                db_config = {
                    'host': os.getenv('REMOTE_TIMESCALE_HOST', '192.168.100.197'),
                    'port': int(os.getenv('REMOTE_TIMESCALE_PORT', '5432')),
                    'database': os.getenv('REMOTE_TIMESCALE_DB', 'options_data'),
                    'user': os.getenv('REMOTE_TIMESCALE_USER', 'quantvibe'),
                    'password': os.getenv('REMOTE_TIMESCALE_PASSWORD', 'quantvibe_dev')
                }
                print(f"🌐 Using REMOTE TimescaleDB: {db_config['host']}:{db_config['port']}")
            else:
                db_config = {
                    'host': os.getenv('TIMESCALE_HOST', 'localhost'),
                    'port': int(os.getenv('TIMESCALE_PORT', '5432')),
                    'database': os.getenv('TIMESCALE_DB', 'options_data'),
                    'user': os.getenv('TIMESCALE_USER', 'quantvibe'),
                    'password': os.getenv('TIMESCALE_PASSWORD', 'quantvibe_dev')
                }
                print(f"💻 Using LOCAL TimescaleDB: {db_config['host']}:{db_config['port']}")

        # Create direct connection (simpler than pool for now)
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        # Set search path to include the appropriate schema
        if trading_mode:
            self.cursor.execute(f"SET search_path TO {self.schema}, public")
            self.conn.commit()
            print(f"📊 Using schema: {self.schema} (trading_mode={trading_mode})")

        # Only ensure tables exist for legacy public schema
        # Mode-specific schemas should already have tables from migration
        if not trading_mode:
            self._ensure_tables_exist()

    def _ensure_tables_exist(self):
        """Create tables for state persistence if they don't exist."""

        # Table for engine state
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_engine_state (
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                id SERIAL PRIMARY KEY,
                state TEXT NOT NULL,
                metadata JSONB,
                UNIQUE(timestamp)
            );
        """)

        # Table for active positions
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_positions (
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
            );
        """)

        # Index for quick lookups
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_live_positions_status
            ON live_positions(status, strategy_name);
        """)

        # Table for orders
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_orders (
                order_id TEXT PRIMARY KEY,
                position_id TEXT REFERENCES live_positions(position_id),
                strategy_name TEXT NOT NULL,
                order_type TEXT NOT NULL,
                action_type TEXT,  -- 'opening' or 'closing'
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
            );
        """)

        # Table for strategy state (daily resets, etc.)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_strategy_state (
                strategy_name TEXT PRIMARY KEY,
                state JSONB NOT NULL,
                last_reset TIMESTAMPTZ,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        # Table for events/audit log
        # Note: For TimescaleDB hypertables, timestamp must be first column in PK
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_events (
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
            );
        """)
        self.conn.commit()

        # Create indexes for efficient queries
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_live_events_strategy
            ON live_events(strategy_name, timestamp DESC);
        """)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_live_events_position
            ON live_events(position_id, timestamp DESC);
        """)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_live_events_severity
            ON live_events(severity, timestamp DESC);
        """)
        self.cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_live_events_type
            ON live_events(event_type, timestamp DESC);
        """)
        self.conn.commit()

        # Hypertable for events (time-series optimized)
        # Note: This requires TimescaleDB extension
        try:
            self.cursor.execute("""
                SELECT create_hypertable('live_events', 'timestamp',
                    migrate_data => TRUE,
                    if_not_exists => TRUE);
            """)
            self.conn.commit()
        except Exception:
            # Rollback the failed hypertable creation
            self.conn.rollback()
            # Table still exists as regular table, which is fine

    # ========================================================================
    # Engine State
    # ========================================================================

    def save_engine_state(self, state: str, metadata: Optional[Dict] = None):
        """
        Save current engine state.

        Args:
            state: Engine state (from TradingState)
            metadata: Additional metadata
        """
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

    # ========================================================================
    # Positions
    # ========================================================================

    def save_position(self, position_data: Dict):
        """
        Save or update a position.

        Args:
            position_data: Position data dict with keys:
                - position_id, strategy_name, spread_type, entry_time,
                  entry_cost, underlying_price_at_entry, legs, status, etc.
        """
        try:
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
            """, {
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
            })
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise  # Re-raise to preserve original error context

    def get_open_positions(self, strategy_name: Optional[str] = None) -> List[Dict]:
        """
        Get all open positions.

        Args:
            strategy_name: Filter by strategy (optional)

        Returns:
            List of position dicts
        """
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

        positions = self.cursor.fetchall()

        # JSONB fields are automatically parsed by psycopg2, no need to json.loads()
        # The legs and metadata columns are JSONB type, so they come back as Python objects

        return positions

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
        """Remove a position from the database (used for cleaning up synthetic positions)."""
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

    def get_all_positions(self) -> List[Dict]:
        """Get all open positions (alias for get_open_positions)."""
        return self.get_open_positions()

    def get_trades_for_date(self, trade_date, account_hash: Optional[str] = None) -> List[Dict]:
        """
        Get all closed trades for a specific date.

        Args:
            trade_date: Date object for the trading day
            account_hash: Optional account hash to filter trades for a specific account

        Returns:
            List of trade dicts with P&L calculated
        """
        if account_hash:
            self.cursor.execute(f"""
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
                  AND account_hash = %s
                ORDER BY exit_time ASC
            """, (trade_date, account_hash))
        else:
            self.cursor.execute(f"""
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
                ORDER BY exit_time ASC
            """, (trade_date,))

        trades = self.cursor.fetchall()

        # JSONB fields (legs, metadata) are automatically parsed by psycopg2
        # No need to parse as they're already Python objects

        return trades

    # ========================================================================
    # Orders
    # ========================================================================

    def clear_broker_sync_orders(self):
        """
        Clear orders that were synced from broker (not created by strategies).
        Keeps orders created by trading strategies.
        """
        try:
            self.cursor.execute(f"""
                DELETE FROM {self.table_prefix}orders
                WHERE strategy_name = 'broker_sync'
            """)
            deleted_count = self.cursor.rowcount
            self.conn.commit()
            return deleted_count
        except Exception as e:
            self.conn.rollback()
            raise

    def save_order(self, order_data: Dict):
        """
        Save or update an order.

        Args:
            order_data: Order data dict
        """
        try:
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
            """, {
                'order_id': order_data.get('order_id', f"unknown_{now_utc().timestamp()}"),
                'position_id': order_data.get('position_id'),
                'strategy_name': order_data.get('strategy_name', 'broker_sync'),  # Default for broker-synced orders
                'order_type': order_data.get('order_type', 'LIMIT'),
                'action_type': order_data.get('action_type', 'opening'),
                'side': order_data.get('side', 'BUY'),
                'quantity': order_data.get('quantity', 1),
                'symbol': order_data.get('symbol', 'UNKNOWN'),
                'status': order_data.get('status', 'pending'),
                'submitted_time': order_data.get('submitted_time', now_utc()),
                'filled_time': order_data.get('filled_time'),  # BUG FIX: was missing
                'expected_price': order_data.get('expected_price'),
                'filled_price': order_data.get('filled_price'),  # BUG FIX: was missing
                'broker_order_id': order_data.get('broker_order_id'),
                'metadata': json.dumps(order_data.get('metadata', {}))
            })
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

    # ========================================================================
    # Strategy State
    # ========================================================================

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
        # state column is JSONB, already parsed by psycopg2
        return result['state'] if result else None

    def reset_strategy_state(self, strategy_name: str):
        """Reset strategy state (for daily reset)."""
        try:
            # Note: Use {{}} to escape braces in f-string
            self.cursor.execute(f"""
                UPDATE {self.table_prefix}strategy_state
                SET state = '{{}}', last_reset = NOW(), updated_at = NOW()
                WHERE strategy_name = %s
            """, (strategy_name,))
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ========================================================================
    # Events / Audit Log
    # ========================================================================

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
        """
        Log an event to the audit trail.

        Args:
            event_type: Type of event (from EventType)
            message: Human-readable message
            severity: info, warning, error, critical
            strategy_name: Associated strategy
            position_id: Associated position
            order_id: Associated order
            details: Additional details as dict
        """
        try:
            # Safely serialize details dict (handles numpy types)
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
            raise  # Re-raise to preserve original error context

    def get_recent_events(
        self,
        limit: int = 100,
        severity: Optional[str] = None,
        strategy_name: Optional[str] = None
    ) -> List[Dict]:
        """Get recent events from audit log."""
        query = "SELECT * FROM {self.table_prefix}events WHERE 1=1"
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
        events = self.cursor.fetchall()

        # details column is JSONB, already parsed by psycopg2
        # No need to parse as it's already a Python object

        return events

    # ========================================================================
    # Account Balance (NEW - for trading mode schemas)
    # ========================================================================

    def get_account_balance(self, account_hash: Optional[str] = None) -> Optional[Dict]:
        """
        Get current account balance for this trading mode.

        Args:
            account_hash: Optional account hash to get balance for. If None, gets the default account.

        Returns:
            Dict with balance info, or None if not found (legacy mode)
        """
        if not self.trading_mode:
            # Legacy mode doesn't have account_balance table
            return None

        if account_hash:
            # Get balance for specific account
            self.cursor.execute(f"""
                SELECT * FROM {self.table_prefix}account_balance
                WHERE account_hash = %s
                ORDER BY timestamp DESC
                LIMIT 1
            """, (account_hash,))
        else:
            # Get balance for the default account
            self.cursor.execute(f"""
                SELECT ab.* FROM {self.table_prefix}account_balance ab
                JOIN {self.table_prefix}broker_accounts ba ON ab.account_hash = ba.account_hash
                WHERE ba.is_default = TRUE
                ORDER BY ab.timestamp DESC
                LIMIT 1
            """)

        result = self.cursor.fetchone()

        # If no balance exists for any account, return None (will be initialized later)
        if not result:
            # Try to get any balance (for backwards compatibility)
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
        """
        Insert a new account balance snapshot for this trading mode.
        Since this is a time-series table, we always INSERT, not UPDATE.

        Args:
            cash: Current cash balance
            portfolio_value: Total portfolio value (cash + positions)
            account_hash: Account hash (if None, uses default account)
            daily_pnl: Today's P&L
            total_trades: Total trades count
            winning_trades: Winning trades count
            losing_trades: Losing trades count
            buying_power: Available buying power
            long_option_value: Value of long option positions
            short_option_value: Value of short option positions
        """
        if not self.trading_mode:
            # Legacy mode doesn't have account_balance table
            return

        try:
            # Get account_hash if not provided
            if not account_hash:
                # Get the default account
                self.cursor.execute(f"""
                    SELECT account_hash FROM {self.table_prefix}broker_accounts
                    WHERE is_default = TRUE
                    LIMIT 1
                """)
                result = self.cursor.fetchone()
                if result:
                    account_hash = result['account_hash']
                else:
                    # No default account, get any account
                    self.cursor.execute(f"""
                        SELECT account_hash FROM {self.table_prefix}broker_accounts
                        LIMIT 1
                    """)
                    result = self.cursor.fetchone()
                    if result:
                        account_hash = result['account_hash']
                    else:
                        # No accounts exist yet, skip update
                        self.logger.warning("No broker accounts found, skipping balance update")
                        return

            # Calculate win rate if we have trade counts
            win_rate = None
            if total_trades and total_trades > 0 and winning_trades is not None:
                win_rate = winning_trades / total_trades

            # Insert new balance record (time-series data)
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
                cash, cash, buying_power or cash * 4,  # Default 4x margin for buying power
                portfolio_value, portfolio_value,
                long_option_value or 0, short_option_value or 0,
                portfolio_value - 100000 if portfolio_value else 0,  # Total P&L from initial 100k
                daily_pnl or 0, win_rate,
            ))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"Failed to update account balance: {e}")
            raise

    def reset_account_balance(self, initial_capital: float = 100000.0, account_hash: Optional[str] = None):
        """
        Reset account balance to initial state by inserting a new reset record.

        Args:
            initial_capital: Starting capital amount
            account_hash: Account hash (if None, resets default account)
        """
        if not self.trading_mode:
            return

        try:
            # Get account_hash if not provided
            if not account_hash:
                # Get the default account
                self.cursor.execute(f"""
                    SELECT account_hash FROM {self.table_prefix}broker_accounts
                    WHERE is_default = TRUE
                    LIMIT 1
                """)
                result = self.cursor.fetchone()
                if result:
                    account_hash = result['account_hash']
                else:
                    # No accounts exist, cannot reset
                    self.logger.warning("No broker accounts found, cannot reset balance")
                    return

            # Insert reset record (new snapshot with initial values)
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
                initial_capital, initial_capital, initial_capital * 4,  # 4x margin
                initial_capital, initial_capital
            ))
            self.conn.commit()
            self.logger.info(f"Reset account balance to ${initial_capital:,.2f}")
        except Exception as e:
            self.conn.rollback()
            self.logger.error(f"Failed to reset account balance: {e}")
            raise

    def get_all_strategy_states(self) -> List[Dict]:
        """
        Get all strategy states.

        Returns:
            List of strategy state dicts
        """
        self.cursor.execute(f"""
            SELECT * FROM {self.table_prefix}strategy_state
            ORDER BY strategy_name
        """)
        states = self.cursor.fetchall()

        # state column is JSONB, already parsed by psycopg2
        # No need to parse as it's already a Python object

        return states

    def clear_all_data(self):
        """
        Clear all trading data for current mode.

        Useful for:
        - Resetting paper trading to fresh state
        - Clearing paper data before replay testing

        Raises:
            ValueError: If in real mode (safety check)
        """
        if self.trading_mode == 'real':
            raise ValueError("Cannot clear real trading data! This is a safety check.")

        if not self.trading_mode:
            raise ValueError("Cannot clear data in legacy mode")

        try:
            # Truncate all tables
            self.cursor.execute(f"TRUNCATE TABLE {self.table_prefix}positions CASCADE")
            self.cursor.execute(f"TRUNCATE TABLE {self.table_prefix}orders CASCADE")
            self.cursor.execute(f"TRUNCATE TABLE {self.table_prefix}strategy_state CASCADE")
            self.cursor.execute(f"TRUNCATE TABLE {self.table_prefix}engine_state CASCADE")

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

    # ========================================================================
    # Cleanup
    # ========================================================================

    def close(self):
        """Close database connection."""
        self.cursor.close()
        self.conn.close()
