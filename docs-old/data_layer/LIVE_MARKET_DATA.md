# LiveMarketDataProvider - Data Access Layer for Live Trading

## Overview

The `LiveMarketDataProvider` is a data access layer that sits between the streaming data feed and the live trading engine. It provides a clean, structured interface for accessing market data in the format expected by trading strategies.

## Architecture

```
┌────────────────────────────────────────────────────┐
│         StrategyExecutor (Live Engine)             │
│                                                    │
│  Needs:                                            │
│  - underlying_data (DataFrame with OHLCV)          │
│  - options_data (DataFrame with full options chain)│
└──────────────────┬─────────────────────────────────┘
                   │
                   │ get_underlying_history()
                   │ get_current_options_snapshot()
                   │
         ┌─────────▼──────────┐
         │                    │
         │ LiveMarketData     │
         │    Provider        │
         │                    │
         │ (Data adapter)     │
         └─────────┬──────────┘
                   │
                   │ Access bars, prices, metadata
                   │
         ┌─────────▼──────────┐
         │                    │
         │  RealtimeDataFeed  │
         │                    │
         │ (Streaming data)   │
         └────────────────────┘
                   ▲
                   │
                   │ handle_message()
                   │
         ┌─────────┴──────────┐
         │                    │
         │  Schwab Stream     │
         │  (schwabdev)       │
         └────────────────────┘
```

## Why This Exists

### Problem

The live trading engine (`StrategyExecutor`) expects data in a specific format:

```python
def on_bar(
    self,
    underlying_data: pd.DataFrame,  # Historical bars (OHLCV)
    options_data: pd.DataFrame,      # Current options chain
    current_time: datetime,
):
    # Strategy execution logic
    ...
```

However, the `RealtimeDataFeed` stores streaming data in a different format:
- Internal data structures (deques, dicts)
- Not directly in DataFrame format
- Optimized for streaming updates, not strategy queries

### Solution

The `LiveMarketDataProvider` acts as an **adapter pattern** that:
1. Wraps the `RealtimeDataFeed`
2. Provides structured access methods
3. Converts internal data to DataFrames
4. Maintains compatibility with backtesting format

This separation of concerns means:
- `RealtimeDataFeed` focuses on efficiently consuming streaming data
- `LiveMarketDataProvider` focuses on providing data to strategies
- Live trading strategies use the same interface as backtesting

## Key Methods

### `get_underlying_history(ticker, lookback_bars)`

Returns historical bars for the underlying asset (e.g., SPX).

**Returns:** DataFrame with columns:
```python
{
    'timestamp': datetime,      # Bar timestamp
    'open': float,              # Open price
    'high': float,              # High price
    'low': float,               # Low price
    'close': float,             # Close price
    'volume': int,              # Trading volume
    'vwap': float,              # Volume-weighted average price
}
```

**Data Sources (in order of preference):**
1. **Direct price tracking**: If `RealtimeDataFeed` has `underlying_prices['SPX']`
2. **Options underlying_price field**: Extract from options bars
3. **Derived from ATM options**: Estimate from at-the-money option prices

**Example:**
```python
# Get last 100 bars of SPX
underlying = provider.get_underlying_history("SPX", lookback_bars=100)

# Calculate indicators
rsi = calculate_rsi(underlying['close'], period=14)
```

### `get_current_options_snapshot(underlying_ticker)`

Returns the current snapshot of all options contracts.

**Returns:** DataFrame with columns:
```python
{
    # Identification
    'timestamp': datetime,
    'contract_symbol': str,           # e.g., SPXW251226C06875000
    'underlying_ticker': str,         # SPX

    # Contract details
    'strike_price': float,            # 6875.0
    'option_type': str,               # 'C' or 'P'
    'expiration_date': date,          # 2025-12-26

    # OHLCV
    'open': float,
    'high': float,
    'low': float,
    'close': float,
    'volume': int,
    'vwap': float,

    # Bid/Ask
    'bid': float,
    'ask': float,
    'mark': float,                    # (bid + ask) / 2
    'bid_size': int,
    'ask_size': int,

    # Greeks
    'delta': float,
    'gamma': float,
    'theta': float,
    'vega': float,
    'rho': float,
    'implied_volatility': float,

    # Metadata
    'transactions': int,              # Number of quotes in bar
}
```

**Behavior:**
- Returns the **most recent bar** for each contract symbol
- Filters by underlying ticker (e.g., only SPX options)
- Empty DataFrame if no data available (with correct column structure)

**Example:**
```python
# Get all active SPXW contracts
options = provider.get_current_options_snapshot("SPX")

# Filter for 0 DTE calls
today = datetime.now().date()
dte_0_calls = options[
    (options['expiration_date'] == today) &
    (options['option_type'] == 'C')
]

# Find ATM strike
atm_strike = underlying_price // 25 * 25  # Round to nearest $25
atm_option = dte_0_calls[
    dte_0_calls['strike_price'] == atm_strike
].iloc[0]
```

