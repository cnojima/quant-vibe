# Quant-Vibe

A Python-based quantitative trading platform for backtesting trading strategies, live options trading, and real-time market data streaming.

## Features

- **Market Data Integration**: Fetch historical and real-time market data from multiple providers (Alpha Vantage, Polygon, Massive, Schwab)
- **Options Trading**: Full support for SPXW options with 1-minute bars, Greeks, and bid/ask data
- **Real-Time Streaming**: Redis pub/sub architecture for low-latency data distribution
- **Technical Indicators**: Calculate common technical indicators (SMA, EMA, RSI, MACD, and more)
- **Trading Strategies**: Implement and test custom trading strategies with a clean, extensible API
- **Config-Driven Backtesting**: Run backtests via YAML configuration files
- **Config-Driven Live Trading**: Paper and live trading via YAML configuration
- **TimescaleDB Integration**: High-performance time-series database for options data
- **Performance Analytics**: Comprehensive performance metrics including Sharpe ratio, max drawdown, and win rate
- **Microservices Architecture**: Decoupled services communicating via Redis for scalability

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

Quant-Vibe uses a **microservices architecture** with Redis pub/sub for real-time communication:

```
┌─────────────────────────────────────────────────────────────┐
│  StreamingService (Schwab API → Redis → TimescaleDB)        │
│  - Single Schwab websocket connection                       │
│  - Publishes bars to Redis topics                           │
│  - Persists data to TimescaleDB                             │
└─────────────────────────────────────────────────────────────┘
                           ↓ Redis Pub/Sub
┌─────────────────────────────────────────────────────────────┐
│  LiveTradingService(s) (Redis → Strategies → Orders)        │
│  - Subscribes to Redis for market data                      │
│  - Executes trading strategies                              │
│  - Multiple instances supported                             │
└─────────────────────────────────────────────────────────────┘
```

**Benefits:**
- ✅ Single Schwab API connection (no duplicate websockets)
- ✅ Lower API rate limits and faster startup
- ✅ Scalable: Run multiple trading instances from one data feed
- ✅ Retry resilience: Exponential backoff prevents API flooding

## Quick Start

### Fetch Market Data

```python
from quant_vibe.data import MarketDataClient, DataStore

client = MarketDataClient(provider="alpha_vantage")
data = client.fetch_daily_data("AAPL")

store = DataStore()
store.save("AAPL", data)
```

### Run a Backtest

**Recommended: Config-Driven Approach**

1. Configure your backtest in `config/backtest.yaml`:
```yaml
strategies:
  enabled:
    - name: bullish_vertical_put
      enabled: true
      params:
        spread_width: 10.0
        profit_target_min: 0.5
```

2. Run the backtest:
```bash
# Run all enabled strategies
python scripts/run_backtest.py

# Run specific strategy
python scripts/run_backtest.py --strategy bullish_vertical_put
```

**Alternative: Programmatic Approach**

```python
from backtest import BacktestOrchestrator

orchestrator = BacktestOrchestrator('config/backtest.yaml')
results = orchestrator.run()
```

### Real-Time Data Streaming

Start the streaming service to collect live market data:

```bash
# Option 1: Run locally
python scripts/stream_spxw_schwabdev.py

# Option 2: Run in Docker
docker compose up streaming
```

This service:
- Subscribes to Schwab API websocket (1 connection)
- Aggregates quotes into 1-minute bars
- Publishes to Redis topics (`streaming.options_bars`, `streaming.underlying_bars`)
- Persists to TimescaleDB for historical analysis

### Run Live Trading

1. Ensure StreamingService is running (publishes data to Redis)
2. Configure strategies in `config/live_trading.yaml`:
```yaml
engine:
  use_redis_feed: true  # Subscribe to Redis (recommended)
  paper_trading: true   # ALWAYS start with paper trading

strategies:
  enabled:
    - name: bullish_vertical_put
      enabled: true
      params:
        spread_width: 10.0
```

3. Run the live trading engine:
```bash
python scripts/run_live_trading.py
```

**Safety Notes**:
- ✅ Starts in **paper trading mode** by default (simulated orders)
- ✅ Uses Redis feed by default (no duplicate API connections)
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

## Project Structure

```
quant-vibe/
├── src/
│   ├── backtest/              # Top-level backtesting orchestrator (peer)
│   ├── streaming_service/     # Real-time data streaming (peer)
│   │   ├── service.py         # StreamingService (Schwab → Redis → DB)
│   │   ├── aggregator.py      # Bar aggregation logic
│   │   └── config.py          # Streaming configuration
│   ├── live_trading_service/  # Live trading engine (peer)
│   │   ├── engine.py          # LiveTradingEngine (Redis → Strategies)
│   │   ├── redis_data_feed.py # Redis subscriber
│   │   ├── order_manager.py   # Order execution
│   │   └── position_manager.py # Position tracking
│   └── quant_vibe/            # Core library (peer)
│       ├── messaging/         # Redis pub/sub messaging
│       │   ├── broker.py      # Message broker abstraction
│       │   └── topics.py      # Topic definitions
│       ├── backtesting/       # Core backtesting framework
│       ├── data/              # Market data fetching and storage
│       ├── indicators/        # Technical indicator calculations
│       ├── strategies/        # Trading strategy implementations
│       └── utils/             # Utility functions (retry, etc.)
├── config/
│   ├── backtest.yaml          # Backtest configuration
│   └── live_trading.yaml      # Live trading configuration
├── scripts/
│   ├── run_backtest.py        # Backtest CLI entry point
│   ├── run_live_trading.py    # Live trading CLI entry point
│   ├── stream_spxw_schwabdev.py # Streaming service CLI
│   └── test_redis_messaging.py  # Test Redis pub/sub
├── docker-compose.yml         # Redis + TimescaleDB services
├── tests/
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
└── reports/                   # Output directory for results
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_indicators.py
```

### Code Quality

```bash
# Format code
black src tests examples

# Lint code
ruff check src tests examples

# Type checking
mypy src
```

## License

MIT
