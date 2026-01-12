# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Testing
```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/unit/test_indicators.py

# Run tests matching a pattern
pytest -k "test_sma"

# Run with verbose output and coverage report
pytest -v --cov=src --cov-report=term-missing

# Run only unit tests or integration tests
pytest tests/unit/
pytest tests/integration/
```

### Code Quality
```bash
# Format all code with Black
black src tests

# Check linting with Ruff
ruff check src tests

# Fix auto-fixable linting issues
ruff check --fix src tests

# Run type checking with mypy
mypy src
```

### Logging

All components use normalized logging format: `[datetime][app][level][msg]`

**Setup logging in your component:**
```python
from quant_vibe.config.logging_config import setup_normalized_logging

logger = setup_normalized_logging(
    app_name="my_component",  # backtest, live, streaming_service, etc.
    log_level="INFO",
    log_dir="logs/my_component",
)

logger.info("Normal message")
logger.warning("Warning message")
logger.error("Error with stack trace", exc_info=True)
```

**Features:**
- Normalized format: `[2025-12-25 12:00:00][backtest][INFO    ] Message`
- Multi-line messages with proper indentation
- Stack trace handling with alignment
- Dual output: console + file
- Per-component log files: `logs/{app_name}/{app_name}_{date}.log`
- **Automatic log rotation**: Rotates at midnight EST (Eastern Time)
- **Timezone-aware**: All timestamps in EST for market alignment
- **Retention policy**: Keeps 30 days of rotated logs by default

**Log Rotation:**
- Files automatically rotate at midnight EST (00:00:00 America/New_York)
- Current file: `app_20251230.log`
- Rotated files: `app_20251230.log.2025-12-29_EST`
- See `docs/LOG_ROTATION.md` for detailed documentation

## Architecture Overview

### Peer Component Architecture

The codebase is organized into four peer components at the `src/` level:

1. **`src/backtest/`** - Top-level backtesting orchestrator (config-driven)
2. **`src/streaming_service/`** - Real-time data streaming service (Schwab API → Redis → TimescaleDB)
3. **`src/live_trading_service/`** - Live trading engine (Redis → Strategy Execution → Orders)
4. **`src/quant_vibe/`** - Core library with reusable components

This peer structure promotes:
- ✅ **Separation of concerns**: Each component has a specific responsibility
- ✅ **Reusability**: Components can import from quant_vibe library
- ✅ **Independent deployment**: Each can be deployed/scaled separately
- ✅ **Clear boundaries**: Top-level orchestrators vs. core framework

### Messaging Architecture (Redis Pub/Sub)

The system uses **Redis pub/sub** for real-time communication between services:

**StreamingService** (Publisher):
- Subscribes to Schwab API websocket once
- Aggregates quotes into 1-minute bars
- Publishes to Redis topics: `streaming.options_bars` and `streaming.underlying_bars`
- Also persists to TimescaleDB for historical analysis

**LiveTradingEngine** (Subscriber):
- Subscribes to Redis topics (no direct Schwab connection)
- Receives real-time bars from StreamingService
- Executes strategies and places orders via Schwab REST API

**Benefits**:
- ✅ **Single streaming connection**: Avoids duplicate Schwab websocket connections
- ✅ **Lower API load**: One connection shared across multiple consumers
- ✅ **Retry mechanism**: Exponential backoff for API errors
- ✅ **Decoupled services**: StreamingService and LiveTradingEngine run independently
- ✅ **Scalable**: Multiple live trading instances can subscribe to same feed

**Configuration**:
```yaml
redis:
  host: null  # Uses REDIS_HOST env var or 'localhost'
  port: null  # Uses REDIS_PORT env var or 6379
  db: null    # Uses REDIS_DB env var or 0
```

**Message Broker API** (`src/quant_vibe/messaging/`):
```python
from quant_vibe.messaging import RedisMessageBroker, Topic

# Publisher
broker = RedisMessageBroker()
broker.publish(Topic.OPTIONS_BARS, bar_data)

# Subscriber
def on_message(topic, data):
    print(f"Received {topic}: {data}")

broker.subscribe([Topic.OPTIONS_BARS], callback=on_message)
broker.listen()  # Blocking
```

**Retry Utilities** (`src/quant_vibe/utils/retry.py`):
```python
from quant_vibe.utils import retry_with_backoff

@retry_with_backoff(max_retries=3, backoff_base=2.0)
def fetch_data():
    response = client.quote("$SPX")
    response.raise_for_status()
    return response.json()
```

### Core Module Structure

The codebase follows a layered architecture within `quant_vibe/`:

**Data Layer** (`src/quant_vibe/data/`)
- `MarketDataClient`: Fetches data from external APIs (Alpha Vantage, Polygon, etc.)
- `DataStore`: Local caching and persistence using parquet/CSV formats
- Environment credentials loaded via python-dotenv from `.env`

**Indicators Layer** (`src/quant_vibe/indicators/`)
- Pure functions for technical analysis calculations (SMA, EMA, RSI, MACD)
- All functions take pandas Series/DataFrame and return the same type
- No state or side effects - fully functional design

**Strategy Layer** (`src/quant_vibe/strategies/`)
- `Strategy` (base class): Abstract base defining the strategy interface
- Concrete strategies inherit from `Strategy` and implement `generate_signals()`
- Signals use `Signal` enum: BUY=1, SELL=-1, HOLD=0
- `validate_data()` ensures OHLCV columns exist before processing

**Backtesting Layer** (`src/quant_vibe/backtesting/`)
- `BacktestEngine`: Simulates trading based on strategy signals
  - Tracks positions, cash, and portfolio value over time
  - Models transaction costs via commission parameter
  - Returns portfolio DataFrame with complete history
- `PerformanceMetrics`: Calculates analytics (Sharpe ratio, max drawdown, win rate, etc.)

**Top-Level Backtesting** (`src/backtest/`)
- `BacktestOrchestrator`: High-level engine for config-driven backtests
  - Loads strategies and parameters from YAML configuration
  - Handles data loading, execution, reporting, and saving
  - Peer component to quant_vibe and streaming_service
- `BacktestConfig`: Configuration loader and validator
- CLI entry point: `scripts/run_backtest.py`
- Configuration: `config/backtest.yaml`

**Live Trading Service** (`src/live_trading_service/`)
- `LiveTradingEngine`: Real-time trading orchestrator (peer component)
  - Subscribes to Redis for market data from StreamingService
  - Coordinates strategy execution, order management
  - Supports paper trading and live trading modes
  - Position tracking, risk management, state persistence
- `RedisDataFeed`: Consumes data from Redis pub/sub
- CLI entry point: `scripts/run_live_trading.py`
- Configuration: `config/live_trading.yaml`

**Utilities Layer** (`src/quant_vibe/utils/`)
- `TeeOutput`: Dual output writer (console + file logging)
- `get_date_range()`: Interactive date range selection
- `make_utc_datetime()`: Timezone-aware datetime creation
- `setup_logging()`: Application logging configuration
- `setup_backtest_output()`: One-line backtest logging setup
- `load_options_backtest_data()`: Load and validate options data from TimescaleDB
- `save_backtest_results()`: Save backtest outputs to CSV files
- `BacktestReporter`: Comprehensive trade details and educational metrics reporting

### Key Design Patterns

**Strategy Pattern**: All trading strategies implement the `Strategy` base class with `generate_signals()` method. This allows easy swapping and testing of different strategies.

**Repository Pattern**: `DataStore` abstracts data persistence, allowing easy switching between file formats (parquet, CSV) or future addition of database backends.

**Functional Core, Imperative Shell**: Indicator calculations are pure functions. Side effects (API calls, file I/O) are isolated in data layer.

### Data Flow

1. **Data Acquisition**: `MarketDataClient` fetches OHLCV data → `DataStore` caches locally
2. **Strategy Application**: Strategy reads cached data → calculates indicators → generates signals
3. **Backtesting**: `BacktestEngine` applies signals to historical data → simulates trades
4. **Analysis**: `PerformanceMetrics` computes statistics on backtest results

### Top-Level Architecture (Backtesting & Live Trading)

The codebase provides two parallel top-level orchestration layers for running strategies:

**1. Backtesting (Config-Driven)**
```
┌─────────────────────────────────────────────────────────┐
│  scripts/run_backtest.py (CLI Entry Point)             │
│  ├─ Parses command-line arguments                       │
│  └─ Initializes BacktestOrchestrator                    │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  src/backtest/engine.py                                 │
│  BacktestOrchestrator (Peer component)                  │
│  ├─ Loads config/backtest.yaml                          │
│  ├─ Validates configuration                             │
│  ├─ Loads data from TimescaleDB (via quant_vibe)        │
│  ├─ Instantiates strategies dynamically (quant_vibe)    │
│  ├─ Runs OptionsBacktestEngine for each strategy        │
│  ├─ Generates reports (BacktestReporter)                │
│  └─ Saves results to CSV                                │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  src/quant_vibe/backtesting/                            │
│  Core backtesting framework (reusable)                  │
│  ├─ OptionsBacktestEngine                               │
│  ├─ BacktestReporter                                    │
│  └─ PerformanceMetrics                                  │
└─────────────────────────────────────────────────────────┘
```

