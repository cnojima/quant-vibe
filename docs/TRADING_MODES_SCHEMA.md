# Trading Modes Schema Design

## Problem Statement

The current database schema doesn't differentiate between different trading modes:
1. **Paper Trading** - Persistent simulated trades with live market data (for testing aggressive strategies)
2. **Replay Trading** - Transient simulated trades with historical data (for testing engine/strategies)
3. **Real Trading** - Persistent actual trades with real money

**Current Issues:**
- All trades are stored in the same tables (`live_positions`, `live_orders`) without mode differentiation
- Switching modes causes data mixing and confusion
- No way to maintain separate state for each mode
- Risk of accidentally treating paper trades as real trades
- Cannot switch between modes and see different positions/balances

**Requirements:**
- ✅ Complete isolation - no data intermixing at all
- ✅ Real money: Persistent, completely separate
- ✅ Paper trading: Persistent, completely separate (test risky strategies)
- ✅ Replay: Transient, can be cleared between runs
- ✅ Mode switching: Load positions, balances, enabled strategies for that mode
- ✅ Clear PnL display per mode

## Proposed Solution: Separate PostgreSQL Schemas

**Core Concept:** Create three completely isolated schemas, each with identical table structure.

```
options_data (database)
├── public (schema)                  # Existing market data tables
│   ├── options_bars
│   ├── underlying_bars
│   └── backtest_* tables
│
├── real_trading (schema)            # Real money trading - PERSISTENT
│   ├── positions
│   ├── orders
│   ├── strategy_state
│   ├── engine_state
│   ├── events
│   └── account_balance
│
├── paper_trading (schema)           # Paper trading - PERSISTENT
│   ├── positions
│   ├── orders
│   ├── strategy_state
│   ├── engine_state
│   ├── events
│   └── account_balance
│
└── replay_trading (schema)          # Replay mode - TRANSIENT
    ├── positions
    ├── orders
    ├── strategy_state
    ├── engine_state
    ├── events
    └── account_balance
```

### Benefits

1. **Complete Isolation**: Impossible to mix data between modes - they're in different schemas
2. **Persistent State**: Real and paper trading maintain state across restarts
3. **Transient Replay**: Replay schema can be truncated between runs without affecting others
4. **Mode Switching**: Simply change the schema search path or table prefix in queries
5. **Identical Structure**: Same code works for all modes, just different schema
6. **Safety**: Accidentally querying wrong schema is impossible with proper code structure
7. **Parallel Operation**: Can run multiple modes simultaneously without conflict
8. **Clear Context**: Schema name makes it obvious which mode you're in
9. **Easy Cleanup**: DROP SCHEMA replay_trading CASCADE to reset replay mode

### Schema Structure

Each schema (real_trading, paper_trading, replay_trading) contains identical tables:

#### 1. Account Balance Table
```sql
CREATE TABLE {schema}.account_balance (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Balance tracking
    cash NUMERIC(15, 2) NOT NULL,
    portfolio_value NUMERIC(15, 2) NOT NULL,
    total_pnl NUMERIC(15, 2),

    -- Daily metrics
    daily_pnl NUMERIC(15, 2),
    daily_return_pct NUMERIC(10, 4),

    -- Lifetime metrics
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    win_rate NUMERIC(10, 4),

    -- Risk metrics
    max_drawdown NUMERIC(10, 4),
    sharpe_ratio NUMERIC(10, 4),

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Only keep the latest balance (updated, not inserted)
CREATE UNIQUE INDEX idx_{schema}_account_balance_latest ON {schema}.account_balance(id) WHERE id = 1;
```

#### 2. Positions Table
```sql
CREATE TABLE {schema}.positions (
    position_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    spread_type TEXT NOT NULL,

    -- Entry
    entry_time TIMESTAMPTZ NOT NULL,
    entry_cost NUMERIC(15, 2) NOT NULL,
    underlying_price_at_entry NUMERIC(12, 4) NOT NULL,

    -- Current state
    status TEXT NOT NULL DEFAULT 'open',  -- 'open', 'closed'
    current_value NUMERIC(15, 2),

    -- Exit
    exit_time TIMESTAMPTZ,
    exit_value NUMERIC(15, 2),
    exit_reason TEXT,

    -- Position details
    legs JSONB NOT NULL,
    metadata JSONB,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_{schema}_positions_status ON {schema}.positions(status, strategy_name);
CREATE INDEX idx_{schema}_positions_entry_time ON {schema}.positions(entry_time DESC);
```

