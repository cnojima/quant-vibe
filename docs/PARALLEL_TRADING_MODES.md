# Parallel Trading Modes Architecture

## Overview

The trading system now supports **parallel real and paper trading** running simultaneously as separate processes. Both engines consume the same Redis data feed, providing complete isolation while sharing the same market data source.

## Key Design Decisions

### 1. Trading Modes are NOT Data Sources

**Old (Wrong) Design:**
- Replay was treated as a "trading mode"
- Real/Paper/Replay were mutually exclusive
- Couldn't run real + paper simultaneously

**New (Correct) Design:**
- Only TWO trading modes: `real` and `paper`
- Replay is a **data source**, not a mode
- Real and paper can run in parallel
- Data source (live vs replay) is independent of trading mode

### 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Data Sources                               │
├──────────────────────────────────────────────────────────────┤
│  StreamingService (live)  OR  ReplayService (historical)    │
│         │                            │                        │
│         └──────────┬─────────────────┘                        │
│                    ▼                                          │
│              Redis Pub/Sub                                    │
│         (options_bars, underlying_bars)                       │
└──────────────────────────────────────────────────────────────┘
                     │
                     │ Both consume same topics
                     ├──────────────┬──────────────┐
                     ▼              ▼              ▼
        ┌─────────────────────┐  ┌─────────────────────┐
        │  Real Trading       │  │  Paper Trading      │
        │  Engine (Process 1) │  │  Engine (Process 2) │
        ├─────────────────────┤  ├─────────────────────┤
        │ StateStore('real')  │  │ StateStore('paper') │
        │ real_trading schema │  │ paper_trading schema│
        │ Real orders→Schwab  │  │ Simulated fills     │
        │ Real $ tracking     │  │ Sim $ tracking      │
        └─────────────────────┘  └─────────────────────┘
```

### 3. Multiprocessing (Separate OS Processes)

Each trading mode runs in its own process:
- ✅ Complete isolation - one crash doesn't affect the other
- ✅ True parallelism on multi-core systems
- ✅ Independent start/stop/restart
- ✅ Clean separation of concerns

### 4. Database Isolation

```sql
-- Two completely isolated schemas
CREATE SCHEMA real_trading;   -- Real money data
CREATE SCHEMA paper_trading;  -- Paper trading data

-- Each schema has identical tables:
-- - positions, orders, strategy_state, engine_state, events, account_balance

-- NO replay_trading schema!
-- Use paper_trading for replay testing
```

## Usage

### Starting Both Real and Paper Trading

```bash
# Run the launcher
python scripts/run_trading_launcher.py

# The launcher will:
# 1. Check config/trading_launcher.yaml
# 2. Start enabled engines as separate processes
# 3. Monitor processes and handle crashes
# 4. Gracefully shutdown on Ctrl+C
```

### Running Only Paper Trading (Testing)

```bash
python scripts/run_trading_launcher.py --paper-only
```

### Running Only Real Trading (Production)

```bash
python scripts/run_trading_launcher.py --real-only
```

## Configuration

### Main Launcher Config: `config/trading_launcher.yaml`

```yaml
# Data source - applies to ALL engines
data_source:
  mode: live  # or 'replay'

  # Replay settings (only used if mode=replay)
  replay:
    start_date: "2024-12-01"
    end_date: "2024-12-31"
    speed_multiplier: 1.0

# Toggle engines on/off
engines:
  real_trading:
    enabled: false  # Start disabled for safety
    config: config/live_trading_real.yaml

  paper_trading:
    enabled: true
    config: config/live_trading_paper.yaml
```

### Real Trading Config: `config/live_trading_real.yaml`

```yaml
engine:
  paper_trading: false  # CRITICAL: false = real money!
  max_positions: 5
  # ... rest of config
```

### Paper Trading Config: `config/live_trading_paper.yaml`

```yaml
engine:
  paper_trading: true  # Simulated
  max_positions: 25  # Can be more aggressive
  # ... rest of config
```

## How It Works

### 1. Trading Launcher

The launcher (`scripts/run_trading_launcher.py`) is the main entry point:

```python
launcher = TradingLauncher(config_path='config/trading_launcher.yaml')
launcher.start()

# Launcher creates child processes:
# - Real trading process (if enabled)
# - Paper trading process (if enabled)
#
# Each process runs its own LiveTradingEngine
```

### 2. Live Trading Engine

Each engine is initialized with a required `trading_mode`:

```python
# In child process 1 (real trading)
engine = LiveTradingEngine(
    trading_mode='real',
    config_path='config/live_trading_real.yaml'
)
engine.initialize()
engine.start()

# In child process 2 (paper trading)
engine = LiveTradingEngine(
    trading_mode='paper',
    config_path='config/live_trading_paper.yaml'
)
engine.initialize()
engine.start()
```

### 3. State Store

Each engine has its own StateStore pointing to a different schema:

```python
# Real engine
state_store = StateStore(trading_mode='real')
# Uses real_trading schema

# Paper engine
state_store = StateStore(trading_mode='paper')
# Uses paper_trading schema

# Completely isolated - no data mixing possible
```

### 4. Data Feed

**Both engines consume the same Redis topics:**

```python
# Both subscribe to:
redis_feed.subscribe('options_bars')
redis_feed.subscribe('underlying_bars')

# Data source (live vs replay) doesn't matter to engines
# They just process whatever comes through Redis
```

## Benefits

### Complete Isolation

```sql
-- Real and paper data completely separate
SELECT * FROM real_trading.positions;   -- Real positions
SELECT * FROM paper_trading.positions;  -- Paper positions

