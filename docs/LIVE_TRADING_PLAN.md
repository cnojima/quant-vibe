# Live Trading Engine - Complete Implementation Plan

## Overview

This document outlines the complete 6-phase plan for implementing a production-ready live trading engine for options strategies using SPXW streaming data.

**Current Status**: ✅ Phase 1 Complete
**Timeline**: 6-8 weeks total
**Mode**: Simulated paper trading first, then live after validation
**Note**: Schwab does not offer paper trading accounts via API - we simulate internally

---

## Phase Summary

| Phase | Timeline | Status | Focus |
|-------|----------|--------|-------|
| **1: Core Infrastructure** | Weeks 1-2 | ✅ Complete | Engine, data feed, persistence |
| **2: Orders & Positions** | Weeks 2-3 | 🔄 Next | Order submission, position tracking |
| **3: Strategy Integration** | Weeks 3-4 | 🔜 Planned | Execute strategies on live data |
| **4: Risk Management** | Weeks 4-5 | 🔜 Planned | Limits, circuit breakers, safety |
| **5: Monitoring & Alerts** | Weeks 5-6 | 🔜 Planned | Dashboard, notifications |
| **6: Testing & Validation** | Weeks 6-8 | 🔜 Planned | Paper trading, go-live prep |

---

## Paper Trading Implementation

**Constraint**: Schwab does not offer paper trading accounts via API.

**Solution**: Internal simulation with dual-mode architecture.

### How It Works

**Simulated Mode** (`paper_trading: true`):
1. Strategy generates entry signal
2. OrderManager creates order internally (no API call)
3. Order "filled" immediately using current bid/ask quotes
4. Apply realistic slippage based on:
   - Spread width (0 DTE: 1-10%, 1 DTE: 0.8-8%, 2+ DTE: 0.5-5%)
   - Order side (buy at ask, sell at bid)
   - Market conditions (wider during high volatility)
5. PositionManager tracks position using real streaming data
6. Exit signals processed same way
7. All activity logged to database as if real

**Live Mode** (`paper_trading: false`):
1. Strategy generates entry signal
2. OrderManager submits actual order to Schwab API
3. Poll order status until filled/cancelled/rejected
4. PositionManager tracks position using streaming data + broker reconciliation
5. Exit signals submit real orders
6. All activity logged to database

### Benefits of This Approach

- ✅ Test complete system logic without risk
- ✅ Validate strategy timing and signals
- ✅ Identify bugs before live trading
- ✅ Use real market data (not simulated market)
- ✅ Easy mode switch (config change only)
- ✅ No broker paper account limitations

### Limitations

- ⚠️ Fill simulation may not match live fills exactly
- ⚠️ Can't test broker rejection scenarios in simulated mode
- ⚠️ Slippage estimates may differ from actual
- ⚠️ No partial fills in simulated mode (always 100% filled)

### Testing Strategy

1. **Weeks 1-6**: Build all components, test in simulated mode
2. **Weeks 7-8**:
   - 1 week continuous simulated paper trading
   - Fix any issues found
   - 1-2 small live trades (1 contract each)
   - If successful, gradually increase size
3. **Ongoing**: Always test new strategies in simulated mode first

---

## Detailed Phase Plans

### Phase 1: Core Infrastructure ✅ COMPLETE

**See**: `docs/LIVE_TRADING_PHASE1.md`

**Delivered**:
- LiveTradingEngine orchestrator
- RealtimeDataFeed (streaming consumer)
- StateStore (database persistence)
- Logging & utilities
- YAML configuration
- Entry scripts & tests

---

### Phase 2: Order & Position Management 🔄 NEXT

**Goal**: Submit orders to broker and track positions in real-time.

**Important**: Schwab does not provide paper trading accounts via API. The OrderManager implements **two modes**:
- **Simulated mode** (`paper_trading: true`): Orders processed internally with simulated fills
- **Live mode** (`paper_trading: false`): Orders submitted to Schwab API

**Components**:

1. **OrderManager** (`src/quant_vibe/live/order_manager.py`)
   - Convert OptionsPosition → Schwab API order format
   - **Simulated Mode**:
     - Process orders internally (no API calls)
     - Simulate fills using current bid/ask quotes
     - Apply realistic slippage (1-5% based on spread width)
     - Track simulated order status
   - **Live Mode**:
     - Submit multi-leg spread orders to Schwab API
     - Poll order status until filled/cancelled
     - Handle partial fills
     - Calculate actual slippage

2. **PositionManager** (`src/quant_vibe/live/position_manager.py`)
   - Track all open positions
   - Update position values from streaming data
   - Calculate real-time P&L
   - Monitor profit targets and stops
   - Reconcile with broker

**Tasks**:
- [ ] Build OrderManager class with dual-mode architecture
- [ ] Implement simulated order processing (paper trading mode)
  - [ ] Simulate fills using bid/ask quotes
  - [ ] Apply realistic slippage models
  - [ ] Track simulated order lifecycle
