# Trading Modes Implementation Summary

## ✅ What's Been Completed

### 1. Schema Design (`docs/TRADING_MODES_SCHEMA.md`)
- Complete isolation using PostgreSQL schemas
- Three separate schemas: `real_trading`, `paper_trading`, `replay_trading`
- Identical table structure across all schemas
- New `account_balance` table for balance/P&L tracking
- Helper functions for mode management

### 2. Migration Script (`src/quant_vibe/data/schema/migrations/010_add_trading_modes.sql`)
- Creates three isolated schemas with complete table structure
- 100% backward compatible with existing `public.live_*` tables
- New fields have default values (zero breaking changes)
- Helper functions: `get_account_balance()`, `clear_replay_data()`, etc.
- Ready to run: `psql -U quantvibe -d options_data < src/quant_vibe/data/schema/migrations/010_add_trading_modes.sql`

### 3. Updated StateStore (`src/live_trading_service/state_store.py`)
- Added `trading_mode` parameter to `__init__`
- Automatically routes to correct schema based on mode
- All existing methods work unchanged
- New methods:
  - `get_account_balance()` - Get balance for current mode
  - `update_account_balance()` - Update balance and metrics
  - `reset_account_balance()` - Reset to initial capital
  - `get_all_strategy_states()` - Get all strategy states
  - `reset_replay_data()` - Clear replay data (replay mode only)
- 100% backward compatible (mode=None uses public schema)

## 🔄 What's Next

### Step 1: Run the Migration

```bash
# Connect to your database
psql -U quantvibe -d options_data

# Run the migration
\i src/quant_vibe/data/schema/migrations/010_add_trading_modes.sql

# Verify schemas were created
\dn

# Check tables in each schema
\dt real_trading.*
\dt paper_trading.*
\dt replay_trading.*

# Test helper functions
SELECT * FROM compare_trading_modes();
```

### Step 2: Update LiveTradingEngine

The LiveTradingEngine needs minimal changes:

```python
# In __init__:
def __init__(self, config_path: str = "config/live_trading.yaml"):
    # ... existing code ...

    # NEW: Determine trading mode from config
    self.trading_mode = self._determine_trading_mode()

    # NEW: Pass trading_mode to StateStore
    self.state_store = StateStore(
        db_config=self._get_db_config(),
        trading_mode=self.trading_mode  # <-- NEW
    )

    # NEW: Load mode-specific state
    self._load_mode_state()

def _determine_trading_mode(self) -> str:
    """Determine trading mode from config."""
    # Check if replay mode
    data_feed_mode = self.config.get('data_feed', {}).get('mode', 'live')
    if data_feed_mode == 'replay':
        return 'replay'

    # Check paper vs real
    paper_trading = self.config['engine'].get('paper_trading', True)
    return 'paper' if paper_trading else 'real'

def _load_mode_state(self):
    """Load existing state for current mode."""
    # Get account balance
    balance = self.state_store.get_account_balance()
    if balance:
        self.logger.info(f"💰 Cash: ${balance['cash']:,.2f}")
        self.logger.info(f"📈 Portfolio: ${balance['portfolio_value']:,.2f}")
        self.logger.info(f"📊 Total P&L: ${balance.get('total_pnl', 0):,.2f}")

    # Get open positions
    positions = self.state_store.get_open_positions()
    self.logger.info(f"📍 Open Positions: {len(positions)}")

    # Display mode status
    self._display_mode_status()

def _display_mode_status(self):
    """Display current mode status on startup."""
    self.logger.info("=" * 70)
    self.logger.info(f"🔧 Trading Mode: {self.trading_mode.upper()}")
    self.logger.info(f"📊 Database Schema: {self.trading_mode}_trading")
    self.logger.info("=" * 70)
```

### Step 3: Testing

#### Test 1: Legacy Mode (Backward Compatibility)
```python
# Should still work exactly as before
state_store = StateStore()  # No trading_mode = uses public.live_* tables
positions = state_store.get_open_positions()
state_store.save_position({...})
```

