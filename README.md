# Quant-Vibe

A Python-based quantitative trading platform for backtesting trading strategies, live options trading, and real-time market data streaming with a focus on S&P 500 options (SPXW).

## Features

### Core Framework
- **Peer Component Architecture**: Modular design with four independent components (backtesting, streaming service, live trading, core library)
- **Config-Driven Orchestration**: YAML-based configuration for backtesting and live trading
- **Normalized Logging**: EST timezone-aware logging with automatic rotation and multi-line support
- **Technical Indicators**: Calculate common technical indicators (SMA, EMA, RSI, MACD, and more)
- **Performance Analytics**: Comprehensive performance metrics including Sharpe ratio, max drawdown, win rate, and educational analytics

### Market Data
- **Multi-Provider Integration**: Support for Massive (historical options), Schwab (real-time), Alpha Vantage, and Polygon
- **TimescaleDB Integration**: High-performance time-series database with automatic compression and continuous aggregates
- **Options Data**: Full support for SPXW options with 1-minute bars, Greeks (delta, gamma, theta, vega, rho), and bid/ask data
- **0 DTE Support**: Zero Days to Expiration intraday options trading with daily SPXW expirations (Mon-Fri)

### Real-Time Architecture
- **Redis Pub/Sub Messaging**: Low-latency data distribution between services
- **Single API Connection**: StreamingService maintains one Schwab websocket, shares data via Redis
- **Scalable Design**: Multiple live trading instances can subscribe to same data feed
- **Retry Resilience**: Exponential backoff for API errors prevents flooding

### Trading & Backtesting
- **Multi-Leg Options Strategies**: Support for spreads (vertical, iron condor, etc.) with multiple legs
- **Intraday Trading**: 1-minute bar resolution for precise entry/exit timing
- **Options Backtesting Engine**: Specialized engine handling multi-leg positions, Greeks tracking, bid/ask mark pricing
- **Live Trading Engine**: Paper and live trading with position tracking, risk management, and state persistence
- **Config-Driven**: Run multiple strategies with single command via YAML configuration

### Infrastructure
- **Docker Compose**: Redis, TimescaleDB, and streaming services orchestrated via Docker
- **Dynamic DNS Support**: Automatic DNS updates via Sonic.net DynDNS for remote access
- **Development Tools**: Comprehensive testing, linting, formatting, and type checking

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd quant-vibe
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the package (choose your option):

**Core package only** (for options data collection with TimescaleDB):
```bash
pip install -e .
```

**With optional features**:
```bash
# For backtesting
pip install -e ".[backtest]"

# For Schwab API integration
pip install -e ".[schwab]"

# For stock data (yfinance)
pip install -e ".[stockdata]"

# Everything (all features)
pip install -e ".[all,dev]"
```

**Note on Technical Indicators**: `pandas-ta` and `ta-lib` are not compatible with Python 3.14. Use pandas built-in functions for indicators (see `INSTALLATION.md` for examples).

4. Set up environment variables:
```bash
cp .env.example .env
# Edit .env and add your API keys
```

**Note**: The core package includes Massive API client, Redis messaging, and TimescaleDB support for high-frequency options data. Optional dependencies are modular to avoid toolchain conflicts on newer Python versions.

5. Start infrastructure services:
```bash
# Start Redis and TimescaleDB
docker compose up -d redis timescaledb

# Verify Redis is running
docker exec quant-vibe-redis redis-cli ping
# Should output: PONG
```

## Architecture

Quant-Vibe uses a **peer component architecture** with four independent top-level components:

```
┌────────────────────────────────────────────────────────────┐
│  src/backtest/ (Backtesting Orchestrator)                  │
│  - Config-driven backtesting via YAML                      │
│  - Loads strategies dynamically                            │
│  - Runs OptionsBacktestEngine                              │
│  - Generates reports and saves results                     │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  src/streaming_service/ (Real-Time Data Streaming)         │
│  - Schwab API websocket → Redis → TimescaleDB              │
│  - Single websocket connection (shared via Redis)          │
│  - Aggregates quotes into 1-minute bars                    │
│  - Auto-enrichment with Greeks/strike/IV                   │
└────────────────────────────────────────────────────────────┘
                           ↓ Redis Pub/Sub
┌────────────────────────────────────────────────────────────┐
│  src/live_trading_service/ (Live Trading Engine)           │
│  - Subscribes to Redis for market data                     │
│  - Executes strategies (paper or live trading)             │
│  - Position tracking, risk management                      │
│  - Multiple instances supported                            │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│  src/quant_vibe/ (Core Library)                            │
│  - Reusable components (backtesting, indicators, etc.)     │
│  - Shared by all peer components                           │
│  - Strategy framework, data access, messaging              │
└────────────────────────────────────────────────────────────┘
```

