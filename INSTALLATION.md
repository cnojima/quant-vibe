# Installation Guide

## Fixed: Python 3.14 Compatibility

The package has been refactored to work with Python 3.14+ and avoid toolchain incompatibilities.

### What Was Fixed

1. **Build Backend**: Changed from `setuptools.build_backend` to `setuptools.build_meta` (Python 3.14 compatible)
2. **Modular Dependencies**: Split dependencies into core and optional groups to avoid conflicts

### Installation Options

#### Core Package (Recommended for Options Trading)

Includes:
- Massive API client (options data)
- TimescaleDB support (high-frequency data storage)
- PostgreSQL connectivity (psycopg2)
- Basic data utilities (numpy, pandas, requests)

```bash
pip install -e .
```

#### Optional Features

Install additional features as needed:

```bash
# Backtesting support
pip install -e ".[backtest]"
# Adds: backtrader, matplotlib

# Technical indicators
pip install -e ".[indicators]"
# Adds: pandas-ta (ta-lib removed due to compilation issues)

# Schwab API integration
pip install -e ".[schwab]"
# Adds: schwab-py

# Stock data fetching
pip install -e ".[stockdata]"
# Adds: yfinance

# Development tools
pip install -e ".[dev]"
# Adds: pytest, black, ruff, mypy

# Everything
pip install -e ".[all,dev]"
```

### Removed/Moved Dependencies

The following were moved from core dependencies due to Python 3.14 compatibility or modularity:

- `backtrader` - Moved to optional `[backtest]` group ✅
- `matplotlib` - Moved to optional `[backtest]` group ✅
- `schwab-py` - Moved to optional `[schwab]` group ✅
- `yfinance` - Moved to optional `[stockdata]` group ✅

**Removed entirely (Python 3.14 incompatibility):**
- `pandas-ta` - Depends on `numba` which doesn't support Python 3.14 yet ❌
- `ta-lib` - Requires C compilation and has installation issues ❌

**For technical indicators**, use pandas built-in functions or implement manually:
```python
# Simple Moving Average
df['SMA_20'] = df['Close'].rolling(window=20).mean()

# Exponential Moving Average
df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()

# RSI
delta = df['Close'].diff()
gain = delta.where(delta > 0, 0).rolling(window=14).mean()
loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
rs = gain / loss
df['RSI'] = 100 - (100 / (1 + rs))
```

### Verification

After installation, verify it works:

```bash
python -c "from quant_vibe.data import MassiveClient, TimescaleStore; print('✓ Installation successful')"
```

### For TimescaleDB Setup

If using TimescaleDB for high-frequency options data:

```bash
# 1. Install core package
pip install -e .

# 2. Start TimescaleDB
docker-compose up -d

# 3. Verify connection
docker exec -it quant-vibe-timescaledb psql -U quantvibe -d options_data

# 4. Start collecting data
python scripts/collect_options_1min_data.py --ticker SPX
```

See [docs/TIMESCALE_SETUP.md](docs/TIMESCALE_SETUP.md) for detailed TimescaleDB documentation.

### Troubleshooting

#### Build backend error
If you see `Cannot import 'setuptools.build_backend'`, ensure you're using the latest version:
```bash
pip install --upgrade setuptools pip wheel
```

#### Missing dependencies
If you get import errors, install the relevant optional dependency group:
```bash
# Example: If you get "No module named 'backtrader'"
pip install -e ".[backtest]"
```

#### Python version
This package requires Python 3.9+. Check your version:
```bash
python --version
```

## Summary

The package is now **modular and compatible with Python 3.14**. Install only what you need:

- **Core**: Options data collection with Massive + TimescaleDB ✅
- **Backtest**: Add backtesting capabilities (optional)
- **Indicators**: Add technical analysis (optional)
- **Schwab**: Add Schwab API integration (optional)
- **All**: Install everything (optional)

This approach avoids dependency conflicts while maintaining full functionality.
