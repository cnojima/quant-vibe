# Replay Service

The replay service allows you to test live trading strategies after market hours by replaying historical market data from TimescaleDB through Redis.

## Key Features

- **No Database Pollution**: Publishes to separate Redis topics (`replay.options_bars`, `replay.underlying_bars`)
- **Timing Control**: Real-time, accelerated (10x), or instant replay
- **Flexible Timeframes**: Easy specification of "today", "yesterday", "last_1h", specific dates, or custom ranges
- **Drop-in Testing**: Live trading service works without changes - just switch the config mode

## Architecture

```
┌─────────────────────────────────────────────────┐
│ REPLAY SERVICE                                   │
│                                                  │
│ TimescaleDB (Historical Data)                   │
│          ↓                                       │
│ ReplayDataLoader (fetch bars by timeframe)      │
│          ↓                                       │
│ ReplayPublisher (publish at original timing)    │
│          ↓                                       │
│ Redis Pub/Sub (replay.options_bars, etc.)      │
│          ↓                                       │
│ RedisDataFeed (same consumer as live)          │
└─────────────────────────────────────────────────┘
```

## Usage

### 1. Start the Replay Service

```bash
# Replay yesterday's market hours at real-time speed
python scripts/run_replay.py --timeframe yesterday

# Replay today at 10x speed (6 hours in 36 minutes)
python scripts/run_replay.py --timeframe today --speed 10

# Replay last 1 hour as fast as possible
python scripts/run_replay.py --timeframe last_1h --speed 0

# Replay specific date
python scripts/run_replay.py --timeframe 2025-01-03 --speed 5

# Replay custom range
python scripts/run_replay.py --timeframe "2025-01-03T14:00:00/2025-01-03T15:30:00"
```

### 2. Configure Live Trading for Replay Mode

Edit `config/live_trading.yaml`:

```yaml
data_feed:
  mode: "replay"  # Change from "live" to "replay"
  window_size: 100
  # ... other settings
```

### 3. Start Live Trading

```bash
# Live trading will now consume replay data
python scripts/run_live_trading.py
```

The live trading service will:
- Subscribe to `replay.options_bars` and `replay.underlying_bars` topics
- Process data exactly as if it were live
- Execute strategies, manage positions, etc.
- NOT write market data back to database (only StreamingService does that)

### 4. Switch Back to Live Mode

Edit `config/live_trading.yaml`:

```yaml
data_feed:
  mode: "live"  # Back to live streaming
```

## Timeframe Formats

| Format | Description | Example |
|--------|-------------|---------|
| `today` | Market hours today (9:30 AM - 4:00 PM ET) | `--timeframe today` |
| `yesterday` | Market hours previous trading day | `--timeframe yesterday` |
| `last_1h` | Most recent 1 hour | `--timeframe last_1h` |
| `1h`, `30m` | Short form (last N hours/minutes) | `--timeframe 1h` |
| `2025-01-03` | Specific date (market hours) | `--timeframe 2025-01-03` |
| `START/END` | Exact ISO 8601 range | `--timeframe "2025-01-03T14:00:00/2025-01-03T15:30:00"` |

## Speed Options

| Speed | Description | Use Case |
|-------|-------------|----------|
| `1.0` | Real-time (1 min = 1 min) | Realistic testing with original timing |
| `10.0` | 10x faster (1 min = 6 sec) | Quick backtesting of full day |
| `60.0` | 60x faster (1 hour = 1 min) | Very fast replay |
| `0` | Instant (no delays) | Maximum throughput testing |

## CLI Options

```bash
python scripts/run_replay.py --help

Options:
  --timeframe TEXT         Timeframe to replay (default: "yesterday")
  --speed FLOAT            Speed multiplier (default: 1.0)
  --preserve-timestamps    Keep original timestamps (default: shift to now)
  --underlying TEXT        Underlying ticker (default: SPX)
  --min-dte INTEGER        Minimum days to expiration (default: 0)
  --max-dte INTEGER        Maximum days to expiration (default: 45)
  --db-profile TEXT        Database profile: local or remote (default: auto)
  --log-level TEXT         Logging level (default: INFO)
```

## Example Workflow

### Test a Strategy on Yesterday's Data

```bash
# Terminal 1: Start replay service
python scripts/run_replay.py --timeframe yesterday --speed 10

# Terminal 2: Configure and start live trading
# 1. Edit config/live_trading.yaml -> set mode: "replay"
# 2. Enable only the strategy you want to test
python scripts/run_live_trading.py
```

### Quick Test on Last Hour

```bash
# Terminal 1: Instant replay of last hour
python scripts/run_replay.py --timeframe last_1h --speed 0

# Terminal 2: Live trading in replay mode
python scripts/run_live_trading.py
```

## Safety Features

### No Database Pollution

The replay service:
- ✅ Reads from TimescaleDB (options_bars, underlying_bars tables)
- ✅ Publishes to Redis (`replay.*` topics)
- ❌ Does NOT write back to database

StreamingService (the only writer):
- ✅ Receives live data from Schwab
- ✅ Writes to TimescaleDB
- ✅ Publishes to Redis (`streaming.*` topics)
- ❌ Does NOT subscribe to `replay.*` topics

### Topic Isolation

```python
# Live streaming topics
Topic.OPTIONS_BARS = "streaming.options_bars"
Topic.UNDERLYING_BARS = "streaming.underlying_bars"

# Replay topics (separate)
Topic.REPLAY_OPTIONS_BARS = "replay.options_bars"
Topic.REPLAY_UNDERLYING_BARS = "replay.underlying_bars"
```

RedisDataFeed automatically selects topics based on mode:
- `mode: "live"` → subscribes to `streaming.*`
- `mode: "replay"` → subscribes to `replay.*`

## Components

### `timeframe.py`
Parses timeframe strings into UTC datetime ranges.

### `data_loader.py`
Loads historical bars from TimescaleDB for the specified timeframe.

### `publisher.py`
Publishes bars to Redis with timing control (speed multiplier).

### `service.py`
Main orchestrator that coordinates loading, timing, and publishing.

## Logging

Logs are written to `logs/replay/`:
```
logs/replay/replay_YYYYMMDD.log
```

Set log level with `--log-level`:
```bash
python scripts/run_replay.py --timeframe today --log-level DEBUG
```

## Troubleshooting

### "No data found for timeframe"

Check available data:
```sql
SELECT MIN(timestamp), MAX(timestamp)
FROM options_bars
WHERE underlying_ticker='SPX';
```

### Live trading not receiving data

1. Verify replay service is running
2. Check Redis connection (same host/port in both configs)
3. Confirm `mode: "replay"` in `config/live_trading.yaml`
4. Check logs for subscription confirmation:
   ```
   Using REPLAY topics (replay.options_bars, replay.underlying_bars)
   ```

### Replay too slow/fast

Adjust `--speed`:
- Too slow: Increase to 10, 20, 60
- Too fast: Decrease to 1.0 or 2.0
- Testing throughput: Use `--speed 0` for instant

## Development

To add new features or modify:

1. **Add new timeframe format**: Edit `timeframe.py` > `parse_timeframe()`
2. **Change timing logic**: Edit `publisher.py` > `replay_with_timing()`
3. **Add filters/transforms**: Edit `data_loader.py` > `load_bars()`
4. **Modify topics**: Edit `src/quant_vibe/messaging/topics.py`