## Usage in Live Trading Engine

### Initialization

The engine creates the provider during startup:

```python
# In LiveTradingEngine.initialize()
self.data_feed = RealtimeDataFeed(
    window_size=100,
    aggregate_interval_seconds=60,
    callbacks=[self._on_new_bars]
)

self.market_data = LiveMarketDataProvider(self.data_feed)
```

### On Each New Bar

When new bars arrive, the engine uses the provider:

```python
def _on_new_bars(self, new_bars: List[Dict]):
    for bar in new_bars:
        current_time = bar['timestamp']

        # Get data using provider
        underlying_data = self.market_data.get_underlying_history(
            ticker="SPX",
            lookback_bars=100
        )

        options_data = self.market_data.get_current_options_snapshot(
            underlying_ticker="SPX"
        )

        # Execute strategy
        self.strategy_executor.on_bar(
            underlying_data=underlying_data,
            options_data=options_data,
            current_time=current_time,
        )
```

## Design Patterns

### 1. Adapter Pattern

The provider **adapts** the streaming data feed interface to the strategy executor interface.

```
RealtimeDataFeed                LiveMarketDataProvider
(streaming format)              (strategy format)
     │                                  │
     │  .bars (dict of deques)          │  .get_underlying_history()
     │  .underlying_prices (dict)       │  → Returns DataFrame
     │  .last_update_time               │
     │                                  │
     └──────────────────────────────────┘
              WrappedBy
```

### 2. Separation of Concerns

- **RealtimeDataFeed**: Streaming data consumption and aggregation
- **LiveMarketDataProvider**: Data formatting and access
- **StrategyExecutor**: Business logic (entry/exit signals)

Each component has a single responsibility.

### 3. Consistency with Backtesting

Live strategies receive data in the **exact same format** as backtesting:

```python
# Backtesting (from TimescaleDB)
underlying_data = ts_store.get_underlying_price_from_options(...)
options_data = ts_store.get_options_for_backtest(...)

# Live trading (from stream)
underlying_data = market_data.get_underlying_history(...)
options_data = market_data.get_current_options_snapshot()

# Same columns, same types, same usage!
```

This means:
- Strategies don't need to know if they're in backtest or live mode
- No code changes needed to go from backtest → live
- Testing is more accurate

## Implementation Details

### Empty DataFrame Handling

When no data is available, methods return **empty DataFrames with correct columns**:

```python
if not bars:
    return pd.DataFrame(columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume', 'vwap'
    ])
```

This prevents `KeyError` exceptions when strategies access columns.

### Timestamp Conversion

All timestamps are converted to pandas datetime:

```python
if not pd.api.types.is_datetime64_any_dtype(df['timestamp']):
    df['timestamp'] = pd.to_datetime(df['timestamp'])
```

### Latest Bar Selection

For snapshots, only the **latest bar** per contract is returned:

```python
# Group by contract and take last bar
snapshot = all_bars.groupby('contract_symbol', as_index=False).last()
```

### Underlying Price Derivation

When direct underlying price isn't available, it's derived from options:

```python
# Fallback 1: Extract from options 'underlying_price' field
if 'underlying_price' in options_df.columns:
    underlying_bars = options_df.groupby('timestamp').agg({
        'underlying_price': ['first', 'max', 'min', 'last', 'median']
    })

# Fallback 2: Estimate from ATM option prices
# (less accurate, but better than nothing)
```

## Testing

The provider includes comprehensive tests in `tests/unit/data/test_live_market_data.py`:

- ✅ Initialization
- ✅ Get underlying history (with price)
- ✅ Get underlying history (with lookback)
- ✅ Get options snapshot
- ✅ Empty data handling
- ✅ Timestamp conversion
- ✅ Latest bar selection per contract

Run tests:
```bash
pytest tests/unit/data/test_live_market_data.py -v
```

## Key Benefits

1. **Decoupling**: Streaming logic separated from data access logic
2. **Testability**: Can mock `RealtimeDataFeed` for testing
3. **Consistency**: Same interface as backtesting data access
4. **Maintainability**: Changes to streaming don't affect strategies
5. **Type Safety**: Clear interfaces with DataFrame return types
6. **Error Handling**: Returns empty DataFrames instead of raising exceptions

## Related Files

- **Implementation**: `src/quant_vibe/data/live_market_data.py`
- **Tests**: `tests/unit/data/test_live_market_data.py`
- **Usage**: `src/quant_vibe/live/engine.py` (lines 175-178, 417-423)
- **Data Source**: `src/quant_vibe/live/data_feed.py`

## Related Documentation

- [LIVE_TRADING.md](LIVE_TRADING.md) - Complete live trading architecture
- [STREAM_ENRICHMENT.md](STREAM_ENRICHMENT.md) - How streaming data is enriched
- [QUICKREF_SPXW.md](QUICKREF_SPXW.md) - SPXW contract details

This data access layer is a critical piece of the live trading system, ensuring clean separation of concerns and consistency between backtesting and live execution.