### Benefits

**Separation of Concerns:**
- ✅ Each component has a specific responsibility
- ✅ Top-level orchestrators vs. core framework
- ✅ Clear boundaries between components

**Reusability:**
- ✅ Components import from quant_vibe library
- ✅ Same strategies run in backtest and live trading
- ✅ Shared data access, indicators, and utilities

**Independent Deployment:**
- ✅ Each service can be deployed/scaled separately
- ✅ Single Schwab API connection shared via Redis
- ✅ Multiple live trading instances from one data feed

**Messaging Architecture (Redis Pub/Sub):**
- ✅ Low-latency real-time communication
- ✅ Decoupled services (no direct dependencies)
- ✅ Retry resilience with exponential backoff

## Quick Start

### 1. Collect Historical Options Data

Backfill historical SPXW options data from Massive API:

```bash
# Backfill 0-2 DTE historical data
python scripts/backfill_0dte_spxw.py
```

This populates TimescaleDB with 1-minute OHLCV bars, bid/ask quotes, and estimated Greeks.

### 2. Run a Backtest

**Config-Driven Approach (Recommended):**

1. Configure your backtest in `config/backtest.yaml`:
```yaml
data:
  underlying_ticker: "SPX"
  start_date: "2025-12-01"
  end_date: "2025-12-12"
  min_dte: 0
  max_dte: 45

strategies:
  enabled:
    - name: bullish_vertical_put
      enabled: true
      params:
        spread_width: 10.0
        profit_target_min: 0.5
        stop_loss_pct: 0.50
```

2. Run the backtest:
```bash
# Run all enabled strategies
python scripts/run_backtest.py

# Run specific strategy
python scripts/run_backtest.py --strategy bullish_vertical_put

# Use custom config
python scripts/run_backtest.py --config config/my_backtest.yaml
```

**Programmatic Approach:**

```python
from quant_vibe.backtesting import OptionsBacktestEngine, BacktestReporter
from quant_vibe.strategies.bullish_vertical_put import BullishVerticalPutStrategy
from quant_vibe.utils import load_options_backtest_data
from datetime import datetime

# Load data from TimescaleDB
options_data, underlying_data = load_options_backtest_data(
    underlying_ticker="SPX",
    start_date=datetime(2025, 12, 1),
    end_date=datetime(2025, 12, 12),
    min_dte=0,
    max_dte=45,
)

# Run backtest
strategy = BullishVerticalPutStrategy(spread_width=10.0)
engine = OptionsBacktestEngine(initial_capital=100000.0)
results = engine.run(
    strategy=strategy,
    underlying_data=underlying_data,
    options_data=options_data,
)

# Display results
reporter = BacktestReporter()
reporter.print_trade_details(results["trades"])
reporter.print_educational_metrics(
    results["trades"],
    results["equity_curve"],
    initial_capital=100000.0,
)
```

### 3. Real-Time Data Streaming

Start the streaming service to collect live market data:

```bash
# Option 1: Run locally
python scripts/stream_spxw_schwabdev.py

# Option 2: Run in Docker
docker compose up -d streaming
```

This service:
- ✅ Subscribes to Schwab API websocket (single connection)
- ✅ Aggregates quotes into 1-minute bars
- ✅ Auto-enriches with Greeks/strike/IV from option chain API
- ✅ Publishes to Redis topics (`streaming.options_bars`, `streaming.underlying_bars`)
- ✅ Persists to TimescaleDB for historical analysis

**Stream Data Enrichment:**

The streaming service automatically enriches quote data with contract details (Greeks, strike, IV) from Schwab's option chain API. For existing streaming data missing these fields:

```bash
# Check enrichment status
python scripts/backfill_stream_greeks.py --stats-only

# Preview what would be enriched
python scripts/backfill_stream_greeks.py --dry-run

# Run enrichment backfill
python scripts/backfill_stream_greeks.py
```

See `docs/STREAM_ENRICHMENT.md` for details.

### 4. Run Live Trading

**Prerequisites:**
1. Ensure StreamingService is running (publishes data to Redis)
2. Verify Redis is accessible: `docker exec quant-vibe-redis redis-cli ping`

