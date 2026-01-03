# Slippage Analysis Guide

## Overview

The slippage analysis system tracks the difference between expected fills (from backtests) and actual fills (from paper trading or live trading). This helps validate and improve backtest accuracy.

## How It Works

### 1. Data Collection

When the `OrderManager` fills an order (simulated or live), it tracks:

- **Expected Price**: The price calculated from current bid/ask quotes
- **Filled Price**: The actual fill price (including simulated slippage in paper trading)
- **Slippage**: The difference between filled and expected prices

This data is automatically logged and persisted to the `live_orders` table in TimescaleDB.

### 2. Slippage Model

The current slippage model (in `order_manager.py:_get_slippage_model()`) uses:

**By DTE:**
- 0 DTE: 3% base slippage (10% for options <$0.50)
- 1 DTE: 2% base slippage (8% for options <$0.50)
- 2-7 DTE: 1.5% base slippage
- 7+ DTE: 1% base slippage

This model can be refined using actual paper trading data.

## Usage

### Analyze All Filled Orders

```bash
python scripts/analyze_slippage.py
```

Output includes:
- Overall statistics (mean, std dev, min/max slippage)
- Breakdown by time of day
- Breakdown by DTE (days to expiration)
- Breakdown by spread width
- Breakdown by strategy

### Analyze Specific Date Range

```bash
python scripts/analyze_slippage.py --start 2025-12-01 --end 2025-12-31
```

### Analyze Specific Strategy

```bash
python scripts/analyze_slippage.py --strategy bullish_vertical_put
```

### Get Backtest Recommendations

```bash
python scripts/analyze_slippage.py --recommendations
```

This analyzes actual paper trading fills and recommends slippage parameters for backtests:

```
RECOMMENDED SLIPPAGE ADJUSTMENTS FOR BACKTEST ENGINE
======================================================================

0 DTE:
  Mean Slippage: 3.45%
  Std Dev: 1.20%
  Sample Size: 25 orders
  Confidence: high

1 DTE:
  Mean Slippage: 2.15%
  Std Dev: 0.85%
  Sample Size: 30 orders
  Confidence: high
```

### Export to JSON

```bash
python scripts/analyze_slippage.py --output slippage_report.json
python scripts/analyze_slippage.py --recommendations --output recommended_params.json
```

### Database Selection

```bash
# Use remote TimescaleDB
python scripts/analyze_slippage.py --db-profile remote

# Use local TimescaleDB
python scripts/analyze_slippage.py --db-profile local

# Auto-detect from USE_REMOTE_TIMESCALE env var (default)
python scripts/analyze_slippage.py
```

## Interpreting Results

### Slippage Metrics

**Dollars ($):**
- Positive = Paid more than expected (unfavorable)
- Negative = Paid less than expected (favorable)

**Percentage (%):**
- Calculated as: `(filled_price - expected_price) / abs(expected_price) * 100`
- Shows relative impact regardless of spread cost

### Key Breakdowns

**By Time of Day:**
- Identifies if slippage is worse at market open/close
- Helps optimize entry timing

**By DTE:**
- Validates the slippage model assumptions
- 0 DTE should have highest slippage (wide spreads, high volatility)

**By Spread Width:**
- Wider spreads may have different slippage characteristics
- Helps validate spread selection

**By Strategy:**
- Compares slippage across different strategies
- Some strategies may have more favorable execution

## Updating Backtest Engine

Once you have sufficient paper trading data (recommended: 50+ filled orders), use the recommendations to update the backtest engine:

### 1. Get Recommendations

```bash
python scripts/analyze_slippage.py --recommendations --output recommended_params.json
```

### 2. Review Parameters

Check `recommended_params.json` and verify:
- Sample sizes are sufficient (>10 orders per DTE bucket preferred)
- Values are reasonable (0.5% - 10% range)
- Confidence levels are "high"

### 3. Update Slippage Model

Edit `src/live_trading_service/order_manager.py`:

```python
def _get_slippage_model(self, dte: int, price: float) -> float:
    """
    Get slippage percentage based on DTE and price.

    Updated from paper trading analysis on YYYY-MM-DD.
    """
    # Use measured values from paper trading
    if dte == 0:
        base_slippage = 0.0345  # 3.45% (measured from 25 orders)
        if price < 0.50:
            base_slippage = 0.10  # Still use 10% for cheap options
    elif dte == 1:
        base_slippage = 0.0215  # 2.15% (measured from 30 orders)
        if price < 0.50:
            base_slippage = 0.08
    # ... etc
```

### 4. Re-run Backtests

After updating slippage parameters, re-run backtests to see impact on performance metrics:

```bash
python scripts/run_backtest.py --strategy bullish_vertical_put
```

Compare new results to original backtest to assess realism.

## Success Criteria

The TODO item is complete when:

✅ SlippageAnalyzer class is implemented
✅ Analysis script works and generates reports
✅ Paper trading accumulates 50+ filled orders
✅ Recommended slippage parameters are within 10% of actual
✅ Backtest engine updated with measured parameters

## Next Steps

1. **Run paper trading for 1-2 weeks** to accumulate filled orders
2. **Analyze slippage weekly** to track consistency
3. **Update backtest parameters** once sufficient data collected
4. **Re-validate backtests** with realistic slippage assumptions
5. **Monitor ongoing** to detect if slippage characteristics change

## Troubleshooting

### No filled orders found

- Ensure paper trading is running: `docker-compose logs live_trading`
- Check if orders are actually being filled (market may be closed)
- Verify database connection is correct

### NaN values in report

- This means expected_price or filled_price is NULL in database
- Check OrderManager is persisting values correctly
- Verify slippage calculation in `_simulate_fill()`

### Unrealistic slippage values

- Check if slippage model is too aggressive/conservative
- Verify options quotes are realistic (not stale data)
- Consider if market conditions were abnormal

## Related Files

- `src/quant_vibe/analytics/slippage_analyzer.py` - Analysis class
- `src/live_trading_service/order_manager.py` - Order execution and slippage model
- `src/live_trading_service/state_store.py` - Database persistence
- `scripts/analyze_slippage.py` - Analysis script
- `config/live_trading.yaml` - Trading configuration

## References

- Slippage in options trading: https://www.investopedia.com/terms/s/slippage.asp
- 0 DTE options characteristics: Wide spreads, high volatility
- Backtesting best practices: Use realistic execution assumptions
