# Live Trading Engine - Phase 1 Complete

## Overview

Phase 1 of the live trading engine has been completed. This phase establishes the core infrastructure needed for real-time options trading.

## What Was Built

### 1. Core Components

#### **LiveTradingEngine** (`src/quant_vibe/live/engine.py`)
- Main orchestrator for all trading operations
- Manages lifecycle: initialization → running → shutdown
- Integrates all components (data feed, state store, strategies)
- Handles graceful shutdown on SIGINT/SIGTERM
- Built-in safety: paper trading mode by default

#### **RealtimeDataFeed** (`src/quant_vibe/live/data_feed.py`)
- Consumes streaming data from schwabdev
- Aggregates quotes into 1-minute bars
- Maintains sliding window of recent bars (default: 100)
- Tracks underlying prices
- Callback system for new bar notifications
- Data staleness detection

#### **StateStore** (`src/quant_vibe/live/state_store.py`)
- Database persistence layer using TimescaleDB
- Stores engine state, positions, orders, strategy state
- Comprehensive audit trail (events log)
- Supports engine restart without losing positions
- Tables:
  - `live_engine_state` - Engine status
  - `live_positions` - Active and closed positions
  - `live_orders` - Order tracking
  - `live_strategy_state` - Strategy-specific state
  - `live_events` - Audit log (time-series)

#### **Utilities** (`src/quant_vibe/live/utils.py`)
- Comprehensive logging system (console + file)
- Trading state enums
- Event type constants
- Market hours checking
- Currency/percentage formatters

### 2. Configuration

#### **YAML Configuration** (`config/live_trading.yaml`)
Complete configuration file with:
- Engine settings (paper trading, position limits, loss limits)
- Strategy configuration (pluggable)
- Data feed settings (DTE range, strike range)
- Risk management parameters
- Monitoring & alerts
- Logging configuration
- Emergency controls (kill switch, EOD close)

### 3. Entry Point

#### **Run Script** (`scripts/run_live_trading.py`)
- User-friendly CLI for starting the engine
- Safety confirmation for live trading mode
- Dry-run mode for testing
- Configurable logging levels
- Clear usage instructions

## Directory Structure

```
src/quant_vibe/live/
├── __init__.py            # Package exports
├── engine.py              # Main LiveTradingEngine
├── data_feed.py           # Real-time data consumer
├── state_store.py         # State persistence
└── utils.py               # Utilities and helpers

config/
└── live_trading.yaml      # Configuration file

scripts/
└── run_live_trading.py    # Entry point script

logs/live_trading/         # Log files (created at runtime)

docs/
└── LIVE_TRADING_PHASE1.md # This file
```

## Database Schema

The following tables are created in TimescaleDB:

| Table | Purpose |
|-------|---------|
| `live_engine_state` | Track engine lifecycle |
| `live_positions` | Open/closed positions with P&L |
| `live_orders` | Order submission and status |
| `live_strategy_state` | Per-strategy state management |
| `live_events` | Complete audit trail |

All tables include timestamps and JSONB fields for flexibility.

## Safety Features

✅ **Paper Trading Mode** - Default mode, no real money at risk
✅ **Configuration Validation** - Sane defaults, easy to override
✅ **Graceful Shutdown** - Clean exit on Ctrl+C
✅ **Data Staleness Detection** - Alerts if data feed stops
✅ **Comprehensive Logging** - Debug and audit everything
✅ **State Persistence** - Survive crashes and restarts

## How to Use

### 1. Install Dependencies

```bash
pip install -e ".[live]"  # If live dependencies are specified
# OR ensure these are installed:
pip install pyyaml schwabdev psycopg2-binary
```

### 2. Configure

Edit `config/live_trading.yaml`:
- Set `paper_trading: true` (already default)
- Configure data feed settings
- Adjust risk limits
- Enable/disable strategies (when available)

### 3. Run

```bash
# Dry run (initialize only)
python scripts/run_live_trading.py --dry-run

# Start in paper trading mode
python scripts/run_live_trading.py

# Debug mode
python scripts/run_live_trading.py --log-level DEBUG
```

### 4. Monitor

- Watch console output for status updates
- Check logs in `logs/live_trading/live_trading_YYYYMMDD.log`
- Query database for detailed audit trail

```sql
-- Check engine state
SELECT * FROM live_engine_state ORDER BY timestamp DESC LIMIT 10;

-- Check events
SELECT * FROM live_events ORDER BY timestamp DESC LIMIT 100;

-- Check positions
SELECT * FROM live_positions WHERE status = 'open';
```

## What's NOT Included (Yet)

The following will be implemented in future phases:

❌ Strategy execution logic (Phase 3)
❌ Order submission to broker (Phase 2)
❌ Position tracking & valuation (Phase 2)
❌ Risk management checks (Phase 4)
❌ Monitoring dashboard (Phase 5)
❌ Email/SMS alerts (Phase 5)

## Testing Phase 1

You can test Phase 1 components individually:

```python
# Test data feed
from quant_vibe.live import RealtimeDataFeed

feed = RealtimeDataFeed(window_size=50)
# Pass feed.handle_message to schwabdev stream

# Check stats
print(feed.get_stats())
print(feed.get_bars())
```

```python
# Test state store
from quant_vibe.live import StateStore

store = StateStore()

# Log an event
store.log_event('test', 'Testing state store', severity='info')

# Get recent events
events = store.get_recent_events(limit=10)
print(events)

store.close()
```

```python
# Test engine (dry run)
from quant_vibe.live import LiveTradingEngine

engine = LiveTradingEngine()
engine.initialize()
print(engine.get_status())
```

## Next Steps (Phase 2)

Phase 2 will implement:
1. **OrderManager** - Submit orders to Schwab
2. **PositionManager** - Track and value positions
3. Multi-leg spread order construction
4. Order status tracking
5. Fill notifications

## Notes

- All components use TimescaleDB for persistence
- Data feed callback system allows multiple strategies to consume the same stream
- State store enables engine restart without losing positions
- Comprehensive event logging provides full audit trail
- Paper trading mode is enforced by default for safety

## Support

For issues or questions:
1. Check logs in `logs/live_trading/`
2. Query `live_events` table for audit trail
3. Review configuration in `config/live_trading.yaml`
4. Test components individually as shown above

---

**Status**: ✅ Phase 1 Complete
**Next Phase**: Order & Position Management
**Safe to Run**: Yes (paper trading mode only)