- [ ] Implement live Schwab order submission
  - [ ] Convert to Schwab API order format
  - [ ] Submit multi-leg spread orders
  - [ ] Poll order status until completion
- [ ] Build PositionManager class
- [ ] Implement position valuation from streaming data
- [ ] Add position reconciliation (live mode only)
- [ ] Test extensively in simulated mode

**Acceptance Criteria**:
- ✅ Multi-leg spread orders constructed correctly
- ✅ **Simulated mode**: Orders filled instantly with realistic slippage
- ✅ **Live mode**: Orders submitted to Schwab API successfully
- ✅ Order status tracked accurately in both modes
- ✅ Positions valued in real-time from streaming data
- ✅ P&L calculations match expectations
- ✅ Mode switching works correctly (config change only)

---

### Phase 3: Strategy Integration 🔜 PLANNED

**Goal**: Execute existing strategies on live streaming data.

**Components**:

1. **StrategyExecutor** (`src/quant_vibe/live/strategy_executor.py`)
   - Load strategies from configuration
   - Execute strategy logic on each bar
   - Manage strategy state (daily resets)
   - Track per-strategy performance

2. **Strategy Adaptation**
   - Adapt backtest strategies for live trading
   - Handle real-time data (not just DataFrames)
   - Add position sizing validation

**Execution Flow**:
```
New bars received
  ↓
Get underlying price + options chain
  ↓
strategy.analyze_market()
  ↓
If should_enter():
  - strategy.construct_spread()
  - RiskManager.check()
  - OrderManager.submit()
  - PositionManager.track()
  ↓
For each open position:
  - Update value from quotes
  - strategy.should_exit()?
  - If yes: close position
```

**Tasks**:
- [ ] Build StrategyExecutor class
- [ ] Create strategy loading system
- [ ] Implement execution loop
- [ ] Add strategy adapters
- [ ] Test with BullishVerticalPutStrategy
- [ ] Add daily state reset
- [ ] Build performance tracking

**Acceptance Criteria**:
- ✅ Strategies load from config
- ✅ Strategy signals match backtests
- ✅ Multiple strategies run concurrently
- ✅ Daily resets work correctly

---

### Phase 4: Risk Management 🔜 PLANNED

**Goal**: Comprehensive risk controls to protect capital.

**Components**:

1. **RiskManager** (`src/quant_vibe/live/risk_manager.py`)

**Pre-Trade Checks**:
- Capital availability
- Position size limits  
- Concentration limits
- Daily trade count limit

**Intra-Trade Monitoring**:
- Real-time P&L
- Drawdown levels
- Greeks exposure

**Circuit Breakers**:
- Daily loss limit (5%)
- Max drawdown (10%)
- Data feed unhealthy
- Multiple order errors

**Emergency Controls**:
- Kill switch (close all positions)
- Auto-shutdown triggers
- End-of-day force close

**Risk Limits**:
```yaml
Capital:
  - Max per trade: $10,000
  - Max total exposure: $100,000
  - Min reserve: $10,000

Positions:
  - Max open: 5
  - Max concentration: 30% single position
  - Max contracts per symbol: 100

Losses:
  - Daily loss limit: 5% of capital
  - Max drawdown: 10% from peak
  - Per-trade stop loss: Strategy-defined
```

**Tasks**:
- [ ] Build RiskManager class
- [ ] Implement pre-trade checks
- [ ] Add intra-trade monitoring
- [ ] Build circuit breakers
- [ ] Implement kill switch
- [ ] Test limit enforcement

**Acceptance Criteria**:
- ✅ All limits enforced
- ✅ Circuit breakers trigger correctly
- ✅ Kill switch works
- ✅ Alerts sent on violations

---

### Phase 5: Monitoring & Alerts 🔜 PLANNED

**Goal**: Operational visibility and notifications.

**Components**:

1. **Console Dashboard**
```
╔════════════════════════════════════════════════╗
║      LIVE TRADING ENGINE - STATUS              ║
╠════════════════════════════════════════════════╣
║ State: RUNNING     Mode: PAPER TRADING         ║
║ Uptime: 2h 34m     Market: OPEN                ║
╠════════════════════════════════════════════════╣
║ POSITIONS (1 open)                             ║
║  #1 BVP_20231215  P&L: +$1,250 (27%)          ║
╠════════════════════════════════════════════════╣
║ METRICS                                        ║
║  Daily P&L:     +$1,250 (1.25%)               ║
║  Open:          1 / 5                          ║
║  Capital Used:  4.5%                           ║
║  Win Rate:      75%                            ║
╚════════════════════════════════════════════════╝
```

2. **Alerting System**
   - Email (SMTP)
   - SMS (Twilio - optional)
   - Console warnings
   - Log files

**Alert Conditions**:
- **Critical**: Daily loss limit, max drawdown, data stale
- **Warning**: Position opened/closed, approaching limits
- **Info**: Engine start/stop, EOD summary

3. **Health Checks**
   - Data feed healthy?
   - Database connected?
   - Schwab API accessible?
   - Open positions count
   - Error rate

