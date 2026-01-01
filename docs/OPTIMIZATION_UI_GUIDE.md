# Strategy Optimization UI Guide

## Overview

The Strategy Optimization UI provides a web-based interface for finding optimal trading strategy parameters using grid search and walk-forward analysis. This guide explains how to use the optimization features effectively.

## Features

### 1. Grid Search Optimization
- **Purpose**: Find the best parameter combination from a defined search space
- **Method**: Tests all possible combinations of parameters on training data
- **Output**: Top parameter sets ranked by Sharpe ratio (risk-adjusted return)
- **Use Case**: Initial parameter discovery and tuning

### 2. Walk-Forward Analysis
- **Purpose**: Validate parameter robustness across different market conditions
- **Method**: Rolling window optimization with out-of-sample testing
- **Output**: Performance degradation metrics and consistency checks
- **Use Case**: Prevent overfitting and ensure strategy stability

## Accessing the Optimizer

1. Start the Admin UI:
   ```bash
   cd src/admin_ui/frontend
   npm run dev
   ```

2. Navigate to **Optimize** in the sidebar menu

3. Login with your credentials (default: `admin:changeme`)

## Running an Optimization

### Step 1: Configure the Optimization

**Required Fields:**
- **Strategy**: Select the strategy to optimize (e.g., `bullish_vertical_put`)
- **Optimization Type**: Choose between Grid Search or Walk-Forward Analysis
- **Training Start Date**: Beginning of training data period
- **Training End Date**: End of training data period

**Optional Fields (Grid Search only):**
- **Test Start Date**: Beginning of out-of-sample validation period
- **Test End Date**: End of out-of-sample validation period

**Advanced:**
- **Initial Capital**: Starting account balance (default: $100,000)

### Step 2: Select Date Range

Use the quick preset buttons for common date ranges:

**Training Data Presets:**
- **Last 3 Months**: Quick optimization with recent data
- **Last Year**: More comprehensive parameter search

**Train/Test Split Presets:**
- **Train: 5-2 months ago, Test: Last 2 months**: 3-month training, 2-month validation
- **Train: Year (excl. last 3 mo), Test: Last 3 months**: 9-month training, 3-month validation

**Best Practices:**
- **Training Period**: Use at least 60 days for meaningful statistics
- **Test Period**: Reserve 20-30% of data for out-of-sample validation
- **Walk-Forward**: Use at least 90 days total (60 train + 30 test)

### Step 3: Run Optimization

1. Click **Run Optimization** button
2. Switch to the **Results** tab to monitor progress
3. Optimization will run in the background (may take 5-60 minutes)

## Understanding Results

### Grid Search Results

**Best Parameters Card:**
- **Best Sharpe Ratio**: Highest risk-adjusted return achieved
- **Best Return**: Total percentage return with optimal parameters
- **Optimal Parameter Values**: Specific parameter values that produced best results

**Top 10 Parameter Combinations Table:**
- **Rank**: Position by Sharpe ratio (1 = best)
- **Sharpe**: Risk-adjusted return metric (>1.0 good, >2.0 very good, >3.0 excellent)
- **Return**: Total percentage gain/loss
- **Win Rate**: Percentage of profitable trades
- **Max DD**: Maximum drawdown (largest peak-to-trough decline)
- **Trades**: Number of trades executed

**How to Use:**
- Compare top results to identify parameter ranges that work well
- Look for clusters of good parameters (indicates robust regions)
- Avoid isolated peaks (may indicate overfitting)

### Walk-Forward Results

**Walk-Forward Summary Card:**
- **Periods Tested**: Number of rolling windows evaluated
- **Avg OOS Sharpe**: Average out-of-sample Sharpe ratio
- **Avg OOS Return**: Average out-of-sample return
- **Sharpe Degradation**: Performance drop from training to testing

**Degradation Interpretation:**
- **< 30%**: Excellent robustness (parameters are stable)
- **30-50%**: Good robustness (acceptable degradation)
- **50-70%**: Moderate overfitting risk
- **> 70%**: High overfitting risk (avoid these parameters)

**Color Coding:**
- 🟢 Green: Good performance (low degradation)
- 🟡 Yellow: Moderate performance
- 🔴 Red: Poor performance (high degradation)

## Real-Time Progress Tracking

The optimization UI automatically polls for updates every 2 seconds while running:

**Status Indicators:**
- **Pending**: Optimization queued to start
- **Running**: Currently executing parameter tests
- **Completed**: Finished successfully
- **Failed**: Encountered an error

**Progress Bar:**
- Shows percentage complete for grid search
- Updates in real-time as combinations are tested

## Optimization History

The **History** tab shows all previous optimization runs:

**Features:**
- View past results without re-running
- Compare different optimization configurations
- Delete old optimizations to save space

**Actions:**
- **View Results**: Load results in the Results tab
- **Delete**: Remove optimization and result files

## Parameter Grids

The optimizer uses predefined parameter grids for each strategy. These are configured in:
```
scripts/optimize_strategy.py
```

**Example Grid (Bullish Vertical Put):**
```python
{
    "spread_width": [10.0, 15.0, 20.0, 25.0, 30.0],
    "profit_target_min": [0.30, 0.40, 0.50, 0.60, 0.70],
    "trailing_stop_pct": [0.03, 0.05, 0.07, 0.10],
}
```

**Total Combinations**: 5 × 5 × 4 = 100 backtests

**Customizing Grids:**
Edit the `PARAM_GRIDS` dictionary in `scripts/optimize_strategy.py` to add/modify parameter ranges.

## Best Practices

### 1. Start with Grid Search
- Begin with a broad parameter grid
- Identify promising regions
- Refine grid around best results

### 2. Validate with Walk-Forward
- After finding good parameters, run walk-forward analysis
- Ensure parameters work across different time periods
- Check degradation is acceptable (<50%)

### 3. Out-of-Sample Testing
- Always reserve test data for validation
- Never optimize on your test set
- Use walk-forward for time-series validation

### 4. Avoid Overfitting
- Don't cherry-pick parameters from single best result
- Look for robust parameter ranges (multiple good combinations)
- Prefer simple strategies with fewer parameters
- Use walk-forward to detect overfitting

### 5. Production Deployment
After optimization:
1. Review results in the UI
2. Validate on out-of-sample data
3. Update `config/backtest.yaml` with optimal parameters
4. Run full backtest on test period
5. Update `config/live_trading.yaml` when satisfied
6. Paper trade for 1+ week before going live

## Architecture

### Backend API

**Endpoints:**
- `POST /api/optimization/run` - Start optimization
- `GET /api/optimization/status/{id}` - Get status
- `GET /api/optimization/results/{id}` - Get results
- `GET /api/optimization/history` - List all optimizations
- `DELETE /api/optimization/{id}` - Delete optimization

**Implementation:**
- `src/admin_ui/backend/api/optimization.py` - FastAPI router
- Executes `scripts/optimize_strategy.py` as subprocess
- Stores state in `logs/optimization_state/running_optimizations.json`
- Results saved to `results/optimization/{optimization_id}/`

### Frontend Components

**Main Component:**
- `src/admin_ui/frontend/src/pages/StrategyOptimizer.tsx`

**API Integration:**
- `src/admin_ui/frontend/src/api/queries.ts` - React Query hooks
- Auto-polling for running optimizations (2-second interval)
- Automatic history refresh on completion

**Features:**
- Three-tab interface (Run, Results, History)
- Real-time progress tracking
- Date preset buttons
- Results visualization with color-coded metrics

## Troubleshooting

### Optimization Fails to Start
- Check backend logs: `docker-compose logs admin_ui_backend`
- Verify strategy exists in `STRATEGY_MAP`
- Ensure date range has available data

### Optimization Timeout (1 hour)
- Reduce parameter grid size
- Use shorter date range for testing
- Check for bugs in strategy code

### No Results Displayed
- Verify optimization status is "completed"
- Check result files exist in `results/optimization/{id}/`
- Look for errors in backend logs

### Progress Bar Not Updating
- Check browser console for errors
- Verify WebSocket connection to backend
- Refresh page to re-establish polling

## Performance Considerations

**Optimization Runtime:**
- Grid search: ~0.5-5 seconds per combination
- 100 combinations ≈ 1-8 minutes
- 500 combinations ≈ 5-40 minutes

**Factors Affecting Speed:**
- Number of parameter combinations
- Date range (longer = more data to process)
- Strategy complexity
- Database query performance

**Optimization Tips:**
- Start with coarse grid (fewer values per parameter)
- Use shorter date ranges for initial exploration
- Run intensive optimizations during off-hours
- Consider cloud compute for large-scale optimization

## Next Steps

After finding optimal parameters:
1. **Validate**: Run backtest on out-of-sample period
2. **Document**: Save results and rationale in `docs/strategies/`
3. **Configure**: Update YAML config files
4. **Test**: Paper trade for verification
5. **Deploy**: Enable in live trading when confident
6. **Monitor**: Track live performance vs. backtest

## Related Documentation

- `docs/HOWTO_NEW_STRATEGY.md` - Creating new strategies
- `scripts/optimize_strategy.py` - Backend optimization script
- `src/quant_vibe/optimization/` - Optimization framework
- `CLAUDE.md` - Development commands and architecture