**Configuration:**

Configure strategies in `config/live_trading.yaml`:
```yaml
engine:
  use_redis_feed: true  # Subscribe to Redis (recommended)
  paper_trading: true   # ALWAYS start with paper trading

redis:
  host: null  # Uses REDIS_HOST env var or 'localhost'
  port: null  # Uses REDIS_PORT env var or 6379
  db: null    # Uses REDIS_DB env var or 0

strategies:
  enabled:
    - name: bullish_vertical_put
      enabled: true
      params:
        spread_width: 10.0
        profit_target_min: 0.5
```

**Run the engine:**
```bash
python scripts/run_live_trading.py

# Or with custom config
python scripts/run_live_trading.py --config config/my_live_config.yaml
```

**Safety Notes:**
- ✅ Starts in **paper trading mode** by default (simulated orders)
- ✅ Uses Redis feed by default (no duplicate API connections)
- ✅ Position tracking, risk management, state persistence included
- ⚠️  Set `paper_trading: false` only after extensive testing
- ⚠️  Monitor closely when switching to live trading

### Test Redis Messaging

Verify the pub/sub system is working:

```bash
python scripts/test_redis_messaging.py
# Expected output:
# ✅ SUCCESS: All messages received!
# ✅ SUCCESS: Correct topics received!
```

### Remote Access with Dynamic DNS

Enable remote access to your services using Sonic.net DynDNS:

1. Get API credentials:
```bash
python scripts/get_sonic_dyndns_apikey.py
```

2. Add credentials to `.env`:
```bash
SONIC_DYNDNS_USERID=your_userid
SONIC_DYNDNS_APIKEY=your_apikey
SONIC_DYNDNS_HOSTNAME=your-hostname.sonic.net
```

3. Start the DynDNS service:
```bash
docker compose up -d dyndns
```

The service will automatically update your DNS records when your IP changes. See [docs/DYNDNS_QUICKSTART.md](docs/DYNDNS_QUICKSTART.md) for details.

## Project Structure

The project follows a **peer component architecture** with six independent top-level services and one shared library:

