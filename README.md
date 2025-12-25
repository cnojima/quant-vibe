# Quant-Vibe

A Python-based quantitative trading platform for backtesting trading strategies, fetching live market data, and calculating technical indicators.

## Features

- **Market Data Integration**: Fetch historical and real-time market data from multiple providers (Alpha Vantage, Polygon, Massive, Schwab)
- **Options Trading**: Full support for SPXW options with 1-minute bars, Greeks, and bid/ask data
- **Technical Indicators**: Calculate common technical indicators (SMA, EMA, RSI, MACD, and more)
- **Trading Strategies**: Implement and test custom trading strategies with a clean, extensible API
- **Config-Driven Backtesting**: Run backtests via YAML configuration files with the orchestrator
- **Config-Driven Live Trading**: Paper and live trading via YAML configuration
- **TimescaleDB Integration**: High-performance time-series database for options data
- **Performance Analytics**: Comprehensive performance metrics including Sharpe ratio, max drawdown, and win rate

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

**Note**: The core package includes Massive API client and TimescaleDB support for high-frequency options data. Optional dependencies are modular to avoid toolchain conflicts on newer Python versions.

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

### Run Live Trading

1. Configure strategies in `config/live_trading.yaml`
2. Run the engine:
```bash
python scripts/run_live_trading.py
```

**Note**: Starts in paper trading mode by default for safety.

## Project Structure

```
quant-vibe/
├── src/
│   ├── backtest/          # Top-level backtesting orchestrator (peer)
│   ├── streaming_service/ # Real-time data streaming service (peer)
│   └── quant_vibe/        # Core library (peer)
│       ├── live/          # Live trading engine
│       ├── backtesting/   # Core backtesting framework (reusable)
│       ├── data/          # Market data fetching and storage
│       ├── indicators/    # Technical indicator calculations
│       ├── strategies/    # Trading strategy implementations
│       └── utils/         # Utility functions
├── config/
│   ├── backtest.yaml      # Backtest configuration
│   └── live_trading.yaml  # Live trading configuration
├── scripts/
│   ├── run_backtest.py    # Backtest CLI entry point
│   └── run_live_trading.py # Live trading CLI entry point
├── tests/
│   ├── unit/              # Unit tests
│   └── integration/       # Integration tests
└── reports/               # Output directory for results
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
