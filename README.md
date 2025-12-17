# Quant-Vibe

A Python-based quantitative trading platform for backtesting trading strategies, fetching live market data, and calculating technical indicators.

## Features

- **Market Data Integration**: Fetch historical and real-time market data from multiple providers (Alpha Vantage, Polygon, etc.)
- **Technical Indicators**: Calculate common technical indicators (SMA, EMA, RSI, MACD, and more)
- **Trading Strategies**: Implement and test custom trading strategies with a clean, extensible API
- **Backtesting Engine**: Test strategies against historical data with realistic commission modeling
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

```python
from quant_vibe.strategies import SMACrossoverStrategy
from quant_vibe.backtesting import BacktestEngine, PerformanceMetrics

# Create strategy
strategy = SMACrossoverStrategy(fast_period=50, slow_period=200)

# Run backtest
engine = BacktestEngine(initial_capital=100000.0)
portfolio = engine.run(strategy, data)

# Analyze performance
metrics = PerformanceMetrics.calculate(portfolio)
print(f"Total Return: {metrics['total_return']:.2f}%")
print(f"Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
```

## Project Structure

```
quant-vibe/
├── src/quant_vibe/
│   ├── data/              # Market data fetching and storage
│   ├── indicators/        # Technical indicator calculations
│   ├── strategies/        # Trading strategy implementations
│   ├── backtesting/       # Backtesting engine and performance
│   └── utils/             # Utility functions
├── tests/
│   ├── unit/              # Unit tests
│   └── integration/       # Integration tests
├── examples/              # Example scripts
└── scripts/               # Utility scripts
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