#### 3. Orders Table
```sql
CREATE TABLE {schema}.orders (
    order_id TEXT PRIMARY KEY,
    position_id TEXT REFERENCES {schema}.positions(position_id),
    strategy_name TEXT NOT NULL,

    -- Order details
    order_type TEXT NOT NULL,
    action_type TEXT,  -- 'opening' or 'closing'
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    symbol TEXT NOT NULL,

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'submitted', 'filled', 'rejected', 'cancelled'
    submitted_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    filled_time TIMESTAMPTZ,

    -- Pricing
    expected_price NUMERIC(12, 4),
    filled_price NUMERIC(12, 4),
    filled_quantity INTEGER,

    -- Broker integration
    broker_order_id TEXT,
    error_message TEXT,

    -- Metadata
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_{schema}_orders_position ON {schema}.orders(position_id);
CREATE INDEX idx_{schema}_orders_status ON {schema}.orders(status);
CREATE INDEX idx_{schema}_orders_submitted ON {schema}.orders(submitted_time DESC);
```

#### 4. Strategy State Table
```sql
CREATE TABLE {schema}.strategy_state (
    strategy_name TEXT PRIMARY KEY,

    -- State tracking
    enabled BOOLEAN NOT NULL DEFAULT true,
    state JSONB NOT NULL,

    -- Daily tracking
    trades_today INTEGER DEFAULT 0,
    pnl_today NUMERIC(15, 2) DEFAULT 0,
    last_reset TIMESTAMPTZ,

    -- Timestamps
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_{schema}_strategy_state_enabled ON {schema}.strategy_state(enabled);
```

#### 5. Engine State Table
```sql
CREATE TABLE {schema}.engine_state (
    id INTEGER PRIMARY KEY DEFAULT 1,

    -- Engine state
    state TEXT NOT NULL,  -- 'stopped', 'starting', 'running', 'paused', 'stopping'

    -- Session info
    session_start_time TIMESTAMPTZ,
    session_end_time TIMESTAMPTZ,

    -- Configuration
    config JSONB,

    -- Metadata
    metadata JSONB,
    last_heartbeat TIMESTAMPTZ,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Ensure only one row exists
CREATE UNIQUE INDEX idx_{schema}_engine_state_singleton ON {schema}.engine_state(id);
```

#### 6. Events Table (Hypertable)
```sql
CREATE TABLE {schema}.events (
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    id SERIAL,
    event_type TEXT NOT NULL,
    strategy_name TEXT,
    position_id TEXT,
    order_id TEXT,
    severity TEXT NOT NULL DEFAULT 'info',  -- 'info', 'warning', 'error', 'critical'
    message TEXT NOT NULL,
    details JSONB,
    PRIMARY KEY (timestamp, id)
);

-- Convert to hypertable for time-series optimization
SELECT create_hypertable('{schema}.events', 'timestamp', if_not_exists => TRUE);

CREATE INDEX idx_{schema}_events_strategy ON {schema}.events(strategy_name, timestamp DESC);
CREATE INDEX idx_{schema}_events_severity ON {schema}.events(severity, timestamp DESC);
CREATE INDEX idx_{schema}_events_type ON {schema}.events(event_type, timestamp DESC);
```

## Implementation

### 1. Migration Script

The migration creates all three schemas with identical table structures:

```sql
-- Create schemas
CREATE SCHEMA IF NOT EXISTS real_trading;
CREATE SCHEMA IF NOT EXISTS paper_trading;
CREATE SCHEMA IF NOT EXISTS replay_trading;

-- Grant permissions
GRANT ALL ON SCHEMA real_trading TO quantvibe;
GRANT ALL ON SCHEMA paper_trading TO quantvibe;
GRANT ALL ON SCHEMA replay_trading TO quantvibe;
GRANT ALL ON ALL TABLES IN SCHEMA real_trading TO quantvibe;
GRANT ALL ON ALL TABLES IN SCHEMA paper_trading TO quantvibe;
GRANT ALL ON ALL TABLES IN SCHEMA replay_trading TO quantvibe;

-- Create tables in each schema (identical structure)
-- [Full table definitions for each schema]
```

### 2. StateStore Updates

