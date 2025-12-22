# SPXW Options Streaming Service

A production-ready service for streaming SPXW options data from Schwab API and storing aggregated bars in TimescaleDB.

## Architecture

The service is organized into modular components:

```
streaming_service/
├── __init__.py          # Package exports
├── config.py            # Configuration dataclass
├── token_manager.py     # OAuth token refresh management
├── aggregator.py        # Quote-to-bar aggregation logic
└── service.py           # Main service orchestrator
```

## Components

### StreamingService (`service.py`)

Main orchestrator that coordinates all components:
- Token management (auto-refresh every 14 minutes)
- Contract discovery and subscription
- Quote streaming and enrichment
- Bar aggregation
- Database persistence

### TokenManager (`token_manager.py`)

Manages OAuth token lifecycle:
- Automatic token refresh at configurable intervals
- Token age tracking
- Success/failure logging

### BarAggregator (`aggregator.py`)

Aggregates streaming quotes into OHLCV bars:
- Buffered quote accumulation
- Configurable aggregation intervals (default: 60s)
- VWAP calculation
- Contract detail parsing

### StreamingConfig (`config.py`)

Configuration dataclass with validation:
- DTE range (min/max days to expiration)
- Strike range (percentage of underlying)
- Aggregate interval (seconds)
- Token refresh interval (minutes)
- Maximum symbols per subscription

## Usage

### Basic Usage

```python
from streaming_service import StreamingService, StreamingConfig

# Use default configuration
service = StreamingService()
service.start()
```

### Custom Configuration

```python
from streaming_service import StreamingConfig, StreamingService

config = StreamingConfig(
    max_dte=7,                      # Only 0-7 DTE contracts
    min_dte=0,
    strike_range_pct=0.05,          # ±5% from ATM
    aggregate_interval_seconds=300,  # 5-minute bars
    token_refresh_minutes=10,        # Refresh every 10 minutes
)

service = StreamingService(config)
service.start()
```

### Via Script

```bash
# Default settings (0-45 DTE, ±10% strikes, 1-min bars)
python scripts/stream_spxw_schwabdev.py

# Custom settings
python scripts/stream_spxw_schwabdev.py \
    --max-dte 7 \
    --strike-range-pct 0.05 \
    --aggregate-interval 300 \
    --token-refresh-minutes 10
```

## Features

### Automatic Token Refresh

- Refreshes OAuth token at startup
- Auto-refreshes every N minutes (configurable, default: 14)
- Logs success/failure to console
- Displays token age in status updates

### Quote Enrichment

- Enriches streaming quotes with contract details from option chain API
- Fills in missing Greeks, strike price, IV
- Caches contract details for 15 minutes

### Data Aggregation

- Buffers incoming quote updates
- Aggregates into OHLCV bars at configured intervals
- Calculates VWAP from volume-weighted prices
- Handles cumulative volume correctly

### Database Storage

- Stores bars in TimescaleDB `options_bars` table
- Automatic compression after 7 days
- Continuous aggregates (5min, 15min, 1hour, daily)

## Configuration Options

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_dte` | 45 | Maximum days to expiration |
| `min_dte` | 0 | Minimum days to expiration |
| `strike_range_pct` | 0.10 | Strike range (±10% from ATM) |
| `aggregate_interval_seconds` | 60 | Bar interval (60s = 1min bars) |
| `token_refresh_minutes` | 14 | Token refresh interval |
| `max_symbols_per_subscription` | 500 | Schwab subscription limit |
| `tokens_db_path` | `tokens/schwabdev_tokens.db` | Token database path |
| `enrichment_refresh_minutes` | 15 | Contract cache refresh interval |

## Environment Variables

Required in `.env`:

```bash
SCHWAB_API_KEY=your_api_key
SCHWAB_API_SECRET=your_api_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/

TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_DB=options_data
TIMESCALE_USER=quantvibe
TIMESCALE_PASSWORD=quantvibe_dev
```

## Status Updates

The service logs status updates every minute:

```
📊 Status Update [2025-12-19 14:56:29]:
   Messages received: 1234
   Contracts streaming: 150
   Buffered symbols: 45
   Contract cache: 150 contracts
   Cache age: 3.2 minutes
   Token age: 5.5 minutes
```

## Error Handling

- Token refresh failures are logged but don't stop the service
- API errors are logged with response details
- Database errors are logged but buffering continues
- Malformed messages are caught and logged

## Stopping the Service

Press `Ctrl+C` to gracefully stop:
1. Flushes remaining buffered data
2. Stops streaming connection
3. Closes database connection

## Development

### Adding New Features

**To add a new component:**
1. Create new module in `streaming_service/`
2. Import and initialize in `service.py`
3. Export from `__init__.py`

**To modify aggregation logic:**
Edit `aggregator.py` - the `BarAggregator` class is self-contained

**To change token refresh behavior:**
Edit `token_manager.py` - the `TokenManager` class handles all token logic

## Testing

```bash
# Test imports
python -c "from streaming_service import StreamingService, StreamingConfig; print('OK')"

# Test configuration
python -c "from streaming_service import StreamingConfig; c = StreamingConfig(max_dte=7); print(c)"

# Run service with verbose output
python scripts/stream_spxw_schwabdev.py
```

## Architecture Benefits

- **Modularity**: Each component has a single responsibility
- **Testability**: Components can be tested in isolation
- **Reusability**: Components can be used in other projects
- **Maintainability**: Clear separation of concerns
- **Configurability**: Easy to customize via config object