**2. Live Trading (Config-Driven)**
```
┌─────────────────────────────────────────────────────────┐
│  scripts/run_live_trading.py (CLI Entry Point)         │
│  ├─ Parses command-line arguments                       │
│  └─ Initializes LiveTradingEngine                       │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  src/quant_vibe/live/engine.py                          │
│  LiveTradingEngine                                      │
│  ├─ Loads config/live_trading.yaml                      │
│  ├─ Sets up data feed, order manager, position manager  │
│  ├─ Loads and runs strategies                           │
│  ├─ Manages risk, state persistence                     │
│  └─ Handles emergency controls                          │
└─────────────────────────────────────────────────────────┘
```

**Benefits of Top-Level Architecture**:
- ✅ **Consistency**: Same pattern for backtesting and live trading
- ✅ **Configuration-driven**: YAML configs instead of hardcoded scripts
- ✅ **Reusability**: Share strategies between backtest and live
- ✅ **Maintainability**: Changes in one place, not scattered across scripts
- ✅ **Batch execution**: Run multiple strategies with one command
- ✅ **CLI interface**: Easy to use, scriptable, automatable

**Usage Examples**:

Backtesting:
```bash
# Run all enabled strategies from config
python scripts/run_backtest.py

# Run specific strategy
python scripts/run_backtest.py --strategy bullish_vertical_put

# Use custom config
python scripts/run_backtest.py --config config/my_backtest.yaml
```

Live Trading:
```bash
# Run live trading engine (paper mode by default)
python scripts/run_live_trading.py

# Use custom config
python scripts/run_live_trading.py --config config/my_live_config.yaml
```

### Adding New Components

**New Strategy**:

⚠️ **IMPORTANT**: For complete step-by-step instructions with code examples, see **`docs/HOWTO_NEW_STRATEGY.md`**

**Quick Summary** (8 core steps):
1. **Create strategy class**: `src/quant_vibe/strategies/my_strategy.py` (inherit from `OptionsStrategy`)
2. **Implement methods**: `analyze_market()`, `should_enter()`, `construct_spread()`, `should_exit()`
3. **Export**: Add to `src/quant_vibe/strategies/__init__.py`
4. **Register for backtesting**: Add to `src/backtest/engine.py` → `strategy_map`
5. **Register for live trading**: Add to `src/quant_vibe/live/engine.py` → `strategy_classes`
6. **Expose to Admin UI**: Add to `src/admin_ui/backend/api/strategies.py` → `STRATEGY_METADATA`
7. **Configure**: Add to `config/backtest.yaml` and `config/live_trading.yaml`
8. **Test**: Add unit tests in `tests/unit/test_strategies.py`

**Key Files to Modify**:
- `src/quant_vibe/strategies/my_strategy.py` - Strategy implementation
- `src/quant_vibe/strategies/__init__.py` - Export strategy
- `src/backtest/engine.py` - Register for backtesting
- `src/quant_vibe/live/engine.py` - Register for live trading
- `src/admin_ui/backend/api/strategies.py` - Add metadata for Admin UI
- `config/backtest.yaml` - Backtest configuration
- `config/live_trading.yaml` - Live trading configuration
- `tests/unit/test_strategies.py` - Unit tests

**Admin UI Integration**:
After adding metadata to `strategies.py`, your strategy will automatically appear in the Admin UI (`http://localhost:5173/strategies`) with:
- Enable/disable toggle
- Parameter viewing (expandable)
- Auto-sync with YAML config
- Restart warnings

**Example Registration**:
```python
# src/backtest/engine.py
strategy_map = {
    'bullish_vertical_put': 'quant_vibe.strategies.bullish_vertical_put.BullishVerticalPutStrategy',
    'my_strategy': 'quant_vibe.strategies.my_strategy.MyStrategy',  # Add this
}

# src/admin_ui/backend/api/strategies.py
STRATEGY_METADATA = {
    "my_strategy": {
        "description": "Brief description for UI",
        "default_params": {
            "spread_width": 20.0,
            "profit_target_min": 0.50,
            "min_dte": 0,
            "max_dte": 45,
            # ... all constructor params
        },
    },
}
```

**Testing & Deployment Workflow**:
1. Run backtest: `python scripts/run_backtest.py --strategy my_strategy`
2. Analyze results, iterate on parameters
3. Enable in Admin UI → Strategies page
4. Paper trade for 1+ week (monitor via Admin UI → Live Trading Monitor)
5. Enable live trading via Config Editor (set `paper_trading: false`)

See **`docs/HOWTO_NEW_STRATEGY.md`** for complete walkthrough with code templates and troubleshooting.