```python
class StateStore:
    def __init__(
        self,
        db_config: Optional[Dict] = None,
        trading_mode: str = 'paper'  # 'real', 'paper', or 'replay'
    ):
        """Initialize state store with specific trading mode."""
        if trading_mode not in ['real', 'paper', 'replay']:
            raise ValueError(f"Invalid trading_mode: {trading_mode}")

        self.trading_mode = trading_mode
        self.schema = f"{trading_mode}_trading"

        # Connect to database
        self.conn = psycopg2.connect(**db_config)
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)

        # Set schema search path
        self.cursor.execute(f"SET search_path TO {self.schema}, public")
        self.conn.commit()

    def save_position(self, position_data: Dict):
        """Save position to mode-specific schema."""
        self.cursor.execute(f"""
            INSERT INTO {self.schema}.positions (
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
                legs = EXCLUDED.legs,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """, position_data)
        self.conn.commit()

    def get_open_positions(self, strategy_name: Optional[str] = None) -> List[Dict]:
        """Get open positions from mode-specific schema."""
        if strategy_name:
            self.cursor.execute(f"""
                SELECT * FROM {self.schema}.positions
                WHERE status = 'open' AND strategy_name = %s
                ORDER BY entry_time DESC
            """, (strategy_name,))
        else:
            self.cursor.execute(f"""
                SELECT * FROM {self.schema}.positions
                WHERE status = 'open'
                ORDER BY entry_time DESC
            """)
        return self.cursor.fetchall()

    def get_account_balance(self) -> Dict:
        """Get current account balance for this mode."""
        self.cursor.execute(f"""
            SELECT * FROM {self.schema}.account_balance
            WHERE id = 1
        """)
        result = self.cursor.fetchone()

        if result is None:
            # Initialize default balance
            initial_capital = 100000.0 if self.trading_mode != 'real' else 10000.0
            self.cursor.execute(f"""
                INSERT INTO {self.schema}.account_balance (
                    id, cash, portfolio_value, total_pnl
                ) VALUES (1, %s, %s, 0)
                RETURNING *
            """, (initial_capital, initial_capital))
            self.conn.commit()
            result = self.cursor.fetchone()

        return result

    def update_account_balance(
        self,
        cash: float,
        portfolio_value: float,
        daily_pnl: float = None,
        **kwargs
    ):
        """Update account balance for this mode."""
        self.cursor.execute(f"""
            UPDATE {self.schema}.account_balance
            SET
                cash = %s,
                portfolio_value = %s,
                total_pnl = portfolio_value - (
                    SELECT cash FROM {self.schema}.account_balance WHERE id = 1 LIMIT 1
                ),
                daily_pnl = COALESCE(%s, daily_pnl),
                updated_at = NOW()
            WHERE id = 1
        """, (cash, portfolio_value, daily_pnl))
        self.conn.commit()

    def reset_replay_data(self):
        """Clear all replay trading data (only allowed for replay mode)."""
        if self.trading_mode != 'replay':
            raise ValueError("reset_replay_data() can only be called in replay mode")

        # Truncate all tables in replay schema
        self.cursor.execute(f"TRUNCATE TABLE {self.schema}.positions CASCADE")
        self.cursor.execute(f"TRUNCATE TABLE {self.schema}.orders CASCADE")
        self.cursor.execute(f"TRUNCATE TABLE {self.schema}.strategy_state CASCADE")
        self.cursor.execute(f"DELETE FROM {self.schema}.account_balance")
        self.cursor.execute(f"DELETE FROM {self.schema}.engine_state")
        # Note: events is a hypertable, use DELETE
        self.cursor.execute(f"DELETE FROM {self.schema}.events")
        self.conn.commit()
```

### 3. LiveTradingEngine Updates

```python
class LiveTradingEngine:
    def __init__(self, config_path: str = "config/live_trading.yaml"):
        """Initialize with trading mode from config."""
        self.config = self._load_config(config_path)

        # Determine trading mode
        self.trading_mode = self._get_trading_mode()

        # Initialize state store with correct mode
        self.state_store = StateStore(
            db_config=self._get_db_config(),
            trading_mode=self.trading_mode
        )

        # Load current state for this mode
        self._load_mode_state()

        self.logger.info(f"🔧 Trading Mode: {self.trading_mode.upper()}")
        self.logger.info(f"📊 Schema: {self.trading_mode}_trading")

    def _get_trading_mode(self) -> str:
        """Determine trading mode from config."""
        # Check data feed mode first
        data_feed_mode = self.config.get('data_feed', {}).get('mode', 'live')

        if data_feed_mode == 'replay':
            return 'replay'

        # Check paper trading flag
        paper_trading = self.config['engine'].get('paper_trading', True)

        if paper_trading:
            return 'paper'
        else:
            return 'real'

    def _load_mode_state(self):
        """Load existing state for current trading mode."""
        # Get account balance
        balance = self.state_store.get_account_balance()
        self.current_cash = float(balance['cash'])
        self.portfolio_value = float(balance['portfolio_value'])

        # Get open positions
        positions = self.state_store.get_open_positions()
        self.logger.info(f"📈 Loaded {len(positions)} open positions")

        # Get strategy states
        strategies = self.state_store.get_all_strategy_states()
        self.logger.info(f"⚙️  Loaded {len(strategies)} strategy states")

        # Display current status
        self._display_mode_status()

    def _display_mode_status(self):
        """Display current mode status."""
        balance = self.state_store.get_account_balance()
        positions = self.state_store.get_open_positions()

        self.logger.info("=" * 70)
        self.logger.info(f"Trading Mode: {self.trading_mode.upper()}")
        self.logger.info("-" * 70)
        self.logger.info(f"Cash:            ${balance['cash']:,.2f}")
        self.logger.info(f"Portfolio Value: ${balance['portfolio_value']:,.2f}")
        self.logger.info(f"Total P&L:       ${balance.get('total_pnl', 0):,.2f}")
        self.logger.info(f"Daily P&L:       ${balance.get('daily_pnl', 0):,.2f}")
        self.logger.info(f"Open Positions:  {len(positions)}")
        self.logger.info(f"Total Trades:    {balance.get('total_trades', 0)}")

        if balance.get('total_trades', 0) > 0:
            win_rate = (balance.get('winning_trades', 0) / balance['total_trades']) * 100
            self.logger.info(f"Win Rate:        {win_rate:.1f}%")

        self.logger.info("=" * 70)

    def switch_mode(self, new_mode: str):
        """Switch to a different trading mode (requires restart)."""
        if new_mode not in ['real', 'paper', 'replay']:
            raise ValueError(f"Invalid mode: {new_mode}")

        if new_mode == self.trading_mode:
            self.logger.info(f"Already in {new_mode} mode")
            return

        self.logger.info(f"Switching from {self.trading_mode} to {new_mode} mode...")

        # Save current state
        self.state_store.save_engine_state('stopped')

        # Close current state store
        self.state_store.close()

        # Reinitialize with new mode
        self.trading_mode = new_mode
        self.state_store = StateStore(
            db_config=self._get_db_config(),
            trading_mode=new_mode
        )

        # Load new mode state
        self._load_mode_state()

        self.logger.info(f"✅ Switched to {new_mode} mode")
```

