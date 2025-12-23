# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package in editable mode with all dependencies
pip install -e ".[dev,backtest,indicators]"
```

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
black src tests examples

# Check linting with Ruff
ruff check src tests examples

# Fix auto-fixable linting issues
ruff check --fix src tests examples

# Run type checking with mypy
mypy src
```

### Running Examples
```bash
# Fetch market data (requires API keys in .env)
python examples/fetch_market_data.py

# Calculate technical indicators
python examples/calculate_indicators.py

# Run a simple backtest
python examples/simple_backtest.py
```

## Architecture Overview

### Core Module Structure

The codebase follows a layered architecture:

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

### Adding New Components

**New Strategy**:
1. Create file in `src/quant_vibe/strategies/`
2. Inherit from `Strategy` base class
3. Implement `generate_signals(data: pd.DataFrame) -> pd.Series`
4. Add to `__init__.py` exports
5. Add tests in `tests/unit/test_strategies.py`

**New Indicator**:
1. Add function to `src/quant_vibe/indicators/technical.py`
2. Follow signature: `calculate_X(data: pd.Series, ...) -> pd.Series`
3. Export from `indicators/__init__.py`
4. Add tests in `tests/unit/test_indicators.py`

**New Data Provider**:
1. Add provider logic to `MarketDataClient._load_credentials()` and `fetch_daily_data()`
2. Implement private method like `_fetch_provider_name_daily()`
3. Add required env vars to `.env.example`

**New Backtest Script**:
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
- `SchwabPyClient`: Real-time quotes and OAuth2 authentication
- `RealtimeOptionsCollector`: Websocket streaming for live options data
- Database schema: `scripts/init_timescale.sql`

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
```bash
# Massive API (historical data)
MASSIVE_API_KEY=your_massive_api_key

# Schwab API (real-time data)
SCHWAB_API_KEY=your_schwab_api_key
SCHWAB_API_SECRET=your_schwab_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
SCHWAB_TOKEN_PATH=./tokens/schwab_token.json
SCHWAB_ACCOUNT_NUMBER=your_account_number

# TimescaleDB
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_DB=options_data
TIMESCALE_USER=quantvibe
TIMESCALE_PASSWORD=quantvibe_dev
```

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
- `docs/REALTIME_DATA_COLLECTION.md`: Live data streaming guide
- `QUICKREF_SPXW.md`: Quick reference for SPXW data
- Always use `source venv/bin/activate` before executing a python command