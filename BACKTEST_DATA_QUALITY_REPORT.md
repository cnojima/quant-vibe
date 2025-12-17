# Backtest Data Quality Investigation Report

## Executive Summary

The bullish vertical put backtest for Nov 1 - Dec 12, 2025 shows **unrealistic profitability (+5,708% on one trade)** due to **critical data quality issues**.

### Root Cause

**Missing options contract data at specific timestamps**, causing incorrect position valuations.

## Detailed Findings

### Trade #4 Analysis (Nov 20, 2025)

**Trade Details:**
- Entry: 14:49 @ SPX 6712.50
- Exit: 17:03 (2 hours 14 minutes later)
- Spread: 6710/6700 bull put spread ($10 wide, 10 contracts)
- Entry credit: $1,500
- **Reported P&L: +$85,620 (+5,708%)** ❌ IMPOSSIBLE

**What Happened:**
1. Strategy sold 6710 put @ $7.50, bought 6700 put @ $6.00
2. SPX dropped $47.50 (to 6665.00) - both puts went deep ITM
3. At exit (17:03):
   - 6700 put data: **PRESENT** - mark $84.12
   - 6710 put data: **MISSING** ❌

**Position Valuation Error:**
```
Correct calculation:
  Short 6710 put: -10 × $88 × 100 = -$88,000 (estimated)
  Long 6700 put:  +10 × $84 × 100 = +$84,000
  Net position value: -$4,000
  P&L: -$4,000 - (-$1,500) = -$2,500 LOSS

Actual (buggy) calculation:
  Short 6710 put: MISSING - counted as $0
  Long 6700 put:  +10 × $84.12 × 100 = +$84,120
  Net position value: $84,120 ❌
  P&L: $84,120 - (-$1,500) = +$85,620 ❌ WRONG!
```

### Data Completeness Analysis

**Nov 20, 2025 (0 DTE)**:
- Total timestamps: 391 (9:30 AM - 4:00 PM ET)
- Available strikes: ~120 contracts per timestamp
- **6710 PUT**: Present at 91/391 timestamps (23% coverage) ❌
- **6700 PUT**: Present at 91/391 timestamps (23% coverage) ❌

**Missing Data Pattern:**
- Strikes with lower volume/open interest are frequently missing
- **6710 strike volume**: 105 contracts (moderate)
- **6700 strike volume**: 1,093 contracts (good liquidity)
- Even well-traded strikes missing from specific minutes

### Data Source

**Source**: Massive API (formerly Polygon)
- Historical 1-minute bars backfilled from July-Dec 2025
- Bid/ask spreads **estimated** (not actual quotes)
- Some contracts missing from certain timestamps

### Impact on Other Trades

Checked all 10 trades:
- **Trade #4**: Catastrophic error (+5,708% instead of likely loss)
- **Trades #1, #2, #3, #8, #9**: Exit at "20:45" (impossible - market closes at 16:00)
  - Display bug or timezone issue
  - Actual data only goes to 16:00 ET
- **Other trades**: 83-100% profit (suspiciously high)
  - Likely have same missing data issue but less severe

## Recommendations

### Short-term Fixes

1. **✅ IMPLEMENTED: Data Interpolation**
   - Interpolate missing strikes from neighboring strikes
   - Fallback to entry price if interpolation fails
   - **Status**: Reduces but doesn't eliminate errors

2. **Implement liquidity filters**:
   ```python
   # Only use strikes with minimum volume
   min_volume = 50
   min_open_interest = 100
   ```

3. **Add data validation checks**:
   - Verify all position legs have data before entry
   - Skip timestamp if critical data missing
   - Log all missing data occurrences

4. **Cap position values**:
   ```python
   # For $10 wide spread with 10 contracts
   max_value = 10 * 10 * 100 = $10,000
   if abs(position_value) > max_value:
       position_value = max_value * sign(position_value)
   ```

### Long-term Solutions

1. **Use live polling data**:
   - `scripts/poll_spxw_quotes.py` collects real Schwab quotes
   - Actual bid/ask, not estimated
   - Better data completeness

2. **Switch to wider spreads**:
   - Use $20-50 wide spreads for better liquidity
   - Reduces likelihood of missing data

3. **Filter by ATM distance**:
   - Only trade strikes within ±3% of ATM
   - Higher liquidity, better data quality

4. **Add data quality metrics**:
   - Track % of timestamps with complete data
   - Reject trades if data completeness < 95%

## Conclusion

**The backtest results are INVALID due to data quality issues.**

- Reported +5,708% gain is actually a LOSS
- Most trades have inflated profits due to missing leg data
- Historical Massive data is insufficient for accurate 0 DTE backtesting

**Action Required:**
1. ✅ Data interpolation implemented (partial fix)
2. ⏳ Add liquidity filters and validation
3. ⏳ Re-run backtest with fixes
4. ⏳ Consider using live-collected Schwab data instead

---

*Generated: Dec 15, 2025*
*Investigation: Trade #4 data quality analysis*
