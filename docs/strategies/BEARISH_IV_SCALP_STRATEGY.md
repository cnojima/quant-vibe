# Bearish IV Scalp Strategy for 0DTE SPXW

## Overview

The **Bearish IV Scalp Strategy** is a 0DTE (zero days to expiration) options strategy that capitalizes on elevated implied volatility during bearish market conditions. The strategy sells vertical call spreads when IV spikes during market sell-offs, targeting quick profits from IV crush.

## Strategy Files

- **Strategy Implementation**: `src/quant_vibe/strategies/bearish_iv_scalp.py`
- **Configuration**: `config/backtest.yaml` (added as `bearish_iv_scalp`)
- **Tests**: `tests/test_bearish_iv_scalp.py`
- **Registered in**: `src/backtest/engine.py` (strategy_map)

## Key Strategy Features

### Entry Logic

1. **Observation Period** (15 minutes by default)
   - Monitor market direction at open
   - Identify bearish momentum (declining prices)

2. **IV Spike Detection**
   - Current IV must exceed threshold (15% default)
   - IV must spike by 10%+ from recent 30-bar average
   - Focuses on ATM call options (within ±2% of spot)

3. **Entry Signal**
   - Bearish market direction confirmed
   - IV spike detected on call options
   - Sufficient liquidity in 0DTE options

### Position Structure

**Bearish Vertical Call Spread (Credit Spread)**:
- **Sell** 1 call at lower strike (closer to ATM)
- **Buy** 1 call at higher strike ($10 above, for protection)
- **Receive** net credit on entry
- **Position size**: 5 spreads (default)

### Exit Logic

1. **Profit Target**: 30-50% of max profit
2. **Trailing Stop**: Tight 3% stop from peak P&L
3. **Stop Loss**: 75% of max risk
4. **Time-based**: Close at 3:45 PM ET (0DTE management)

## Strategy Parameters

```yaml
params:
  max_trades_daily: 2              # Allow 1-2 scalps per day
  spread_width: 10                 # $10 wide spreads
  observation_period: 15           # Quick 15-min observation
  iv_threshold: 0.15               # Minimum 15% IV required
  iv_spike_pct: 0.10               # 10% IV increase from avg
  profit_target_min: 0.30          # 30% profit target
  profit_target_max: 0.50          # 50% profit target
  trailing_stop_pct: 0.03          # Tight 3% trailing stop
  stop_loss_pct: 0.75              # 75% stop loss
  min_dte: 0                       # 0DTE only
  max_dte: 0                       # 0DTE only
  num_spreads: 5                   # 5 spreads per entry
  min_volume: 20                   # Lower volume for 0DTE
  min_bid_ask_spread_pct: 15       # Accept wider spreads
  momentum_lookback: 5             # 5 bars for momentum
  iv_lookback: 30                  # 30 bars for IV average
```

## Risk Management

### Position Sizing
- **Small size**: 5 spreads (vs. 10 for other strategies)
- **Reason**: 0DTE has higher risk due to rapid time decay

### Stop Loss
- **75% of max risk**: Tighter than typical strategies
- **Reasoning**: 0DTE can move quickly against you

### Trailing Stop
- **3% from peak**: Very tight to lock in profits
- **Reasoning**: IV can reverse quickly

### Time Management
- **Close by 3:45 PM ET**: Avoids pin risk and final 15 mins
- **0DTE only**: Expires same day, no overnight risk

## Data Requirements

### ⚠️ IMPORTANT: Implied Volatility Data Required

This strategy **requires** historical implied volatility (IV) data to function. The current historical data from Massive API does **not** include IV values.

**Current Status**:
- ❌ Historical data (0DTE SPXW from Massive): **No IV data**
- ✅ Real-time streaming data (schwabdev): **IV available** (if enriched)
- ❌ Backtesting: **Will not generate trades** without IV

**Solutions**:
1. **Live Trading Only**: Use this strategy only for live trading with real-time IV data
2. **Backfill IV**: Calculate/estimate IV for historical data (complex)
3. **Alternative Signal**: Modify strategy to use price volatility instead of IV