```
quant-vibe/
├── src/
│   ├── backtest/                      # Backtesting orchestrator (peer service)
│   │   ├── engine.py                  # BacktestOrchestrator (config-driven)
│   │   └── config_loader.py           # Configuration loader and validator
│   │
│   ├── streaming_service/             # Real-time data streaming (peer service)
│   │   ├── service.py                 # StreamingService (Schwab → Redis → DB)
│   │   ├── aggregator.py              # Options bar aggregation logic
│   │   ├── underlying_aggregator.py   # Underlying price aggregation
│   │   ├── enrich_stream_with_chain.py # Auto-enrichment with Greeks/strike/IV
│   │   ├── config.py                  # Streaming configuration
│   │   └── token_manager.py           # Token refresh management
│   │
│   ├── live_trading_service/          # Live trading engine (peer service)
│   │   ├── engine.py                  # LiveTradingEngine (Redis → Strategies → Orders)
│   │   ├── redis_data_feed.py         # Redis subscriber for market data
│   │   ├── data_feed.py               # Direct Schwab data feed (legacy)
│   │   ├── order_manager.py           # Order execution and management
│   │   ├── position_manager.py        # Position tracking and P&L
│   │   ├── strategy_executor.py       # Strategy execution coordinator
│   │   ├── strategy_loader.py         # Dynamic strategy loading
│   │   ├── state_store.py             # Persistent state management
│   │   └── utils.py                   # Trading utilities
│   │
│   ├── token_service/                 # Token refresh service (peer service)
│   │   ├── service.py                 # TokenRefreshService (Redis pub/sub)
│   │   ├── manager.py                 # Token manager with auto-refresh
│   │   ├── client.py                  # Token service client
│   │   └── config.py                  # Token service configuration
│   │
│   ├── watcher_service/               # Service monitoring and alerting (peer service)
│   │   ├── watcher.py                 # Main watcher service
│   │   ├── service_monitor.py         # Service health monitoring
│   │   ├── heartbeat_manager.py       # Heartbeat tracking
│   │   ├── alert_manager.py           # Alert notifications (Pushover)
│   │   └── config.py                  # Watcher configuration
│   │
│   ├── admin_ui/                      # Web-based admin dashboard (peer service)
│   │   ├── backend/
│   │   │   ├── main.py                # FastAPI application
│   │   │   ├── auth.py                # Authentication
│   │   │   ├── api/                   # API endpoints
│   │   │   │   ├── status.py          # Service status
│   │   │   │   ├── services.py        # Service control
│   │   │   │   ├── tokens.py          # Token management
│   │   │   │   ├── backtests.py       # Backtest management
│   │   │   │   └── live.py            # Live trading control
│   │   │   ├── db/                    # Database clients
│   │   │   │   └── timescale.py       # TimescaleDB client
│   │   │   ├── docker/                # Docker management
│   │   │   │   └── manager.py         # Docker API wrapper
│   │   │   └── redis_client.py        # Redis client
│   │   └── frontend/                  # React UI (static files)
│   │
│   └── quant_vibe/                    # Core library (shared by all services)
│       ├── messaging/                 # Redis pub/sub messaging
│       │   ├── broker.py              # RedisMessageBroker
│       │   └── topics.py              # Topic definitions
│       │
│       ├── backtesting/               # Core backtesting framework
│       │   ├── options_engine.py      # OptionsBacktestEngine
│       │   ├── engine.py              # Stock backtesting engine
│       │   ├── reporter.py            # BacktestReporter (educational metrics)
│       │   └── performance.py         # PerformanceMetrics
│       │
│       ├── data/                      # Market data fetching and storage
│       │   ├── timescale_store.py     # TimescaleDB integration
│       │   ├── massive_client.py      # Massive API (historical options)
│       │   ├── schwabdev_client.py    # Schwab API (real-time)
│       │   ├── data_store.py          # Local data storage (parquet/CSV)
│       │   └── market_data_client.py  # Multi-provider data client
│       │
│       ├── indicators/                # Technical indicator calculations
│       │   └── technical.py           # SMA, EMA, RSI, MACD, Bollinger, etc.
│       │
│       ├── strategies/                # Trading strategy implementations
│       │   ├── options_base.py        # OptionsStrategy base class
│       │   ├── bullish_vertical_put.py # Bullish vertical put spread
│       │   ├── sma_crossover_delayed.py # SMA crossover
│       │   ├── rsi_macd_confirmation.py # RSI + MACD combo
│       │   ├── bollinger_bands.py     # Bollinger bands strategy
│       │   └── macd_histogram.py      # MACD histogram strategy
│       │
│       ├── utils/                     # Utility functions
│       │   ├── datetime_utils.py      # EST timezone-aware datetime
│       │   ├── backtest_helpers.py    # Backtest utilities
│       │   ├── retry.py               # Exponential backoff retry
│       │   ├── output.py              # TeeOutput logging
│       │   └── symbol_utils.py        # Symbol parsing and validation
│       │
│       ├── notifications/             # Notification integrations
│       │   └── pushover.py            # Pushover push notifications
│       │
│       ├── services/                  # Shared service utilities
│       │   └── heartbeat.py           # Heartbeat protocol
│       │
│       └── config/                    # Configuration management
│           ├── logging_config.py      # Normalized logging setup
│           └── unified_logging.py     # Unified logging interface
│
├── config/
│   ├── backtest.yaml                  # Backtest configuration
│   ├── live_trading.yaml              # Live trading configuration
│   └── watcher.yaml                   # Watcher service configuration
│
├── scripts/
│   ├── run_backtest.py                # Backtest CLI entry point
│   ├── run_live_trading.py            # Live trading CLI entry point
│   ├── stream_spxw_schwabdev.py       # Streaming service CLI
│   ├── run_token_service.py           # Token service CLI
│   ├── run_watcher.py                 # Watcher service CLI
│   ├── run_admin_ui.py                # Admin UI CLI
│   ├── run_dyndns.py                  # Dynamic DNS updater
│   │
│   ├── backfill/                      # Data backfill utilities
│   │   ├── backfill_0dte_spxw-massive.py # Historical 0 DTE data
│   │   ├── backfill_stream_greeks.py  # Enrich streaming data
│   │   ├── backfill_spx_options.py    # SPX options backfill
│   │   ├── backfill_spx_underlying_1min.py # Underlying price
│   │   ├── backfill_december_gaps.py  # Fill data gaps
│   │   └── backfill_expiration_dates.py # Expiration dates
│   │
│   ├── fix/                           # Data migration and fixes
│   │   ├── normalize_all_contracts.py # Normalize contract symbols
│   │   ├── migrate_normalize_contract_symbols.py # Symbol migration
│   │   └── fix_contract_type_migration.py # Contract type fixes
│   │
│   ├── init_timescale.sql             # Database schema
│   ├── test_redis_messaging.py        # Test Redis pub/sub
│   ├── test_live_trading_redis.py     # Test live trading feed
│   ├── test_heartbeat_flow.py         # Test heartbeat protocol
│   ├── diagnose_heartbeat_issue.py    # Heartbeat diagnostics
│   ├── get_sonic_dyndns_apikey.py     # Get Sonic DynDNS API key
│   └── sync_moirae.py                 # Sync with Moirae server
│
├── tests/
│   ├── unit/                          # Unit tests
│   │   ├── streaming_service/         # Streaming service tests
│   │   ├── test_token_service/        # Token service tests
│   │   ├── data/                      # Data layer tests
│   │   ├── utils/                     # Utility tests
│   │   ├── test_indicators.py         # Indicator tests
│   │   ├── test_strategies.py         # Strategy tests
│   │   └── test_data_store.py         # Data store tests
│   └── integration/                   # Integration tests
│       └── test_backtest_workflow.py  # Full backtest workflow
│
├── docs/                              # Documentation
│   ├── data_layer/                    # Data layer documentation
│   ├── live_trading/                  # Live trading guides
│   ├── logging/                       # Logging documentation
│   ├── dyndns/                        # DynDNS documentation
│   ├── admin_ui/                      # Admin UI documentation
│   ├── token_service/                 # Token service docs
│   ├── testing/                       # Testing guides
│   ├── INSTALLATION.md                # Installation guide
│   ├── DOCKER_GUIDE.md                # Docker setup guide
│   ├── STRATEGIES_GUIDE.md            # Strategy development guide
│   ├── NOTIFICATIONS.md               # Notification setup
│   └── TROUBLESHOOTING.md             # Troubleshooting guide
│
├── docker-compose.yml                 # All services orchestration
├── reports/                           # Backtest output directory
├── logs/                              # Application logs (auto-rotated)
├── CLAUDE.md                          # Claude Code development guide
├── QUICKREF_SPXW.md                   # SPXW quick reference
└── .env                               # Environment configuration (not committed)
```