-- Different balances, different P&L
SELECT * FROM real_trading.account_balance;
SELECT * FROM paper_trading.account_balance;
```

### Parallel Operation

- Run conservative strategies in real mode
- Run aggressive strategies in paper mode
- Both using the same live data
- Compare results in real-time

### Data Source Independence

```yaml
# Live market data
data_source:
  mode: live

# Both engines get live data
# Real engine trades with real money
# Paper engine simulates trades
```

```yaml
# Replay historical data
data_source:
  mode: replay
  replay:
    start_date: "2024-12-01"
    end_date: "2024-12-31"

# Both engines get replay data
# Real engine can trade (if enabled - usually not recommended)
# Paper engine tests strategies on historical data
```

### Independent Control

```bash
# Kill only paper engine (real keeps running)
pkill -f "paper-trading"

# Kill only real engine
pkill -f "real-trading"

# Restart just one engine
# (Launcher monitors and can auto-restart)
```

## Typical Workflows

### Workflow 1: Live Trading (Real + Paper)

```yaml
# config/trading_launcher.yaml
data_source:
  mode: live

engines:
  real_trading:
    enabled: true  # Real money, conservative strategies
  paper_trading:
    enabled: true  # Simulated, aggressive strategies
```

**Use Case:** Run proven strategies with real money while testing new strategies in paper mode.

### Workflow 2: Replay Testing (Paper Only)

```yaml
# config/trading_launcher.yaml
data_source:
  mode: replay
  replay:
    start_date: "2024-12-01"
    end_date: "2024-12-31"

engines:
  real_trading:
    enabled: false  # Don't trade real money on replay
  paper_trading:
    enabled: true   # Test strategies on historical data
```

**Use Case:** Backtest strategies using replay service with full engine simulation.

### Workflow 3: Paper Only (Pre-Production Testing)

```yaml
# config/trading_launcher.yaml
data_source:
  mode: live

engines:
  real_trading:
    enabled: false
  paper_trading:
    enabled: true
```

**Use Case:** Test strategies with live market data before going live with real money.

## Migration Guide

### If You Already Ran the Old Migration

```sql
-- Drop the old replay_trading schema if it exists
DROP SCHEMA IF NOT EXISTS replay_trading CASCADE;

-- Re-run the updated migration
\i src/quant_vibe/data/schema/migrations/010_add_trading_modes.sql
```

### Update Your Launch Scripts

**Old Way:**
```python
# DON'T DO THIS ANYMORE
engine = LiveTradingEngine(config_path='config/live_trading.yaml')
```

**New Way:**
```python
# Use the launcher
python scripts/run_trading_launcher.py
```

Or if you need to run engines directly:
```python
# Specify trading_mode explicitly
engine = LiveTradingEngine(
    trading_mode='paper',  # Required!
    config_path='config/live_trading_paper.yaml'
)
```

## Monitoring

### Check Running Engines

```bash
# See which engines are running
ps aux | grep "trading"

# Should see:
# - run_trading_launcher.py (parent)
# - real-trading (child process, if enabled)
# - paper-trading (child process, if enabled)
```

### Compare Performance

```sql
-- Compare real vs paper
SELECT * FROM compare_trading_modes();

-- Output:
--  mode  | cash     | portfolio_value | total_pnl | total_trades | win_rate
-- -------|----------|-----------------|-----------|--------------|----------
--  real  | 98500.00 | 99200.00        | -800.00   | 15           | 0.60
--  paper | 105200.00| 108500.00       | 8500.00   | 42           | 0.65
```

### Monitor Logs

```bash
# Real trading logs
tail -f logs/live_trading/real-trading.log

# Paper trading logs
tail -f logs/live_trading/paper-trading.log
```

## Safety Features

### Real Trading Protection

1. **Disabled by default** in launcher config
2. **Warning messages** on startup if real mode enabled
3. **Can't clear real data** (safety check in StateStore)
4. **Separate schema** - impossible to mix with paper data

### Process Isolation

- One engine crash doesn't affect the other
- Can restart individual engines
- Graceful shutdown on Ctrl+C
- Force kill if needed (timeout)

### Config Validation

- `trading_mode` parameter is required
- Mode must match config (`paper_trading` flag)
- Warning if mismatch detected
- Clear error messages

## Troubleshooting

### Issue: No engines start

**Check:** `config/trading_launcher.yaml`

```yaml
engines:
  real_trading:
    enabled: true  # or false
  paper_trading:
    enabled: true  # or false
```

At least one must be `enabled: true`.

### Issue: Engine crashes immediately

**Check:** Engine-specific config file exists
- `config/live_trading_real.yaml`
- `config/live_trading_paper.yaml`

**Check:** Database schemas exist
```sql
\dn  -- Should show real_trading and paper_trading
```

### Issue: Data not flowing to engines

**Check:** Redis is running and data is being published
```bash
redis-cli
> SUBSCRIBE options_bars
# Should see messages if StreamingService/ReplayService is running
```

### Issue: Modes getting mixed up

**Solution:** This should be impossible now! Each mode uses a different schema.

If you see mixed data:
1. Check which schema you're querying
2. Verify `trading_mode` parameter was passed correctly
3. Check logs for which schema the engine connected to

## Summary

✅ Real and paper trading run as **separate processes**
✅ **Complete database isolation** (different schemas)
✅ **Same data source** for both (live or replay)
✅ **Toggle-able** - enable/disable each mode independently
✅ **Safe** - can't accidentally mix real and paper data
✅ **Flexible** - test aggressive strategies in paper while running conservative in real

This architecture provides the foundation for robust, isolated trading with clear separation between real money and simulated trading.
