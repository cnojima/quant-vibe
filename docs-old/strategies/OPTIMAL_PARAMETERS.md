# Optimal Strategy Parameters

This document tracks optimal parameters for each trading strategy, derived from systematic optimization and walk-forward analysis.

**Last Updated**: 2025-12-31

---

## Optimization Process

All parameters are optimized using:

1. **Grid Search**: Test all combinations of parameters on training data
2. **Walk-Forward Analysis**: Validate robustness on out-of-sample data
3. **Robustness Checks**:
   - Sharpe degradation <50%
   - Return degradation <50%
   - Out-of-sample Sharpe >1.0
   - Out-of-sample win rate >55%

**Training Period**: September 2025 - November 2025
**Test Period**: December 2025
**Initial Capital**: $100,000

---

## Bullish Vertical Put Strategy

**Status**: ⏳ Pending optimization

**Description**: Sells credit spreads on bullish days with favorable Greeks.

### Parameter Grid Tested

```python
param_grid = {
    'spread_width': [5.0, 10.0, 15.0, 20.0, 25.0],
    'profit_target_min': [0.30, 0.40, 0.50, 0.60, 0.70],
    'stop_loss_pct': [0.50, 0.75, 1.00, 1.50, 2.00],
}
```

### Fixed Parameters

```python
fixed_params = {
    'min_dte': 0,
    'max_dte': 45,
    'min_delta': 0.15,
    'max_delta': 0.35,
    'max_spread_bid_ask_pct': 0.50,
    'min_distance_from_spot_pct': 0.02,
}
```

### Optimal Parameters (Pending)

```yaml
# To be filled after optimization
spread_width: TBD
profit_target_min: TBD
stop_loss_pct: TBD
```

### Performance Metrics (Pending)

- **In-Sample Sharpe**: TBD
- **Out-of-Sample Sharpe**: TBD
- **Sharpe Degradation**: TBD%
- **Win Rate**: TBD%
- **Max Drawdown**: TBD%
- **Total Return**: TBD%

### Walk-Forward Results (Pending)

| Period | Train Period | Test Period | OOS Sharpe | OOS Return | Degradation |
|--------|--------------|-------------|------------|------------|-------------|
| 1      | TBD          | TBD         | TBD        | TBD        | TBD         |
| 2      | TBD          | TBD         | TBD        | TBD        | TBD         |
| 3      | TBD          | TBD         | TBD        | TBD        | TBD         |

### Parameter Stability

**Verdict**: ⏳ Pending analysis

- Do optimal parameters change significantly between periods?
- Is performance consistent across market conditions?

### Recommended Action

⏳ **Run optimization**:
```bash
python scripts/optimize_strategy.py --strategy bullish_vertical_put --walk-forward
```

---

## Bullish Vertical Call Strategy

**Status**: ⏳ Pending optimization

**Description**: 0-2 DTE intraday call spreads entered in the morning, exited before close.

### Parameter Grid Tested

```python
param_grid = {
    'spread_width': [5.0, 10.0, 15.0, 20.0, 25.0],
    'profit_target_min': [0.30, 0.40, 0.50, 0.60, 0.70],
    'stop_loss_pct': [0.50, 0.75, 1.00, 1.50, 2.00],
}
```

### Fixed Parameters

```python
fixed_params = {
    'min_dte': 0,
    'max_dte': 2,
    'entry_hour': 10,
    'entry_minute': 0,
    'exit_hour': 15,
    'exit_minute': 45,
    'min_delta': 0.30,
    'max_delta': 0.50,
}
```

### Optimal Parameters (Pending)

```yaml
# To be filled after optimization
spread_width: TBD
profit_target_min: TBD
stop_loss_pct: TBD
```

### Performance Metrics (Pending)

- **In-Sample Sharpe**: TBD
- **Out-of-Sample Sharpe**: TBD
- **Sharpe Degradation**: TBD%
- **Win Rate**: TBD%
- **Max Drawdown**: TBD%
- **Total Return**: TBD%

### Walk-Forward Results (Pending)

| Period | Train Period | Test Period | OOS Sharpe | OOS Return | Degradation |
|--------|--------------|-------------|------------|------------|-------------|
| 1      | TBD          | TBD         | TBD        | TBD        | TBD         |
| 2      | TBD          | TBD         | TBD        | TBD        | TBD         |
| 3      | TBD          | TBD         | TBD        | TBD        | TBD         |

### Parameter Stability

**Verdict**: ⏳ Pending analysis

### Recommended Action

⏳ **Run optimization**:
```bash
python scripts/optimize_strategy.py --strategy bullish_vertical_call --walk-forward
```

---

## Bearish IV Scalp Strategy

