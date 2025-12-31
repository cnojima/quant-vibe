# Bearish IV Scalp - Known Issues & Solutions

## Issue: Backtests Complete with 0 Trades

### Problem
When running backtests for the Bearish IV Scalp strategy, the backtest completes successfully but shows **0 trades executed**.

### Root Cause
The strategy requires **Implied Volatility (IV) data** to detect IV spikes, but the historical options data from Massive API **does not include IV values**. All `implied_volatility` column values are NULL.

### Evidence
```
Sample 0DTE Options Data (Dec 2, 2025):
Total rows: 26298
IV Data Availability: 0/26298 (0.0%)
❌ NO IMPLIED VOLATILITY DATA AVAILABLE!
```

### Why Backtests Don't Fail
The strategy gracefully handles missing IV data:
1. IV calculation returns empty metrics when no IV data is found
2. `iv_spike` is set to `False`
3. Entry conditions are never met
4. Backtest completes successfully with 0 trades

### Solutions

#### Solution 1: Use for Live Trading Only (Recommended)
The strategy works perfectly with real-time data where IV is available:
- Real-time schwabdev streaming includes IV
- Stream enrichment backfills IV from option chain API
- Live trading will have IV spike detection working

**Action**: Enable this strategy only in `config/live_trading.yaml`, not backtests

#### Solution 2: Disable in Backtest Config
If you don't plan to backtest this strategy, disable it:

```yaml
# config/backtest.yaml
strategies:
  enabled:
    - name: bearish_iv_scalp
      enabled: false  # Disable for backtesting
```

#### Solution 3: Calculate Historical IV (Advanced)
Calculate IV for historical data using Black-Scholes model:

**Requirements**:
- Risk-free rate data
- Dividend yield for SPX
- Time to expiration
- Underlying price
- Option prices (bid/ask)

**Implementation** (future enhancement):
```python
from scipy.stats import norm
import numpy as np

def calculate_iv_black_scholes(option_price, S, K, T, r, option_type='call'):
    """Calculate implied volatility using Black-Scholes."""
    # Newton-Raphson method to solve for sigma
    # ... implementation
    pass
```

This would be added to the backfill process to enrich historical data with calculated IV.

#### Solution 4: Modify Strategy to Use Alternative Signal
Replace IV spike detection with price-based volatility:

**Current**: IV spike = `current_iv > threshold AND iv_increase > 10%`

**Alternative**: Use realized volatility from price action:
- Calculate rolling standard deviation of returns
- Detect volatility spikes in price movement
- Use as proxy for IV spikes

**Example**:
```python
def calculate_price_volatility(underlying_data, lookback=30):
    """Calculate realized volatility from price data."""
    returns = underlying_data['close'].pct_change()
    volatility = returns.rolling(window=lookback).std() * np.sqrt(252)
    return volatility

def detect_volatility_spike(volatility, threshold=0.15, spike_pct=0.10):
    """Detect spikes in realized volatility."""
    current = volatility.iloc[-1]
    recent_avg = volatility.iloc[-lookback:].mean()

    if current > threshold and (current - recent_avg) / recent_avg > spike_pct:
        return True
    return False
```

## Issue: Large Date Ranges May Time Out

### Problem
3-month and 12-month backtests may appear to "fail" or hang.

### Root Cause
- Large datasets (hundreds of thousands of option bars)
- Iterating through every timestamp checking IV
- No early termination when IV data is missing

### Solution
Add early detection of missing IV data:

```python
# In analyze_market() method
if not self._iv_data_available:
    # Skip IV spike detection entirely
    return analysis

def _check_iv_availability(self, options_data):
    """Check if IV data is available (run once at start)."""
    iv_available = options_data['implied_volatility'].notna().sum()
    if iv_available == 0:
        print("⚠️  WARNING: No IV data available - strategy will not generate trades")
        self._iv_data_available = False
        return False
    self._iv_data_available = True
    return True
```

## Verification Steps

### Test 1: Check IV Data Availability
```bash
PYTHONPATH=src python -c "
from quant_vibe.data.timescale_store import TimescaleStore
from datetime import datetime

ts_store = TimescaleStore()
options_data = ts_store.get_options_for_backtest(
    underlying_ticker='SPX',
    start_time=datetime(2025, 12, 1),
    end_time=datetime(2025, 12, 31),
    min_dte=0,
    max_dte=0,
)

iv_count = options_data['implied_volatility'].notna().sum()
total = len(options_data)
print(f'IV Data: {iv_count}/{total} ({iv_count/total*100:.1f}%)')
"
```

**Expected**: 0% for historical data, >90% for enriched streaming data

### Test 2: Run Short Backtest
```bash
python scripts/run_backtest.py --strategy bearish_iv_scalp --start-date 2025-12-01 --end-date 2025-12-05
```

**Expected**:
- ✅ Completes successfully
- ✅ 0 trades (due to missing IV)
- ✅ No errors or crashes

### Test 3: Check Real-Time IV Availability
```bash
# Query recent streaming data
SELECT
    COUNT(*) as total,
    COUNT(implied_volatility) as with_iv,
    COUNT(implied_volatility) * 100.0 / COUNT(*) as iv_pct
FROM options_bars
WHERE data_source = 'schwab_realtime'
  AND timestamp >= NOW() - INTERVAL '1 day';
```

**Expected**: >90% IV availability for real-time data

## Workaround Summary

**For Backtesting**:
- Expect 0 trades (this is normal without IV data)
- Use other strategies (bullish_vertical_put, bullish_vertical_call)

**For Live Trading**:
- Strategy will work correctly with real-time IV data
- Ensure streaming service is running with enrichment enabled

## Future Enhancements

1. **IV Calculation Module**: Add Black-Scholes IV calculation for historical data
2. **Hybrid Signal**: Combine price volatility + IV (when available)
3. **Early IV Check**: Detect missing IV at start, skip processing
4. **Alternative Strategy**: Create `bearish_momentum_scalp` that uses price action only