**Workaround for Backtesting**:
Currently, backtests will complete successfully but show **0 trades** because IV spike detection never triggers. This is expected behavior with missing IV data.

## When This Strategy Works Best

### Market Conditions
✅ **Bearish sell-offs** with elevated volatility
✅ **IV spikes** on call options during declines
✅ **Mean-reversion setup**: IV likely to contract
✅ **Liquid 0DTE options** with tight spreads
✅ **Real-time IV data available** (live trading or enriched historical data)

### Ideal Scenario
1. Market opens, begins declining
2. Call IV spikes as traders buy protection
3. Enter when IV elevated + bearish confirmed
4. IV contracts as selling pressure eases
5. Exit with 30-50% profit in 1-3 hours

### Avoid When
❌ Low volatility environments
❌ Choppy/sideways markets (no clear direction)
❌ Low liquidity in 0DTE options
❌ After first hour (premium already decayed)

## How to Run

### Backtest with Config-Based Orchestrator

```bash
# Run all enabled strategies (includes bearish_iv_scalp)
python scripts/run_backtest.py

# Run ONLY bearish_iv_scalp
python scripts/run_backtest.py --strategy bearish_iv_scalp

# Disable other strategies in config/backtest.yaml
# Set enabled: false for bullish_vertical_put and bullish_vertical_call
```

### Enable/Disable in Config

Edit `config/backtest.yaml`:

```yaml
strategies:
  enabled:
    - name: bearish_iv_scalp
      enabled: true  # Set to false to disable
      params:
        # ... parameters ...
```

### Run Tests

```bash
# Run basic unit tests
source venv/bin/activate
python tests/test_bearish_iv_scalp.py
```

## Performance Metrics

The strategy tracks standard metrics via `BacktestReporter`:

- **Win Rate**: Percentage of profitable trades
- **Average Win/Loss**: Profit per winning/losing trade
- **Sharpe Ratio**: Risk-adjusted returns
- **Max Drawdown**: Largest peak-to-trough decline
- **Return on Risk**: Credit received / max risk
- **IV Analysis**: IV levels at entry/exit

## Implementation Details

### IV Calculation
- Focuses on **ATM call options** (±2% of spot)
- Compares current IV to 30-bar rolling average
- Spike = current IV > threshold AND > avg + spike_pct

### Data Completeness Check
- Validates 80%+ data coverage (vs. 95% for other strategies)
- Shorter lookback (30 mins) for 0DTE
- Ensures contracts have been present recently

### Greeks (Future Enhancement)
- Currently not used in entry/exit logic
- Potential to add delta-based position sizing
- Theta decay tracking for optimization

## Example Trade Flow

**Entry (10:15 AM ET)**:
- Market down 0.5% since open
- ATM call IV = 18% (up from 14% 30-min avg)
- **Action**: Sell 5900/5910 call spread, receive $250 credit
- **Max Risk**: $5,000 (10 points × 100 × 5 spreads)
- **Target**: $125-$175 profit (50-70% of credit)

**Exit (11:30 AM ET)**:
- Spread value declined to $100 (from $250 entry)
- **P&L**: $150 profit (60% of max)
- **Reason**: Profit target hit (50% of max)
- **Duration**: 75 minutes

## Next Steps / Improvements

1. **Backtest with historical data**: Run on Dec 2025 0DTE data
2. **Optimize parameters**: Test different IV thresholds, profit targets
3. **Greeks integration**: Use delta for position sizing
4. **Multi-timeframe**: Test on 1DTE, 2DTE options
5. **Combo strategies**: Pair with bullish strategies for market-neutral portfolio

## Related Strategies

- **Bullish Vertical Put** (`bullish_vertical_put.py`): Bullish credit spread
- **Bullish Vertical Call** (`bullish_vertical_call.py`): Bullish debit spread

## References

- **SPXW Options**: S&P 500 Weekly options (PM-settled, 0DTE available Mon-Fri)
- **0DTE Trading**: Same-day expiration, high theta decay, elevated IV
- **IV Scalping**: Profit from volatility expansion/contraction