#### Test 2: Paper Trading Mode
```python
# Test paper trading schema
state_store = StateStore(trading_mode='paper')

# Check account balance
balance = state_store.get_account_balance()
print(f"Cash: ${balance['cash']}")

# Save a position
state_store.save_position({
    'position_id': 'test_paper_001',
    'strategy_name': 'bullish_vertical_put',
    'spread_type': 'vertical_put',
    'entry_time': now_utc(),
    'entry_cost': 1000.0,
    'underlying_price_at_entry': 5900.0,
    'legs': [{'symbol': 'SPXW...', 'quantity': 10, 'side': 'sell'}]
})

# Verify it's in paper_trading schema, not public
positions = state_store.get_open_positions()
assert len(positions) == 1
```

#### Test 3: Real Trading Mode
```python
# Test real trading schema (completely isolated)
state_store = StateStore(trading_mode='real')

# Should be empty (no data mixed from paper)
positions = state_store.get_open_positions()
assert len(positions) == 0

# Update balance
state_store.update_account_balance(
    cash=95000.0,
    portfolio_value=96500.0,
    daily_pnl=1500.0
)

balance = state_store.get_account_balance()
assert balance['cash'] == 95000.0
assert balance['daily_pnl'] == 1500.0
```

#### Test 4: Replay Mode
```python
# Test replay schema (transient)
state_store = StateStore(trading_mode='replay')

# Add some test data
state_store.save_position({...})
state_store.save_order({...})

# Clear replay data
state_store.reset_replay_data()

# Verify everything was cleared
positions = state_store.get_open_positions()
assert len(positions) == 0

balance = state_store.get_account_balance()
assert balance['cash'] == 100000.0  # Reset to default
```

#### Test 5: Mode Isolation
```python
# Create positions in each mode
paper_store = StateStore(trading_mode='paper')
real_store = StateStore(trading_mode='real')
replay_store = StateStore(trading_mode='replay')

# Add position to paper
paper_store.save_position({'position_id': 'paper_001', ...})

# Verify it doesn't appear in other modes
assert len(real_store.get_open_positions()) == 0
assert len(replay_store.get_open_positions()) == 0

# Add position to real
real_store.save_position({'position_id': 'real_001', ...})

# Verify isolation
assert len(paper_store.get_open_positions()) == 1  # Only paper_001
assert len(real_store.get_open_positions()) == 1   # Only real_001
assert len(replay_store.get_open_positions()) == 0
```

#### Test 6: Compare Modes Query
```sql
-- Run the comparison function
SELECT * FROM compare_trading_modes();

-- Should return 3 rows (real, paper, replay) with their respective metrics
```

### Step 4: Update Configuration

The mode is automatically determined, but you can verify your config:

```yaml
# config/live_trading.yaml

# For paper trading
engine:
  paper_trading: true  # <-- This sets paper mode
data_feed:
  mode: live

# For real trading
engine:
  paper_trading: false  # <-- This sets real mode
data_feed:
  mode: live

# For replay mode
data_feed:
  mode: replay  # <-- This overrides to replay mode regardless of paper_trading
```

## 📊 Key Benefits

### Complete Isolation
```sql
-- Each mode has its own data - no mixing possible
SELECT * FROM paper_trading.positions;   -- Paper positions
SELECT * FROM real_trading.positions;    -- Real positions
SELECT * FROM replay_trading.positions;  -- Replay positions
```

### Mode Switching
```bash
# Start in paper mode
python scripts/run_live_trading.py
# Loads paper_trading schema, shows paper positions/balance

# Stop and switch config to real mode (paper_trading: false)
# Start again
python scripts/run_live_trading.py
# Loads real_trading schema, shows DIFFERENT positions/balance
```

### Transient Replay
```python
# Clear replay data between runs
state_store = StateStore(trading_mode='replay')
state_store.reset_replay_data()
# All replay data gone, ready for fresh run
```