**New Indicator**:
1. Add function to `src/quant_vibe/indicators/technical.py`
2. Follow signature: `calculate_X(data: pd.Series, ...) -> pd.Series`
3. Export from `indicators/__init__.py`
4. Add tests in `tests/unit/test_indicators.py`

**New Data Provider**:
1. Add provider logic to `MarketDataClient._load_credentials()` and `fetch_daily_data()`
2. Implement private method like `_fetch_provider_name_daily()`
3. Add required env vars to `.env.example`

**Running Backtests (Recommended - Config-Based)**:
1. Add strategy configuration to `config/backtest.yaml`:
   ```yaml
   strategies:
     enabled:
       - name: my_strategy
         enabled: true
         params:
           param1: value1
           param2: value2
   ```
2. Run backtest using CLI:
   ```bash
   # Run all enabled strategies
   python scripts/run_backtest.py

   # Run specific strategy
   python scripts/run_backtest.py --strategy my_strategy

   # Use custom config
   python scripts/run_backtest.py --config config/my_backtest.yaml
   ```

**Running Backtests (Legacy - Individual Scripts)**:
NOTE: This approach is deprecated in favor of the config-based orchestrator above.

1. Create file in `backtests/` directory (e.g., `backtest_my_strategy.py`)
2. Import utilities:
   ```python
   from quant_vibe.utils import (
       setup_backtest_output,
       get_date_range,
       load_options_backtest_data,
       save_backtest_results,
   )
   from quant_vibe.backtesting import BacktestReporter, OptionsBacktestEngine
   ```
3. Use `setup_backtest_output()` for logging setup (1 line)
4. Use `get_date_range()` for interactive date selection
5. Use `load_options_backtest_data()` to load data with validation (1 line)
6. Use `BacktestReporter` to display results (2 lines)
7. Use `save_backtest_results()` to save outputs (1 line)
8. Follow the complete pattern in "Backtest Utilities" section
9. See `backtests/backtest_bullish_vertical_put.py` for reference implementation

## Testing Philosophy

- **Unit tests**: Test individual functions/classes in isolation (indicators, strategies, data store)
- **Integration tests**: Test complete workflows (full backtest pipeline)
- **Fixtures**: `conftest.py` provides reusable test data (`sample_ohlcv_data`, `temp_data_dir`)
- Type hints enable mypy checking - all public functions should be typed

## Configuration

- **Environment variables**: API keys and config in `.env` (never commit this file)
- **Project config**: `pyproject.toml` contains dependencies, tool settings (black, ruff, mypy, pytest)
- **Data storage**: Defaults to `./data/` directory (gitignored)

## Common Patterns

**Loading cached data with fallback to API**:
```python
data = store.load(symbol)
if data is None:
    data = client.fetch_daily_data(symbol)
    store.save(symbol, data)
```

**Strategy usage**:
```python
strategy = SomeStrategy(param1=value1)
signals = strategy.generate_signals(ohlcv_data)  # Returns Series of 1, -1, 0
```

**Backtest workflow**:
```python
engine = BacktestEngine(initial_capital=100000.0, commission=0.001)
portfolio = engine.run(strategy, data)
metrics = PerformanceMetrics.calculate(portfolio)
```

## Backtest Utilities

The backtest utilities provide a complete framework for creating consistent, maintainable backtest scripts with minimal code duplication.

### Core Components

**Utilities Layer** (`src/quant_vibe/utils/`)

The utilities module provides reusable components for backtest scripts:

**1. Date & Time Utilities** (`datetime_utils.py`)

**IMPORTANT**: All date/time functions use **US Eastern Time (EST/EDT)** for market hours. This ensures consistent handling of trading days regardless of where you run the backtest.

Core functions:
- `make_utc_datetime(year, month, day, hour=0, minute=0, second=0)`: Create timezone-aware UTC datetime
- `trading_day_to_utc(year, month, day)`: Convert a trading day to UTC market hours range
  - **Market hours**: 9:30 AM - 4:00 PM EST (Eastern Time)
  - Example: Dec 22, 2025 → 2025-12-22 14:30:00 UTC to 2025-12-22 21:00:00 UTC
  - Returns tuple of (market_open_utc, market_close_utc)