### Component Descriptions

**Peer Services** (Independent, separately deployable):
- **backtest**: Config-driven backtesting orchestrator
- **streaming_service**: Real-time market data collector and distributor
- **live_trading_service**: Paper and live trading execution engine
- **token_service**: Centralized OAuth token refresh service
- **watcher_service**: Service health monitoring and alerting
- **admin_ui**: Web-based dashboard for monitoring and control

**Shared Library**:
- **quant_vibe**: Core library used by all peer services (backtesting, data access, strategies, indicators, messaging, utilities)

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_indicators.py

# Run tests matching a pattern
pytest -k "test_sma"

# Run only unit or integration tests
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

### Environment Configuration

All services use environment variables from `.env`:

```bash
# Copy example and edit with your credentials
cp .env.example .env
```

**Key environment variables:**
- `MASSIVE_API_KEY` - Massive API for historical options data
- `SCHWAB_API_KEY`, `SCHWAB_API_SECRET` - Schwab API credentials
- `TIMESCALE_*` - Local TimescaleDB connection
- `REMOTE_TIMESCALE_*` - Remote TimescaleDB connection
- `USE_REMOTE_TIMESCALE` - Toggle between local/remote database
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_DB` - Redis configuration

### Adding New Strategies

1. Create strategy file in `src/quant_vibe/strategies/` (inherit from `OptionsStrategy`)
2. Implement required methods: `analyze_market()`, `should_enter()`, `construct_spread()`, `should_exit()`
3. Add to `__init__.py` exports
4. Register in `src/backtest/engine.py` strategy map
5. Add configuration to `config/backtest.yaml` and `config/live_trading.yaml`
6. Add tests in `tests/unit/test_strategies.py`

See `src/quant_vibe/strategies/bullish_vertical_put.py` for reference implementation.

## Key Resources

- **CLAUDE.md** - Comprehensive development guide for Claude Code
- **docs/TIMESCALE_SETUP.md** - Database setup and schema
- **docs/STREAM_ENRICHMENT.md** - Stream data enrichment details
- **docs/LOG_ROTATION.md** - Log rotation and timezone handling
- **QUICKREF_SPXW.md** - Quick reference for SPXW options data

## License

MIT