### Balance Tracking
```python
# Each mode tracks its own balance
paper_balance = StateStore(trading_mode='paper').get_account_balance()
real_balance = StateStore(trading_mode='real').get_account_balance()

# Different balances, different P&L, different win rates
print(f"Paper P&L: ${paper_balance['total_pnl']}")
print(f"Real P&L: ${real_balance['total_pnl']}")
```

## 🔍 Troubleshooting

### Issue: Tables not found
**Symptom**: `relation "paper_trading.positions" does not exist`

**Solution**: Run the migration script
```bash
psql -U quantvibe -d options_data -f src/quant_vibe/data/schema/migrations/010_add_trading_modes.sql
```

### Issue: Legacy code breaks
**Symptom**: Existing code stops working after migration

**Solution**: Legacy code should work unchanged. If issues occur:
```python
# Explicitly use legacy mode
state_store = StateStore(trading_mode=None)  # Uses public.live_* tables
```

### Issue: Wrong schema being used
**Symptom**: Data appears in wrong mode

**Solution**: Check the StateStore initialization
```python
# Debug: Print which schema is being used
state_store = StateStore(trading_mode='paper')
print(f"Schema: {state_store.schema}")  # Should be "paper_trading"
print(f"Table prefix: {state_store.table_prefix}")  # Should be ""
```

### Issue: Cannot clear replay data
**Symptom**: `reset_replay_data() raises ValueError`

**Solution**: Only works in replay mode
```python
# ❌ Wrong
state_store = StateStore(trading_mode='paper')
state_store.reset_replay_data()  # Raises ValueError

# ✅ Correct
state_store = StateStore(trading_mode='replay')
state_store.reset_replay_data()  # Works
```

## 📝 Migration Checklist

- [ ] Backup database before running migration
- [ ] Run migration script (`010_add_trading_modes.sql`)
- [ ] Verify schemas created (`\dn` in psql)
- [ ] Verify tables created (`\dt paper_trading.*`)
- [ ] Test legacy mode (no trading_mode parameter)
- [ ] Test paper mode with StateStore
- [ ] Test real mode with StateStore
- [ ] Test replay mode with StateStore
- [ ] Test mode isolation (data doesn't mix)
- [ ] Update LiveTradingEngine to pass trading_mode
- [ ] Test full engine startup in each mode
- [ ] Update admin UI to show mode-specific data
- [ ] Document mode switching process for users

## 🚀 Quick Start

```bash
# 1. Run migration
psql -U quantvibe -d options_data -f src/quant_vibe/data/schema/migrations/010_add_trading_modes.sql

# 2. Test StateStore
python3 << 'EOF'
from src.live_trading_service.state_store import StateStore

# Test paper mode
store = StateStore(trading_mode='paper')
balance = store.get_account_balance()
print(f"Paper Trading Balance: ${balance['cash']:,.2f}")
store.close()

# Test real mode
store = StateStore(trading_mode='real')
balance = store.get_account_balance()
print(f"Real Trading Balance: ${balance['cash']:,.2f}")
store.close()
EOF

# 3. Update LiveTradingEngine (see Step 2 above)

# 4. Test engine startup
python scripts/run_live_trading.py
```

## 📚 Related Documentation

- `docs/TRADING_MODES_SCHEMA.md` - Detailed schema design
- `src/quant_vibe/data/schema/migrations/010_add_trading_modes.sql` - Migration script
- `src/live_trading_service/state_store.py` - Updated StateStore implementation

## 🎯 Success Criteria

You'll know the implementation is successful when:

✅ Migration runs without errors
✅ Three schemas exist with identical table structure
✅ Legacy code works unchanged (backward compatible)
✅ StateStore with `trading_mode='paper'` uses `paper_trading` schema
✅ StateStore with `trading_mode='real'` uses `real_trading` schema
✅ StateStore with `trading_mode='replay'` uses `replay_trading` schema
✅ Data is completely isolated between modes
✅ `compare_trading_modes()` returns different metrics per mode
✅ Replay data can be cleared without affecting other modes
✅ LiveTradingEngine loads correct state when mode switches