- `is_trading_day(year, month, day)`: Check if a date is a trading day (Mon-Fri, excludes weekends)
- `get_trading_days_in_range(start_y, start_m, start_d, end_y, end_m, end_d)`: Get all trading days in a date range
- `get_date_range()`: Interactive date range selection with presets:
  - **Today**: Today's date in EST, market hours only (9:30 AM - 4:00 PM EST)
  - **This week**: Mon-Fri of current week, market hours for each trading day
  - **This month**: All trading days (Mon-Fri) in current month, market hours
  - **This quarter**: All trading days in current quarter, market hours
  - **This year**: All trading days in current year, market hours
  - **Custom**: User-specified date range, trading days only, market hours
  - **All options automatically**:
    - Use EST timezone (not user's local timezone or UTC)
    - Constrain to market hours (9:30 AM - 4:00 PM EST)
    - Exclude weekends (trading days only)
    - Convert to UTC for database queries

**2. Output Utilities** (`output.py`)
- `TeeOutput`: Dual output writer for console and log files
  - Automatically saves all print statements to both terminal and file
  - Useful for preserving complete backtest execution logs

**3. Backtest Helpers** (`backtest_helpers.py`)
- `setup_backtest_output(strategy_name, base_dir=None)`: Setup output directory, timestamp, and TeeOutput logger
  - Returns: `(output_dir, timestamp, tee_output)`
  - Automatically creates log file: `{strategy_name}_log_{timestamp}.txt`

- `load_options_backtest_data(underlying_ticker, start_date, end_date, min_dte, max_dte, verbose=True, db_profile=None)`: Load options and underlying data from TimescaleDB
  - Returns: `(options_data, underlying_data)` DataFrames
  - Includes validation, error handling, and verbose logging
  - Automatically derives underlying price from options bid/ask data
  - `db_profile`: Select database (default: auto-detect from `USE_REMOTE_TIMESCALE`)
    - `None` (default): Auto-selects based on `USE_REMOTE_TIMESCALE` env var
    - `"local"`: Forces local database using `TIMESCALE_*` environment variables
    - `"remote"`: Forces remote database using `REMOTE_TIMESCALE_*` environment variables

- `save_backtest_results(results, strategy_name, output_dir, timestamp, verbose=True)`: Save backtest results to CSV files
  - Returns: `{'trades': Path, 'equity': Path}` dictionary
  - Saves: `{strategy_name}_trades_{timestamp}.csv` and `{strategy_name}_equity_{timestamp}.csv`

**Backtesting Layer** (`src/quant_vibe/backtesting/`)

**4. Backtest Reporter** (`reporter.py`)
- `BacktestReporter`: Comprehensive reporting and analytics for backtest results

Methods:
- `print_trade_details(trades_df)`: Detailed trade-by-trade analysis
  - Entry/exit information
  - Position details (legs, strikes, premiums)
  - Performance metrics
  - Win/loss indication

- `print_educational_metrics(trades_df, equity_curve, initial_capital)`: Educational analytics
  - Trade timing analysis
  - Exit reason breakdown
  - Win/loss patterns and streaks
  - Risk/reward analysis
  - Drawdown analysis
  - Profit distribution
  - Entry trigger analysis
  - Day of week performance
  - Return metrics (ROI, annualized return)

### Creating a Backtest Script

**Recommended Pattern** (uses all utilities):
```python
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.backtesting import BacktestReporter, OptionsBacktestEngine
from quant_vibe.strategies.my_strategy import MyStrategy
from quant_vibe.utils import (
    get_date_range,
    load_options_backtest_data,
    save_backtest_results,
    setup_backtest_output,
)

def main():
    # Setup output logging (1 line instead of 10)
    output_dir, timestamp, tee = setup_backtest_output("my_strategy")
    sys.stdout = tee

    try:
        # Get date range from user
        start_date, end_date = get_date_range()

        # Configure strategy parameters
        strategy = MyStrategy(param1=value1, param2=value2)
        initial_capital = 100000.0

        # Load data (1 line instead of 60)
        # Use db_profile="local" (default) or db_profile="remote"
        options_data, underlying_data = load_options_backtest_data(
            underlying_ticker="SPX",
            start_date=start_date,
            end_date=end_date,
            min_dte=0,
            max_dte=45,
            # db_profile="remote",  # Uncomment to use remote database
        )

        # Run backtest
        engine = OptionsBacktestEngine(initial_capital=initial_capital)
        results = engine.run(
            strategy=strategy,
            underlying_data=underlying_data,
            options_data=options_data,
            start_date=start_date,
            end_date=end_date,
        )

        # Display results (2 lines instead of 250)
        reporter = BacktestReporter()
        reporter.print_trade_details(results["trades"])
        reporter.print_educational_metrics(
            results["trades"],
            results["equity_curve"],
            initial_capital,
        )

        # Save results (1 line instead of 20)
        save_backtest_results(
            results=results,
            strategy_name="my_strategy",
            output_dir=output_dir,
            timestamp=timestamp,
        )

    finally:
        tee.close()

if __name__ == "__main__":
    main()
```

**Result**: Backtest scripts reduced from ~470 lines to ~130 lines (~72% code reduction)

### Key Benefits

- **Consistency**: All backtest scripts use the same interfaces and patterns
- **Reusability**: No duplicate code across backtest scripts
- **Maintainability**: Changes to reporting/logging happen in one place
- **Logging**: Complete execution logs saved automatically
- **Timezone-aware**: All datetimes properly handle UTC timezone
- **Error Handling**: Built-in validation and error messages
- **Extensibility**: Easy to add new metrics or output formats

### Data Sync (Remote to Local)

**Syncing data from remote TimescaleDB (Moirae) to local development database:**

```bash
# Automated workflow (recommended)
./scripts/auto_sync_gaps.sh                    # Interactive mode
./scripts/auto_sync_gaps.sh --auto             # Fully automated
./scripts/auto_sync_gaps.sh --quick            # Quick scan (30 days)

# Manual analysis + sync
python scripts/analyze_data_gaps.py --quick --detailed
python scripts/sync_moirae.py --since 2025-12-01 --until 2025-12-31

# Daily sync (add to cron)
./scripts/auto_sync_gaps.sh --auto >> logs/daily_sync.log 2>&1
```

**Gap Analysis:**
- `analyze_data_gaps.py` - Identifies missing/incomplete data
- Detects: missing days, partial days (<80% coverage), sparse contracts
- Generates sync commands automatically

**Sync Tool:**
- `sync_moirae.py` - Syncs data with conflict handling (idempotent)
- Supports date ranges, auto-batching for large ranges
- Uses `ON CONFLICT` to update existing bars safely

**See:** `docs/DATA_SYNC_GUIDE.md` for comprehensive documentation

### Database Configuration

**Local vs Remote TimescaleDB**

The backtest utilities automatically detect which database to use based on the `USE_REMOTE_TIMESCALE` environment variable.

**Environment Variables** (`.env`):
```bash
# Database selection (set once, applies to all backtests)
USE_REMOTE_TIMESCALE=true  # or false for local database

# Local TimescaleDB credentials
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_DB=options_data
TIMESCALE_USER=quantvibe
TIMESCALE_PASSWORD=quantvibe_dev

# Remote TimescaleDB credentials
REMOTE_TIMESCALE_HOST=192.168.100.197  # your remote IP/hostname
REMOTE_TIMESCALE_PORT=5432
REMOTE_TIMESCALE_DB=options_data
REMOTE_TIMESCALE_USER=quantvibe
REMOTE_TIMESCALE_PASSWORD=your-remote-password
```

**Automatic Database Selection**:
```python
# Database is automatically selected from USE_REMOTE_TIMESCALE env var
options_data, underlying_data = load_options_backtest_data(
    underlying_ticker="SPX",
    start_date=start_date,
    end_date=end_date,
    min_dte=0,
    max_dte=45,
)
# If USE_REMOTE_TIMESCALE=true → uses remote database
# If USE_REMOTE_TIMESCALE=false → uses local database
```

**Manual Override** (optional):
```python
# Override environment variable for a specific call
options_data, underlying_data = load_options_backtest_data(
    underlying_ticker="SPX",
    start_date=start_date,
    end_date=end_date,
    min_dte=0,
    max_dte=45,
    db_profile="local",  # Force local database (ignores USE_REMOTE_TIMESCALE)
)

# Or force remote
options_data, underlying_data = load_options_backtest_data(
    underlying_ticker="SPX",
    start_date=start_date,
    end_date=end_date,
    min_dte=0,
    max_dte=45,
    db_profile="remote",  # Force remote database (ignores USE_REMOTE_TIMESCALE)
)
```

**Benefits**:
- ✅ Set once in `.env`, applies to all backtest scripts
- ✅ No code changes needed to switch between local/remote
- ✅ Can still override per-call if needed
- ✅ Verbose output shows which database is being used

## Code Style

- Line length: 100 characters (Black + Ruff configured)
- Type hints required for all function signatures (enforced by mypy)
- Docstrings: Google style with Args/Returns sections
- Import order: stdlib → third-party → local (sorted by Ruff)

## Options Trading System (SPXW)

### Architecture

The system now supports **options backtesting and real-time data collection** for SPXW (S&P 500 Weekly Options):

**Options Data Layer** (`src/quant_vibe/data/`)
- `TimescaleStore`: High-performance TimescaleDB integration for 1-minute options bars
  - Stores OHLCV, bid/ask quotes, Greeks (delta, gamma, theta, vega, rho)
  - Automatic compression for historical data
  - Continuous aggregates (5min, 15min, 1hour, daily)
- `MassiveClient`: Historical options data from Massive.io (formerly Polygon)
- `SchwabDevClient`: Real-time quotes and OAuth2 authentication using schwabdev
- Streaming service: Websocket streaming for live options data (uses schwabdev)
- Database schema: `src/quant_vibe/data/schema/init_timescale.sql`

**Options Strategy Layer** (`src/quant_vibe/strategies/`)
- `OptionsStrategy` (base class): Abstract base for multi-leg options strategies
- `OptionsPosition`: Represents spreads with multiple legs (vertical, iron condor, etc.)
- `OptionLeg`: Individual option contract in a spread
- Supports: profit targets, stop losses, trailing stops, Greeks tracking
- Example: `BullishVerticalCallStrategy` - 0 DTE intraday strategy

**Options Backtesting** (`src/quant_vibe/backtesting/`)
- `OptionsBacktestEngine`: Specialized engine for options strategies
  - Handles multi-leg positions and spreads
  - Tracks position P&L with bid/ask mark pricing
  - Supports intraday trading with 1-minute bars
  - Calculates Sharpe ratio, max drawdown, win rate
- Derives underlying price from ATM options when needed

### Data Sources

**Historical Data (Massive API)**
- 1-minute OHLCV bars for options
- Coverage: July 2025 - December 2025 (expandable)
- Stored in: TimescaleDB `options_bars` table
- Access: `TimescaleStore.get_options_for_backtest()`

**Real-Time Data (Schwab API)**
- Websocket streaming: `scripts/stream_spxw_realtime.py`
- Polling mode: `scripts/poll_spxw_quotes.py`
- Collects: bid/ask, Greeks, volume, IV
- Auto-aggregates into 1-minute bars
- Stores with tag: `schwab_realtime` or `schwab_poll`

### Key Scripts

**Data Collection**
```bash
# Backfill 0-2 DTE historical data from Massive API
python scripts/backfill_0dte_spxw.py

# Real-time streaming (websocket) - includes auto-enrichment
python scripts/stream_spxw_schwabdev.py

# Real-time polling (simpler, recommended for testing)
python scripts/poll_spxw_quotes.py

# Backfill missing Greeks/strike/IV in existing streaming data
python scripts/backfill_stream_greeks.py --stats-only  # Check status
python scripts/backfill_stream_greeks.py --dry-run     # Preview changes
python scripts/backfill_stream_greeks.py               # Run backfill
```

**Backtesting**
```bash
# Backtest bullish vertical call spread strategy
python scripts/backtest_bullish_vertical_call.py

# Test 0 DTE data availability
python scripts/test_0dte_availability.py
```

### Options Data Flow

1. **Historical Backfill**: Massive API → `backfill_0dte_spxw.py` → TimescaleDB
   - Fetches OHLCV bars for expired contracts
   - Estimates bid/ask spreads based on DTE and price
   - Covers 0-2 DTE for daily SPXW expirations (Mon-Fri)

2. **Real-Time Collection**: Schwab API → `stream_spxw_schwabdev.py` → TimescaleDB
   - Subscribes to active contracts (0-45 DTE, ±10% ATM)
   - Aggregates quote updates into 1-minute bars
   - Auto-enriches with Greeks/strike/IV from option chain API
   - Includes actual bid/ask and contract details

2b. **Stream Data Enrichment**: Option Chain API → Cache → Enrich Stream
   - Fetches contract details (Greeks, strike, IV) every 15 minutes
   - Enriches streaming quotes with cached data
   - Backfill utility available for existing data: `scripts/backfill_stream_greeks.py`
   - See `docs/STREAM_ENRICHMENT.md` for details

3. **Backtesting**: TimescaleDB → `OptionsBacktestEngine` → Results
   - Loads options + underlying data
   - Executes strategy logic
   - Tracks multi-leg position P&L
   - Outputs trades, equity curve, metrics

### Database Schema

**TimescaleDB** (PostgreSQL + TimescaleDB extension)
```sql
-- Main table: options_bars (hypertable, partitioned by time)
- timestamp (TIMESTAMPTZ, primary key)
- option_ticker (TEXT, primary key)
- underlying_ticker (TEXT) -- 'SPX'
- OHLCV: open, high, low, close, volume, vwap, transactions
- Quotes: bid, ask, bid_size, ask_size
- Contract: strike_price, contract_type (call/put), expiration_date
- Greeks: implied_volatility, delta, gamma, theta, vega, rho
- Metadata: data_source ('massive', 'schwab_realtime', 'schwab_poll')

-- Continuous aggregates: options_bars_5min, _15min, _1hour, _daily
-- Automatic compression after 7 days
```

### Options Strategy Development

**Creating a New Options Strategy**:
1. Inherit from `OptionsStrategy` in `src/quant_vibe/strategies/options_base.py`
2. Implement required methods:
   - `analyze_market()`: Analyze market conditions
   - `should_enter()`: Entry signal logic
   - `construct_spread()`: Build multi-leg position
   - `should_exit()`: Exit signal logic (profit target, stops)
3. Use helper methods from base class:
   - `update_position_value()`: Get current position value from options data
   - `check_profit_target()`: Check if profit target reached
   - `check_trailing_stop()`: Check trailing stop
   - `close_position()`: Close and record trade

**Strategy Pattern**:
```python
from quant_vibe.strategies.options_base import (
    OptionsStrategy, OptionsPosition, OptionLeg, OptionType, SpreadType
)

class MyStrategy(OptionsStrategy):
    def analyze_market(self, underlying_data, options_data, current_time):
        # Return dict with market analysis
        return {'direction': 'bullish', 'signal': True}

    def should_enter(self, underlying_data, options_data, current_time, analysis):
        # Return True to enter position
        return analysis['signal'] and self.active_position is None

    def construct_spread(self, underlying_data, options_data, current_time, analysis):
        # Build multi-leg position
        legs = [
            OptionLeg(contract_symbol=..., quantity=1, ...),  # Buy
            OptionLeg(contract_symbol=..., quantity=-1, ...), # Sell
        ]
        return OptionsPosition(position_id=..., legs=legs, ...)

    def should_exit(self, position, underlying_data, options_data, current_time):
        # Check exit conditions
        if self.check_profit_target(position):
            return True, "Profit target"
        return False, None
```

### 0 DTE (Zero Days to Expiration)

**What is 0 DTE?**
- Options expiring the same day
- SPXW expires at 4:00 PM ET (PM-settled)
- High volatility, wide spreads
- Popular for intraday trading

**Data Availability**:
- ✅ SPXW has daily expirations (Mon-Fri)
- ✅ 0 DTE data IS available from Massive API
- ✅ Backfill script includes 0, 1, 2 DTE data
- ❌ SPX (AM-settled) has minimal 0 DTE data (expires at 9:30 AM)

**Bid/Ask Spreads**:
- Historical data: Estimated based on DTE and price
  - 0 DTE: 1-10% spreads (wider due to volatility)
  - 1 DTE: 0.8-8% spreads
  - 2 DTE: 0.5-5% spreads
- Real-time data: Actual bid/ask from Schwab

### Configuration Files

**Environment Variables** (`.env`):

**Docker** (`docker-compose.yml`):
- TimescaleDB container for options data
- Port 5432 exposed to localhost
- Persistent volume for data storage

### Common Options Patterns

**Loading Options Data for Backtest**:
```python
from quant_vibe.data.timescale_store import TimescaleStore

ts_store = TimescaleStore()

# Get options data
options_data = ts_store.get_options_for_backtest(
    underlying_ticker='SPX',
    start_time=datetime(2025, 12, 1),
    end_time=datetime(2025, 12, 12),
    min_dte=0,  # Include 0 DTE
    max_dte=45,
)

# Get underlying price from options
underlying_data = ts_store.get_underlying_price_from_options(
    underlying_ticker='SPX',
    start_time=datetime(2025, 12, 1),
    end_time=datetime(2025, 12, 12),
)
```

**Running Options Backtest**:
```python
from quant_vibe.backtesting.options_engine import OptionsBacktestEngine
from quant_vibe.strategies.bullish_vertical_call import BullishVerticalCallStrategy

strategy = BullishVerticalCallStrategy(
    spread_width=20.0,
    min_dte=0,
    max_dte=45,
)

engine = OptionsBacktestEngine(initial_capital=100000.0)

results = engine.run(
    strategy=strategy,
    underlying_data=underlying_data,
    options_data=options_data,
)

# Results include: trades, equity_curve, metrics (Sharpe, drawdown, win rate)
```

**Real-Time Collection**:
```python
from quant_vibe.data.realtime_collector import RealtimeOptionsCollector

collector = RealtimeOptionsCollector(
    max_dte=45,
    min_dte=0,
    strike_range_pct=0.10,  # ±10% from ATM
)

await collector.start_streaming()  # Websocket

# Or use polling (simpler)
# python scripts/poll_spxw_quotes.py
```

### Documentation

- `docs/TIMESCALE_SETUP.md`: Database setup and schema
- `docs/SPXW_FIX.md`: Options data collection troubleshooting
- `QUICKREF_SPXW.md`: Quick reference for SPXW data
- Always use `source venv/bin/activate` before executing a python command
- auth for local UI development - admin:changeme
- Schwab API uses `$SPX` as the underlying symbol for SPXW contracts
- don't assume localhost for the timescaleDB and redis.  check the flags in .env