**Status**: ⚠️ Under review (currently disabled)

**Note**: This strategy is currently disabled in live trading config due to performance concerns. Optimization may help, but strategy logic should be reviewed first.

### Parameter Grid (Proposed)

```python
param_grid = {
    'iv_threshold': [0.12, 0.15, 0.18, 0.20],
    'iv_spike_pct': [0.08, 0.10, 0.12, 0.15],
    'profit_target_min': [0.30, 0.40, 0.50, 0.60],
}
```

### Recommended Action

1. ⚠️ **Review strategy logic first** - May have fundamental issues
2. ❓ **Consider disabling permanently** if logic is flawed
3. 🔧 **Fix logic, then optimize** if strategy concept is sound

---

## How to Use This Document

### After Running Optimization

1. Run optimization script:
   ```bash
   python scripts/optimize_strategy.py --strategy <name> --walk-forward
   ```

2. Review results in `results/optimization/`

3. Update this document with:
   - Optimal parameters
   - Performance metrics
   - Walk-forward results
   - Parameter stability assessment
   - Robustness check verdict

4. Update `config/backtest.yaml` with optimal params

5. Run out-of-sample backtest to validate:
   ```bash
   python scripts/run_backtest.py --strategy <name>
   ```

6. If out-of-sample results match walk-forward predictions:
   - Update `config/live_trading.yaml` with optimal params
   - Start paper trading for 1-2 weeks
   - Monitor slippage vs backtest assumptions

### Red Flags (Do NOT Use Parameters If)

- ❌ Sharpe degradation >50%
- ❌ Any period with negative returns
- ❌ Out-of-sample Sharpe <1.0
- ❌ Out-of-sample win rate <55%
- ❌ Parameters change drastically between periods
- ❌ Performance highly sensitive to small parameter changes

### Green Lights (Safe to Use Parameters If)

- ✅ Sharpe degradation <30%
- ✅ All periods positive returns
- ✅ Out-of-sample Sharpe >1.5
- ✅ Out-of-sample win rate >60%
- ✅ Parameters stable across periods
- ✅ Performance robust to small parameter changes
- ✅ Consistent with domain knowledge/theory

---

## Parameter Sensitivity Analysis

### Heatmap Generation

Create heatmaps to visualize parameter interactions:

```python
from quant_vibe.optimization import ParameterOptimizer

# After running grid search
pivot = optimizer.create_heatmap_data(
    param_x='spread_width',
    param_y='profit_target_min',
    metric='sharpe_ratio'
)

# Plot with matplotlib/seaborn
import seaborn as sns
import matplotlib.pyplot as plt

sns.heatmap(pivot, annot=True, fmt='.2f', cmap='RdYlGn')
plt.title('Sharpe Ratio by Spread Width vs Profit Target')
plt.show()
```

### Analyzing Stability

**Good**: Small parameter changes = small performance changes (smooth surface)
**Bad**: Small parameter changes = large performance swings (overfitting)

Look for:
- Broad plateau of good performance (robust)
- Isolated peak (overfitted, avoid)
- Consistent patterns across metrics

---

## Version History

### 2025-12-31 - Initial Version
- Created documentation structure
- Defined optimization process
- Set up parameter grids for all strategies
- Pending: Actual optimization results

### Future Updates

Track changes when parameters are re-optimized:
- Date of optimization
- Data period used
- Why parameters changed
- Performance impact

---

## Notes

### Re-optimization Schedule

Parameters should be re-optimized when:
1. **Quarterly**: Normal schedule (every 3 months)
2. **Market regime change**: Major volatility shifts
3. **Performance degradation**: Live Sharpe drops >20% from backtest
4. **New data available**: After collecting 3+ months of new live data

### Parameter Constraints

When optimizing, respect these constraints:
- Spread width: 5-30 (SPX) - narrower=more risk, wider=less premium
- Profit target: 0.30-0.70 - lower=higher win rate but smaller wins
- Stop loss: 0.50-2.00x credit - tighter=fewer losers but more frequent
- DTE: 0-45 days - higher=more theta decay, lower=more gamma risk

### Domain Knowledge

Don't purely trust optimization:
- Parameters should make sense theoretically
- Extremely aggressive (0.90 profit target) or conservative (5% profit target) unlikely to be optimal
- Very tight stops (<0.50x) likely to get stopped out too often
- Very wide stops (>2.00x) defeat the purpose of risk management

---

## Questions?

See:
- `CLAUDE.md` - Architecture and development guide
- `docs/HOWTO_NEW_STRATEGY.md` - Strategy development
- `scripts/optimize_strategy.py` - Optimization script
- `src/quant_vibe/optimization/` - Optimization framework code
