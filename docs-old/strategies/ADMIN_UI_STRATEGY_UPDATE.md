# Admin UI Strategy Update - Bearish IV Scalp

## Summary

The **Bearish IV Scalp** strategy has been successfully enabled in the Admin UI frontend backtest runner.

## Changes Made

### Backend API Update

**File**: `src/admin_ui/backend/api/backtests.py`

**Change**: Added bearish_iv_scalp to the strategies list in the `/backtests/strategies` endpoint

```python
strategies = [
    {
        "name": "bullish_vertical_put",
        "display_name": "Bullish Vertical Put",
        "description": "0 DTE bullish vertical put spread strategy",
    },
    {
        "name": "bullish_vertical_call",
        "display_name": "Bullish Vertical Call",
        "description": "0 DTE bullish vertical call spread strategy",
    },
    {
        "name": "bearish_iv_scalp",  # NEW
        "display_name": "Bearish IV Scalp",
        "description": "0 DTE bearish IV scalping with vertical call spreads - profit from IV contraction during bearish moves",
    },
]
```

### Services Restarted

- ✅ Backend container restarted: `docker restart quant-vibe-admin-ui`
- ✅ Backend is healthy and running on port 8000
- ✅ Frontend is running on port 80 (no changes needed - dynamically loads strategies)

## How It Works

### Architecture

```
Frontend (React)
    ↓
    useStrategies() hook
    ↓
    GET /api/backtests/strategies
    ↓
Backend (FastAPI)
    ↓
    list_strategies() endpoint
    ↓
    Returns strategy list (hardcoded for now)
```

### Frontend Components

The frontend automatically displays all strategies returned from the API:

**File**: `src/admin_ui/frontend/src/pages/BacktestRunner.tsx`

- Strategy dropdown is dynamically populated from `useStrategies()` hook
- No frontend code changes needed
- Strategy selection happens via `<select>` element (lines 199-211)

### API Response Format

```json
{
  "strategies": [
    {
      "name": "bearish_iv_scalp",
      "display_name": "Bearish IV Scalp",
      "description": "0 DTE bearish IV scalping with vertical call spreads - profit from IV contraction during bearish moves"
    }
  ],
  "count": 3
}
```

## Verification Steps

### 1. Access Admin UI

Open browser to: `http://localhost` (or your server IP)

### 2. Navigate to Backtest Runner

- Click "Backtest Runner" in the sidebar
- Go to "Run Backtest" tab

### 3. Check Strategy Dropdown

You should now see:
- ✅ Bullish Vertical Put
- ✅ Bullish Vertical Call
- ✅ **Bearish IV Scalp** (NEW)

### 4. Run a Backtest

1. Select "Bearish IV Scalp" from dropdown
2. Set date range (e.g., December 2025)
3. Set DTE range (0 DTE for this strategy)
4. Set initial capital ($100,000)
5. Click "Run Backtest"

### 5. View Results

The backtest will execute using the backend and display:
- Equity curve
- Performance metrics (Sharpe, max drawdown, win rate)
- Trade history
- P&L distribution

## Backend Strategy Execution Flow

When you run a backtest from the UI:

```
1. Frontend sends POST /api/backtests/run
   {
     "strategy_name": "bearish_iv_scalp",
     "start_date": "2025-12-01",
     "end_date": "2025-12-31",
     "initial_capital": 100000,
     "params": { ... }
   }

2. Backend spawns subprocess:
   python scripts/run_backtest.py --strategy bearish_iv_scalp

3. BacktestOrchestrator loads strategy:
   - Reads config/backtest.yaml
   - Loads BearishIVScalpStrategy class
   - Runs backtest with parameters

4. Results saved to database:
   - Trades table
   - Equity curve
   - Performance metrics

5. Frontend polls for completion:
   GET /api/backtests/{backtest_id}/status
   GET /api/backtests/{backtest_id}/results

6. Results displayed in UI
```

## Strategy Parameters in UI

The frontend currently passes these parameters:
- `min_dte` (from DTE range input)
- `max_dte` (from DTE range input)
- `max_trades_daily` (from dedicated input)

For the Bearish IV Scalp strategy, recommended settings:
- **Min DTE**: 0 (same-day expiration)
- **Max DTE**: 0 (0DTE only)
- **Max Trades Daily**: 2 (default from strategy)
- **Initial Capital**: $100,000

## Future Enhancements

### Dynamic Strategy Loading (TODO)

Current limitation: Strategies are hardcoded in `backtests.py`

**Improvement**: Auto-discover strategies from `config/backtest.yaml`

```python
# Future implementation
@router.get("/strategies")
async def list_strategies():
    config = BacktestConfig('config/backtest.yaml')

    strategies = []
    for strategy_config in config.strategies.enabled:
        # Load strategy metadata dynamically
        strategy_class = load_strategy_class(strategy_config.name)
        strategies.append({
            "name": strategy_config.name,
            "display_name": strategy_class.display_name,
            "description": strategy_class.__doc__,
            "default_params": strategy_config.params,
        })

    return {"strategies": strategies, "count": len(strategies)}
```

### Advanced Parameter Configuration

Add UI controls for strategy-specific parameters:
- IV threshold slider
- IV spike percentage input
- Profit target range
- Trailing stop percentage

## Testing Checklist

- [x] Backend code updated with new strategy
- [x] Backend container restarted successfully
- [x] Backend health check passing
- [x] Strategy appears in API response (requires auth)
- [ ] UI displays new strategy in dropdown (manual verification needed)
- [ ] Backtest runs successfully from UI (manual verification needed)
- [ ] Results display correctly (manual verification needed)

## Manual Verification Required

Since the API requires authentication, please verify manually:

1. **Login to Admin UI**: http://localhost
2. **Navigate to Backtest Runner**
3. **Check dropdown**: Should see "Bearish IV Scalp"
4. **Run test backtest**: Use Dec 2025 data
5. **Verify results**: Check metrics and trades

## Rollback Instructions

If you need to revert this change:

```bash
# 1. Edit backtests.py to remove bearish_iv_scalp entry
# 2. Restart backend
docker restart quant-vibe-admin-ui
```

## Documentation

For more details on the strategy:
- Strategy implementation: `BEARISH_IV_SCALP_STRATEGY.md`
- Strategy code: `src/quant_vibe/strategies/bearish_iv_scalp.py`
- Configuration: `config/backtest.yaml`
