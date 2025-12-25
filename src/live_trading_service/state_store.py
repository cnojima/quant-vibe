"""State persistence for live trading engine.

Provides database-backed state storage to enable:
- Engine restart without losing track of positions
- Audit trail of all decisions and actions
- Recovery from failures
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()


class StateStore:
    """Manages persistence of trading engine state."""

    def __init__(self, db_config: Optional[Dict] = None, db_profile: Optional[str] = None):
        """
        Initialize state store.

        Args:
            db_config: Database configuration (defaults to TimescaleDB config from .env)
            db_profile: Database profile to use ('local' or 'remote').
                       If None, auto-detects from USE_REMOTE_TIMESCALE env var.
        """
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

        self._ensure_tables_exist()

    def _ensure_tables_exist(self):
        """Create tables for state persistence if they don't exist."""

        # Table for engine state
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_engine_state (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
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
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS live_events (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                event_type TEXT NOT NULL,
                strategy_name TEXT,
                position_id TEXT,
                order_id TEXT,
                severity TEXT NOT NULL DEFAULT 'info',
                message TEXT NOT NULL,
                details JSONB
            );
        """)
        self.conn.commit()

        # Hypertable for events (time-series optimized)
        # Note: This requires TimescaleDB extension
        try:
            self.cursor.execute("""
                SELECT create_hypertable('live_events', 'timestamp',
                    if_not_exists => TRUE);
            """)
            self.conn.commit()
        except Exception as e:
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
        self.cursor.execute("""
            INSERT INTO live_engine_state (timestamp, state, metadata)
            VALUES (NOW(), %s, %s)
            ON CONFLICT (timestamp) DO UPDATE
            SET state = EXCLUDED.state, metadata = EXCLUDED.metadata
        """, (state, json.dumps(metadata) if metadata else None))
        self.conn.commit()

    def get_latest_engine_state(self) -> Optional[Dict]:
        """Get the most recent engine state."""
        self.cursor.execute("""
            SELECT * FROM live_engine_state
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
        self.cursor.execute("""
            INSERT INTO live_positions (
                position_id, strategy_name, spread_type, entry_time,
                entry_cost, underlying_price_at_entry, status,
                current_value, exit_time, exit_value, exit_reason,
                legs, metadata
            ) VALUES (
                %(position_id)s, %(strategy_name)s, %(spread_type)s, %(entry_time)s,
                %(entry_cost)s, %(underlying_price_at_entry)s, %(status)s,
                %(current_value)s, %(exit_time)s, %(exit_value)s, %(exit_reason)s,
                %(legs)s, %(metadata)s
            )
            ON CONFLICT (position_id) DO UPDATE SET
                status = EXCLUDED.status,
                current_value = EXCLUDED.current_value,
                exit_time = EXCLUDED.exit_time,
                exit_value = EXCLUDED.exit_value,
                exit_reason = EXCLUDED.exit_reason,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
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
            'metadata': json.dumps(position_data.get('metadata', {}))
        })
        self.conn.commit()

    def get_open_positions(self, strategy_name: Optional[str] = None) -> List[Dict]:
        """
        Get all open positions.

        Args:
            strategy_name: Filter by strategy (optional)

        Returns:
            List of position dicts
        """
        if strategy_name:
            self.cursor.execute("""
                SELECT * FROM live_positions
                WHERE status = 'open' AND strategy_name = %s
                ORDER BY entry_time DESC
            """, (strategy_name,))
        else:
            self.cursor.execute("""
                SELECT * FROM live_positions
                WHERE status = 'open'
                ORDER BY entry_time DESC
            """)

        positions = self.cursor.fetchall()

        # Parse JSON fields
        for pos in positions:
            pos['legs'] = json.loads(pos['legs'])
            if pos.get('metadata'):
                pos['metadata'] = json.loads(pos['metadata'])

        return positions

    def close_position(self, position_id: str, exit_value: float, exit_reason: str):
        """Mark a position as closed."""
        self.cursor.execute("""
            UPDATE live_positions
            SET status = 'closed',
                exit_time = NOW(),
                exit_value = %s,
                exit_reason = %s,
                updated_at = NOW()
            WHERE position_id = %s
        """, (exit_value, exit_reason, position_id))
        self.conn.commit()

    # ========================================================================
    # Orders
    # ========================================================================

    def save_order(self, order_data: Dict):
        """
        Save or update an order.

        Args:
            order_data: Order data dict
        """
        self.cursor.execute("""
            INSERT INTO live_orders (
                order_id, position_id, strategy_name, order_type, side,
                quantity, symbol, status, submitted_time, expected_price,
                broker_order_id, metadata
            ) VALUES (
                %(order_id)s, %(position_id)s, %(strategy_name)s, %(order_type)s,
                %(side)s, %(quantity)s, %(symbol)s, %(status)s,
                %(submitted_time)s, %(expected_price)s,
                %(broker_order_id)s, %(metadata)s
            )
            ON CONFLICT (order_id) DO UPDATE SET
                status = EXCLUDED.status,
                filled_time = COALESCE(EXCLUDED.filled_time, live_orders.filled_time),
                filled_price = COALESCE(EXCLUDED.filled_price, live_orders.filled_price),
                filled_quantity = COALESCE(EXCLUDED.filled_quantity, live_orders.filled_quantity),
                error_message = COALESCE(EXCLUDED.error_message, live_orders.error_message),
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """, {
            'order_id': order_data['order_id'],
            'position_id': order_data.get('position_id'),
            'strategy_name': order_data['strategy_name'],
            'order_type': order_data['order_type'],
            'side': order_data['side'],
            'quantity': order_data['quantity'],
            'symbol': order_data['symbol'],
            'status': order_data.get('status', 'pending'),
            'submitted_time': order_data.get('submitted_time', datetime.now()),
            'expected_price': order_data.get('expected_price'),
            'broker_order_id': order_data.get('broker_order_id'),
            'metadata': json.dumps(order_data.get('metadata', {}))
        })
        self.conn.commit()

    def update_order_status(
        self,
        order_id: str,
        status: str,
        filled_price: Optional[float] = None,
        filled_quantity: Optional[int] = None,
        error_message: Optional[str] = None
    ):
        """Update order status."""
        self.cursor.execute("""
            UPDATE live_orders
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

    # ========================================================================
    # Strategy State
    # ========================================================================

    def save_strategy_state(self, strategy_name: str, state: Dict):
        """Save strategy-specific state."""
        self.cursor.execute("""
            INSERT INTO live_strategy_state (strategy_name, state, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (strategy_name) DO UPDATE
            SET state = EXCLUDED.state, updated_at = NOW()
        """, (strategy_name, json.dumps(state)))
        self.conn.commit()

    def get_strategy_state(self, strategy_name: str) -> Optional[Dict]:
        """Get strategy state."""
        self.cursor.execute("""
            SELECT state FROM live_strategy_state
            WHERE strategy_name = %s
        """, (strategy_name,))
        result = self.cursor.fetchone()
        return json.loads(result['state']) if result else None

    def reset_strategy_state(self, strategy_name: str):
        """Reset strategy state (for daily reset)."""
        self.cursor.execute("""
            UPDATE live_strategy_state
            SET state = '{}', last_reset = NOW(), updated_at = NOW()
            WHERE strategy_name = %s
        """, (strategy_name,))
        self.conn.commit()

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
        self.cursor.execute("""
            INSERT INTO live_events (
                timestamp, event_type, strategy_name, position_id, order_id,
                severity, message, details
            ) VALUES (
                NOW(), %s, %s, %s, %s, %s, %s, %s
            )
        """, (
            event_type, strategy_name, position_id, order_id,
            severity, message, json.dumps(details) if details else None
        ))
        self.conn.commit()

    def get_recent_events(
        self,
        limit: int = 100,
        severity: Optional[str] = None,
        strategy_name: Optional[str] = None
    ) -> List[Dict]:
        """Get recent events from audit log."""
        query = "SELECT * FROM live_events WHERE 1=1"
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

        # Parse JSON fields
        for event in events:
            if event.get('details'):
                event['details'] = json.loads(event['details'])

        return events

    # ========================================================================
    # Cleanup
    # ========================================================================

    def close(self):
        """Close database connection."""
        self.cursor.close()
        self.conn.close()