**Tasks**:
- [ ] Build Monitor class
- [ ] Create console dashboard
- [ ] Build AlertManager
- [ ] Add email alerting
- [ ] Implement health checks
- [ ] Build performance dashboard

**Acceptance Criteria**:
- ✅ Dashboard displays correctly
- ✅ Real-time updates work
- ✅ All alerts trigger
- ✅ Health checks detect issues

---

### Phase 6: Testing & Validation 🔜 PLANNED

**Goal**: Comprehensive testing before live trading.

**Testing Phases**:

1. **Simulated Paper Trading** (1-2 weeks)
   - Run with `paper_trading: true` in config
   - Use real market data from Schwab stream
   - Simulate order fills internally (no API calls)
   - Apply realistic slippage models
   - Validate strategy logic and timing
   - Monitor continuously for stability
   - No real money at risk, no broker interaction

2. **Backtest Validation**
   - Replay historical data through live engine
   - Compare results to backtests
   - Verify entry/exit timing
   - Check P&L accuracy

3. **Failure Scenario Testing**
   - Stream disconnection
   - Database failure
   - API timeouts
   - Partial fills
   - Order rejections
   - Circuit breaker triggers

4. **Small Live Test**
   - 1-2 real trades
   - 1 contract per trade
   - Manual approval
   - Close monitoring
   - Capital at risk: $500-1,000

**Validation Checklist**:

Technical:
- [ ] 1 week stable simulated paper trading
- [ ] Zero critical errors in simulation mode
- [ ] Backtest results roughly match (within 10% due to slippage variance)
- [ ] Failure scenarios handled gracefully
- [ ] Small live test successful (1-2 real trades)

Risk:
- [ ] All limits working
- [ ] Circuit breakers tested
- [ ] Kill switch functional
- [ ] Position reconciliation accurate

Operational:
- [ ] Monitoring reliable
- [ ] Alerts delivered
- [ ] Logs complete
- [ ] Documentation complete

**Go-Live Decision**:
- Review all test results
- Confirm risk parameters
- Define success metrics
- Plan monitoring schedule
- Document procedures

---

## Configuration Example

```yaml
engine:
  paper_trading: true  # IMPORTANT: Simulated mode (no real orders)
                       # Set to false only after successful simulated testing
  max_positions: 5
  max_capital_per_trade: 10000
  daily_loss_limit_pct: 0.05

strategies:
  enabled:
    - name: bullish_vertical_put
      capital_allocation: 50000
      params:
        spread_width: 10
        profit_target: 0.5

risk:
  max_total_exposure: 100000
  max_drawdown_pct: 0.10
  position_concentration_limit: 0.30

monitoring:
  email_alerts_enabled: true
  alerts:
    on_daily_loss_limit: true
    on_position_close: true
```

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Runaway losses | Daily loss limit, max drawdown breaker |
| Order errors | Simulated paper trading validation, format tests, small live test |
| Fill simulation inaccuracy | Apply conservative slippage, validate with small live trades |
| Data issues | Staleness detection, auto-pause |
| System crashes | State persistence, auto-restart |
| Strategy bugs | Backtest validation, simulated paper trading, small position sizes |
| Broker API failures | Retry logic, order status polling, manual intervention alerts |

---

## Success Metrics

**Technical**:
- Uptime: >99.5% during market hours
- Data latency: <1 second
- Order submission: <500ms
- Error rate: <0.1%

**Trading**:
- Slippage: <5% vs expected
- Max drawdown: Within limits (<10%)
- Sharpe ratio: >1.0 target

**Operational**:
- Alert response: <5 min
- Recovery time: <15 min
- Monitoring: 100% coverage

---

## Next Steps

### This Week
1. ✅ Complete Phase 1 testing
2. ✅ Document plan
3. 🔄 Begin Phase 2 (OrderManager)

### Next 2 Weeks
1. Implement OrderManager (dual-mode: simulated + live)
2. Implement PositionManager
3. Test extensively in simulated paper trading mode

### Weeks 3-6
1. Complete Phases 3-5
2. Build monitoring dashboard
3. Extensive simulated paper trading

### Weeks 7-8
1. Comprehensive testing
2. Small live test
3. Go-live decision

---

## Documentation

**Existing**:
- `docs/LIVE_TRADING_PHASE1.md` - Phase 1 details
- `docs/LIVE_TRADING_PLAN.md` - This document
- `config/live_trading.yaml` - Configuration reference

**To Create**:
- Runbook (start/stop/monitor)
- Troubleshooting guide
- Alert response procedures
- Disaster recovery plan

---

## Contact & Support

**Questions**: Document in `docs/QUESTIONS.md`

**Issues**: Create detailed bug reports with:
- Logs from `logs/live_trading/`
- Query `live_events` table
- Screenshots of error
- Steps to reproduce

---

**Last Updated**: 2025-12-17
**Version**: 1.1
**Status**: Phase 1 Complete ✅
**Next**: Phase 2 - Order & Position Management
**Note**: Updated to reflect simulated paper trading (Schwab has no API paper trading)