### 4. Utility Functions

```python
def compare_modes():
    """Compare performance across trading modes."""
    modes = ['real', 'paper', 'replay']

    for mode in modes:
        store = StateStore(trading_mode=mode)
        balance = store.get_account_balance()
        positions = store.get_closed_positions()

        print(f"\n{'=' * 70}")
        print(f"{mode.upper()} TRADING")
        print(f"{'=' * 70}")
        print(f"Cash:            ${balance['cash']:,.2f}")
        print(f"Portfolio Value: ${balance['portfolio_value']:,.2f}")
        print(f"Total P&L:       ${balance.get('total_pnl', 0):,.2f}")
        print(f"Total Trades:    {balance.get('total_trades', 0)}")

        if balance.get('total_trades', 0) > 0:
            win_rate = (balance.get('winning_trades', 0) / balance['total_trades']) * 100
            print(f"Win Rate:        {win_rate:.1f}%")

        store.close()

def reset_replay():
    """Reset replay trading data."""
    store = StateStore(trading_mode='replay')
    store.reset_replay_data()
    print("✅ Replay trading data cleared")
    store.close()
```

## Usage Examples

### Starting in Different Modes

```yaml
# config/live_trading.yaml

# For paper trading
engine:
  paper_trading: true
data_feed:
  mode: live

# For real trading
engine:
  paper_trading: false
data_feed:
  mode: live

# For replay mode
engine:
  paper_trading: true  # ignored when data_feed.mode=replay
data_feed:
  mode: replay
```

### Mode Switching

```bash
# Start in paper mode
python scripts/run_live_trading.py --mode paper

# Start in real mode (requires confirmation)
python scripts/run_live_trading.py --mode real --confirm

# Start in replay mode
python scripts/run_replay.py  # automatically uses replay mode
```

### Querying Mode-Specific Data

```sql
-- Check paper trading positions
SELECT * FROM paper_trading.positions WHERE status = 'open';

-- Check real trading balance
SELECT * FROM real_trading.account_balance WHERE id = 1;

-- Clear replay data
TRUNCATE TABLE replay_trading.positions CASCADE;
TRUNCATE TABLE replay_trading.orders CASCADE;
DELETE FROM replay_trading.events;
```

## Benefits Summary

✅ **Complete Isolation**: Schemas are completely separate - no mixing possible
✅ **Persistent State**: Real and paper trading maintain state across restarts
✅ **Transient Replay**: Easy to clear replay data without affecting others
✅ **Mode Switching**: Load different positions/balances per mode
✅ **Clear Context**: Always know which mode you're in
✅ **Parallel Operation**: Can run multiple modes simultaneously
✅ **Safety**: Real trading is completely isolated from testing
✅ **Code Reuse**: Same table names and structure in each schema

## Next Steps

1. ✅ Review and approve design
2. Create migration script (010_create_trading_mode_schemas.sql)
3. Update StateStore class with schema-based routing
4. Update LiveTradingEngine to handle mode switching
5. Add CLI commands for mode management
6. Update admin UI to show mode-specific data
7. Add mode comparison utilities
8. Test all three modes thoroughly
