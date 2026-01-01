# TODO: Quant-Vibe Development Roadmap

**Goal**: Generate $1,780 daily income from $800K capital using systematic SPX options spreads

**Last Updated**: 2025-01-01

## 📊 ANALYTICS & OPTIMIZATION (Week 2-3)

### [ ] 5. Parameter Optimization Framework
**Priority**: MEDIUM  
**Estimated Time**: 4 hours  
**Files**: `src/quant_vibe/optimization/parameter_optimizer.py`

#### Create Optimizer
- [ ] Create `src/quant_vibe/optimization/parameter_optimizer.py`:
```python
class ParameterOptimizer:
    def __init__(self, strategy_class, data, initial_capital):
        self.strategy_class = strategy_class
        self.data = data
        self.initial_capital = initial_capital
    
    def grid_search(self, param_grid: dict) -> pd.DataFrame:
        """
        Run grid search over parameter combinations.
        
        Args:
            param_grid: dict like {
                'spread_width': [5, 10, 15, 20],
                'profit_target_min': [0.30, 0.40, 0.50, 0.60],
                'stop_loss_pct': [0.50, 0.75, 1.00]
            }
        
        Returns:
            DataFrame with columns:
            - params: dict of parameter combination
            - total_return: float
            - sharpe_ratio: float
            - max_drawdown: float
            - win_rate: float
            - num_trades: int
            - profit_factor: float
        """
        pass
    
    def find_optimal(self, metric: str = 'sharpe_ratio') -> dict:
        """Return best parameter set by specified metric."""
        pass
```

#### Optimize Each Strategy
- [ ] Bullish Vertical Put:
  - [ ] Parameters: spread_width (5, 10, 15, 20)
  - [ ] Parameters: profit_target_min (0.30, 0.40, 0.50, 0.60)
  - [ ] Parameters: stop_loss_pct (0.50, 0.75, 1.00, 1.50)
  - [ ] Train on: Sep-Nov 2025 data
  - [ ] Test on: Dec 2025 data (out-of-sample)
  
- [ ] Bullish Vertical Call:
  - [ ] Same parameter grid as above
  - [ ] Same train/test split
  
- [ ] Bearish IV Scalp (if using live):
  - [ ] Parameters: iv_threshold (0.12, 0.15, 0.18)
  - [ ] Parameters: iv_spike_pct (0.08, 0.10, 0.12)
  - [ ] Parameters: profit_target_min (0.30, 0.40, 0.50)

#### Analysis
- [ ] Create heatmaps of parameter performance
- [ ] Check for parameter stability (small changes = small impact)
- [ ] Avoid overfitting (validate on out-of-sample data)
- [ ] Document optimal parameters in `docs/strategies/OPTIMAL_PARAMETERS.md`

#### Update Configs
- [ ] Update `config/backtest.yaml` with optimal params
- [ ] Update `config/live_trading.yaml` with optimal params
- [ ] Keep previous params commented for reference

**Success Criteria**: Each strategy has optimized parameters validated on out-of-sample data

---

### [ ] 6. Walk-Forward Analysis
**Priority**: MEDIUM  
**Estimated Time**: 3 hours  
**Files**: `src/quant_vibe/optimization/walk_forward.py`

#### Implementation
- [ ] Create `src/quant_vibe/optimization/walk_forward.py`:
```python
class WalkForwardAnalysis:
    def __init__(self, strategy, train_window: int = 60, test_window: int = 30):
        """
        Args:
            train_window: days to train on
            test_window: days to test on
        """
        self.strategy = strategy
        self.train_window = train_window
        self.test_window = test_window
    
    def run(self, data: pd.DataFrame, param_grid: dict) -> pd.DataFrame:
        """
        Walk-forward optimization:
        1. Train on 60 days, optimize parameters
        2. Test on next 30 days with optimal params
        3. Roll window forward, repeat
        
        Returns:
            DataFrame with performance by test period
        """
        pass
```

#### Test Periods
- [ ] Period 1: Train Sep 1-Oct 30, Test Nov 1-30
- [ ] Period 2: Train Oct 1-Nov 30, Test Dec 1-31
- [ ] Period 3: Train Sep 1-Nov 30, Test Dec 1-31 (full test)

#### Metrics to Track
- [ ] Out-of-sample Sharpe ratio (should be >1.0)
- [ ] Out-of-sample win rate (should be >55%)
- [ ] Parameter stability (do optimal params change drastically?)
- [ ] Degradation from in-sample to out-of-sample

#### Red Flags
- [ ] Sharpe drops >50% out-of-sample → overfitting
- [ ] Win rate drops >20% out-of-sample → overfitting
- [ ] Negative returns in any test period → strategy not robust

**Success Criteria**: Strategies maintain >70% of in-sample performance on out-of-sample data

---

### [ ] 7. Slippage & Fill Analysis
**Priority**: MEDIUM  
**Estimated Time**: 2 hours  
**Files**: `src/quant_vibe/analytics/slippage_analyzer.py`

#### Track Slippage
- [ ] Compare backtest fills to actual paper trading fills
- [ ] Measure in both $ and % terms
- [ ] Break down by:
  - [ ] Time of day (worse at open/close?)
  - [ ] Spread width (wider spreads = more slippage?)
  - [ ] Market volatility (VIX level)
  - [ ] Order type (market vs limit)

#### Implementation
- [ ] Create `src/quant_vibe/analytics/slippage_analyzer.py`
- [ ] Log expected fill from backtest vs actual fill
- [ ] Calculate average slippage per strategy
- [ ] Adjust backtest engine with realistic slippage assumptions

#### Backtest Adjustment
- [ ] Update `OptionsBacktestEngine` with slippage parameter
- [ ] Use measured slippage from paper trading
- [ ] Re-run backtests with realistic fills

**Success Criteria**: Backtests model realistic fills within 10% of actual

---

## 🛠️ INFRASTRUCTURE (Week 3-4)

### [ ] 8. Implement RAG System for Development
**Priority**: LOW  
**Estimated Time**: 2 hours  
**Files**: `tools/claude_rag.py`, `.env`

#### Setup
- [ ] Install dependencies: `pip install anthropic python-dotenv`
- [ ] Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-...`
- [ ] Create `tools/claude_rag.py` with ClaudeCodeRAG class
- [ ] Test with simple query: "Show me the current spread entry logic"

#### Benefits
- [ ] 90% cheaper token costs with prompt caching
- [ ] Full codebase context for complex changes
- [ ] Faster iteration on strategy development
- [ ] Better debugging with full context

#### Usage Examples
```bash
# In Claude Code session
python tools/claude_rag.py --query "Add logging to all entry decisions"
python tools/claude_rag.py --query "Modify stop loss to use 2x ATR"
```

**Success Criteria**: RAG system reduces development time for complex changes by 30%+

---

### [ ] 9. Volatility-Based Position Sizing
**Priority**: MEDIUM  
**Estimated Time**: 3 hours  
**Files**: `src/quant_vibe/risk/volatility_position_sizer.py`

#### Implementation
- [ ] Create `src/quant_vibe/risk/volatility_position_sizer.py`:
```python
class VolatilityPositionSizer:
    def __init__(self, risk_per_trade_pct: float = 0.01):
        """
        Size positions based on ATR(20) to maintain consistent $ risk.
        
        Args:
            risk_per_trade_pct: Max % of account to risk per trade (default 1%)
        """
        self.risk_pct = risk_per_trade_pct
    
    def calculate_size(
        self,
        account_value: float,
        atr_value: float,
        spread_width: float,
        max_loss_per_spread: float
    ) -> int:
        """
        Calculate number of spreads based on volatility.
        
        Higher ATR = smaller position size
        Lower ATR = larger position size
        
        Returns:
            Number of spreads (minimum 1)
        """
        max_loss_per_trade = account_value * self.risk_pct
        contracts = max_loss_per_trade / max_loss_per_spread
        return max(1, int(contracts))
```

#### Integration
- [ ] Add to `OptionsStrategy` base class
- [ ] Calculate ATR(20) in `analyze_market()`
- [ ] Call position sizer before `construct_spread()`
- [ ] Update `num_spreads` dynamically based on volatility

#### Testing
- [ ] Backtest with fixed size vs volatility-based size
- [ ] Compare risk-adjusted returns (Sharpe ratio)
- [ ] Verify position sizes scale appropriately

**Success Criteria**: Volatility-based sizing improves Sharpe ratio by >10%

---

### [ ] 10. Database Optimization
**Priority**: LOW  
**Estimated Time**: 2 hours  
**Files**: `scripts/optimize_timescale.sql`

#### Performance Audit
- [ ] Check compression status:
```sql
SELECT * FROM timescaledb_information.compressed_chunks;
```

- [ ] Check continuous aggregates:
```sql
SELECT * FROM timescaledb_information.continuous_aggregates;
```

- [ ] Check slow queries:
```sql
SELECT * FROM pg_stat_statements 
ORDER BY total_time DESC 
LIMIT 20;
```

#### Optimizations
- [ ] Add missing indexes:
```sql
CREATE INDEX idx_options_bars_strike_expiry 
ON options_bars (strike_price, expiration_date, timestamp DESC);

CREATE INDEX idx_options_bars_underlying_time
ON options_bars (underlying_ticker, timestamp DESC);
```

- [ ] Run ANALYZE on large tables:
```sql
ANALYZE options_bars;
ANALYZE underlying_bars;
```

- [ ] Verify compression policy (compress after 7 days)
- [ ] Check continuous aggregate refresh policy

**Success Criteria**: Query times <1 second for typical backtest data loads

---

## 🚀 PRODUCTION READINESS (Week 4)

### [ ] 11. Emergency Stop Procedures
**Priority**: CRITICAL  
**Estimated Time**: 3 hours  
**Files**: `docs/EMERGENCY_PROCEDURES.md`, `scripts/emergency_stop.py`

#### Documentation
- [ ] Create `docs/EMERGENCY_PROCEDURES.md`:
  - [ ] How to manually close all positions (Admin UI steps)
  - [ ] How to manually close via Schwab web interface
  - [ ] How to disable all strategies instantly
  - [ ] Emergency contact numbers (broker, support)
  - [ ] Maximum acceptable loss before manual intervention ($16,000 = 2%)
  - [ ] What to do if server crashes during market hours
  - [ ] Backup server failover procedures (if applicable)

#### Emergency Stop Script
- [ ] Create `scripts/emergency_stop.py`:
```python
#!/usr/bin/env python3
"""
Emergency stop script - closes all positions and disables trading.

Usage:
    python scripts/emergency_stop.py --confirm

This script:
1. Closes all active positions at market price
2. Disables all strategies in live_trading.yaml
3. Stops the live_trading service
4. Sends Pushover alert confirming shutdown
"""
```

- [ ] Add confirmation prompt (prevent accidental execution)
- [ ] Close all positions via Schwab API
- [ ] Disable strategies in config
- [ ] Stop live_trading service
- [ ] Send Pushover confirmation
- [ ] Log all actions with timestamps

#### Testing
- [ ] Test in paper trading mode
- [ ] Verify all positions close correctly
- [ ] Verify strategies disable
- [ ] Verify service stops
- [ ] Time the full process (should be <30 seconds)

#### Quick Access
- [ ] Add "EMERGENCY STOP" button to Admin UI
- [ ] Add confirmation dialog ("Are you sure?")
- [ ] Make script executable: `chmod +x scripts/emergency_stop.py`
- [ ] Add alias to shell: `alias stop-trading='python scripts/emergency_stop.py'`

**Success Criteria**: Can stop all trading and close positions in <30 seconds

---

### [ ] 12. Auto-Disable on Drawdown Limit
**Priority**: CRITICAL  
**Estimated Time**: 2 hours  
**Files**: `src/live_trading_service/risk_manager.py`

#### Implementation
- [ ] Create `src/live_trading_service/risk_manager.py`:
```python
class RiskManager:
    def __init__(self, max_daily_drawdown_pct: float = 0.02):
        """
        Monitor risk limits and auto-disable trading if breached.
        
        Args:
            max_daily_drawdown_pct: Max daily loss (default 2% = $16,000 on $800K)
        """
        self.max_drawdown = max_daily_drawdown_pct
        self.daily_start_value = None
        self.daily_low_value = None
    
    def check_drawdown(self, current_portfolio_value: float) -> bool:
        """
        Check if daily drawdown limit exceeded.
        
        Returns:
            True if limit breached (should disable trading)
        """
        if self.daily_start_value is None:
            self.daily_start_value = current_portfolio_value
            self.daily_low_value = current_portfolio_value
            return False
        
        self.daily_low_value = min(self.daily_low_value, current_portfolio_value)
        drawdown = (self.daily_start_value - self.daily_low_value) / self.daily_start_value
        
        if drawdown >= self.max_drawdown:
            return True
        return False
    
    def reset_daily(self):
        """Reset daily tracking at market open."""
        self.daily_start_value = None
        self.daily_low_value = None
```

#### Integration
- [ ] Add RiskManager to LiveTradingEngine
- [ ] Check after every position update
- [ ] If limit breached:
  - [ ] Close all positions immediately
  - [ ] Disable all strategies
  - [ ] Send emergency Pushover alert (priority=2)
  - [ ] Log detailed event
  - [ ] Prevent new trades for rest of day

#### Testing
- [ ] Test with simulated loss in paper trading
- [ ] Verify triggers at exactly 2% drawdown
- [ ] Verify positions close correctly
- [ ] Verify strategies disable
- [ ] Verify alert sent

**Success Criteria**: System automatically stops trading at 2% daily drawdown

---

### [ ] 13. Logging & Monitoring Improvements
**Priority**: MEDIUM  
**Estimated Time**: 3 hours  
**Files**: `src/quant_vibe/config/logging_config.py`, `src/watcher_service/alerts.py`

#### Enhanced Logging
- [ ] Add structured logging with context:
```python
logger.info(
    "Trade filled",
    extra={
        "strategy": "bullish_vertical_put",
        "spread": "5900/5890 put",
        "fill_price": 1.20,
        "credit": 120.0,
        "timestamp": datetime.now(tz=timezone.utc)
    }
)
```

- [ ] Log all decision points:
  - [ ] Why entry triggered
  - [ ] Why entry not triggered (when signals present)
  - [ ] Why exit triggered
  - [ ] Parameter values at decision time

#### Watcher Service Alerts
- [ ] Alert on service restarts (unexpected)
- [ ] Alert on API errors (>3 in 5 minutes)
- [ ] Alert on missing data (bars not arriving)
- [ ] Alert on system resource usage (CPU >80%, memory >90%)

#### Log Analysis Dashboard
- [ ] Add log viewer to Admin UI
- [ ] Filter by level (ERROR, WARNING, INFO)
- [ ] Filter by service (streaming, live_trading, watcher)
- [ ] Search by keyword
- [ ] Download logs for analysis

**Success Criteria**: All critical events logged with full context, searchable via Admin UI

---

### [ ] 14. Tax Reporting Preparation
**Priority**: LOW  
**Estimated Time**: 2 hours  
**Files**: `src/quant_vibe/reporting/tax_report.py`

#### Implementation
- [ ] Create `src/quant_vibe/reporting/tax_report.py`:
```python
class Section1256Report:
    """
    Generate tax reports for Section 1256 contracts (SPX options).
    
    SPX options get 60/40 tax treatment:
    - 60% taxed as long-term capital gains
    - 40% taxed as short-term capital gains
    """
    
    def generate_annual_report(self, trades_df: pd.DataFrame, year: int) -> dict:
        """
        Generate annual Section 1256 report.
        
        Returns:
            dict with:
            - total_pnl: float
            - long_term_portion: float (60%)
            - short_term_portion: float (40%)
            - trade_count: int
            - by_month: dict (monthly breakdown)
        """
        pass
    
    def mark_to_market_positions(self, open_positions: list, year_end_date: datetime) -> float:
        """
        Calculate mark-to-market P&L for open positions at year-end.
        (Required for Section 1256)
        """
        pass
```

#### Features
- [ ] Total gains/losses for year
- [ ] 60/40 split calculation
- [ ] Trade-by-trade detail (for accountant)
- [ ] Open position mark-to-market at Dec 31
- [ ] Monthly breakdown
- [ ] Export to CSV for accountant

#### Automation
- [ ] Generate on Dec 31 at 4:05 PM ET
- [ ] Send via Pushover with summary
- [ ] Save to `reports/tax/YYYY_section_1256_report.csv`

**Success Criteria**: Complete tax report generated automatically at year-end

---

## 📈 ADVANCED FEATURES (After 1+ Month Live Trading)

### [ ] 15. Multi-Strategy Portfolio Optimization
**Priority**: LOW  
**Estimated Time**: 4 hours  
**Files**: `src/quant_vibe/optimization/portfolio_optimizer.py`

#### Implementation
- [ ] Create `src/quant_vibe/optimization/portfolio_optimizer.py`
- [ ] Calculate correlation between strategies
- [ ] Optimize capital allocation for maximum Sharpe ratio
- [ ] Ensure diversification (no single strategy >50% allocation)

#### Example Allocation
```python
# Based on backtest results
allocations = {
    'bullish_vertical_put': 0.40,   # Sharpe: 1.8, correlation: 0.3
    'bullish_vertical_call': 0.35,  # Sharpe: 1.6, correlation: 0.5
    'bearish_iv_scalp': 0.25,       # Sharpe: 2.1, correlation: -0.2
}
```

**Success Criteria**: Portfolio Sharpe ratio >2.0 (better than any individual strategy)

---

### [ ] 16. Machine Learning Entry Timing
**Priority**: LOW  
**Estimated Time**: 8 hours  
**Files**: `src/quant_vibe/ml/entry_predictor.py`

#### Features to Engineer
- [ ] ATR percentile (current vs 30-day range)
- [ ] IV percentile (current vs 30-day range)
- [ ] Time of day (avoid first/last 30 minutes)
- [ ] VIX level
- [ ] Day of week (avoid Monday opens)
- [ ] Days to expiration
- [ ] Distance from ATM

#### Model Training
- [ ] Use Random Forest Classifier
- [ ] Target: Probability trade will profit
- [ ] Train on: Last 6 months of trades
- [ ] Test on: Last 1 month (out-of-sample)
- [ ] Threshold: Only enter if prob >0.65

#### Integration
- [ ] Add to `should_enter()` method
- [ ] Backtest with ML filter vs without
- [ ] Compare win rate improvement

**Success Criteria**: ML filter improves win rate by >5% on out-of-sample data

---

### [ ] 17. Remote Access via Dynamic DNS
**Priority**: LOW  
**Estimated Time**: 1 hour  
**Files**: `.env`, `docker-compose.yml`

#### Setup
- [ ] Verify Sonic.net DynDNS credentials in `.env`
- [ ] Start dyndns service: `docker-compose up -d dyndns`
- [ ] Configure port forwarding on router:
  - [ ] External port 443 → Internal port 80 (Admin UI)
  - [ ] External port 8000 → Internal port 8000 (API)
- [ ] Set up SSL certificate (Let's Encrypt)
- [ ] Test access from external network

#### Security
- [ ] Require VPN for external access (recommended)
- [ ] Rate limit API endpoints
- [ ] Monitor failed login attempts
- [ ] Use strong passwords (already enforced)

**Success Criteria**: Can monitor trading from anywhere via https://your-hostname.sonic.net

---

## 📊 SUCCESS METRICS

### Daily Tracking (via Daily Report)
- [ ] P&L vs $1,780 target
  - [ ] Target: ≥$1,780/day ($355k/year)
  - [ ] Current: $___ (track in spreadsheet)
  
- [ ] Win Rate
  - [ ] Target: ≥60%
  - [ ] Current: ___% (update daily)
  
- [ ] Max Drawdown
  - [ ] Limit: ≤2% ($16,000 on $800K)
  - [ ] Current: ___% (update daily)
  
- [ ] Slippage
  - [ ] Target: <10% difference vs backtest
  - [ ] Current: ___% (update weekly)

### Weekly Tracking
- [ ] Sharpe Ratio
  - [ ] Target: ≥1.5
  - [ ] Current: ___ (calculate weekly)
  
- [ ] Strategy Performance Comparison
  - [ ] Which strategies outperform?
  - [ ] Which underperform?
  - [ ] Adjust allocations accordingly
  
- [ ] Error Rate
  - [ ] Target: <1% of orders
  - [ ] Failed orders: ___
  - [ ] API errors: ___

### Monthly Tracking
- [ ] Total Return vs S&P 500
  - [ ] Target: Beat SPX by 2x
  - [ ] Current: ___% vs SPX ___% (update monthly)
  
- [ ] Drawdown Recovery Time
  - [ ] Target: <5 days from any drawdown
  - [ ] Longest: ___ days (track monthly)
  
- [ ] Parameter Drift
  - [ ] Do backtested params still work?
  - [ ] Re-optimize if Sharpe drops >20%

---

## 🎯 4-WEEK ROADMAP TO LIVE TRADING

### Week 1: Validation & Monitoring
- [x] Enable paper trading (bullish_vertical_put only)
- [ ] Implement Pushover notifications
- [ ] Create daily performance reports
- [ ] Track slippage vs backtest
- **Goal**: Validate strategy works in real market

### Week 2: Optimization & Analysis
- [ ] Fix or disable bearish_iv_scalp
- [ ] Run parameter optimization
- [ ] Run walk-forward analysis
- [ ] Analyze slippage patterns
- **Goal**: Ensure strategies are robust and optimized

### Week 3: Infrastructure & Risk
- [ ] Implement volatility-based position sizing
- [ ] Set up auto-disable on drawdown
- [ ] Create emergency stop procedures
- [ ] Optimize database performance
- **Goal**: Build robust risk management and infrastructure

### Week 4: Production Readiness
- [ ] Test emergency stop script
- [ ] Test auto-disable on drawdown
- [ ] Document all procedures
- [ ] Final checklist review
- [ ] Enable live trading with 1 contract per strategy
- **Goal**: Go live with minimal risk, scale gradually

### Post-Week 4: Scale & Enhance
- [ ] Monitor live trading 1-2 weeks at 1 contract
- [ ] Scale to 5 contracts if performance matches backtest
- [ ] Scale to 10 contracts after 1 month
- [ ] Add advanced features (portfolio optimization, ML)
- **Goal**: Scale to full $800K capital allocation

---

## 📝 NOTES FOR CLAUDE CODE

### Project Context
- **Goal**: Generate $1,780/day from $800K using SPX options spreads
- **Risk Limits**: 1-2% max daily drawdown ($16,000)
- **Trading Style**: Systematic, rule-based, 0-2 DTE options
- **Tech Stack**: Python, TimescaleDB, Redis, Docker, Schwab API

### Current State
- ✅ Backtesting framework complete
- ✅ Three strategies implemented (bullish put/call, bearish IV scalp)
- ✅ Admin UI for monitoring
- ✅ Docker orchestration
- ⚠️ Paper trading not yet validated (start here)
- ⚠️ No live trading yet (need 2+ weeks paper trading first)

### Key Files to Know
- `config/live_trading.yaml` - Live trading configuration
- `config/backtest.yaml` - Backtest configuration
- `src/quant_vibe/strategies/` - All strategies
- `src/live_trading_service/engine.py` - Live trading engine
- `src/quant_vibe/backtesting/options_engine.py` - Backtest engine
- `docs/HOWTO_NEW_STRATEGY.md` - Guide for adding strategies

### Development Workflow
1. **Always start with backtesting** - Validate logic before live
2. **Paper trade 2+ weeks minimum** - Never skip this
3. **Start with 1 contract** - Scale up slowly
4. **Monitor daily** - Review performance every day
5. **Document everything** - Future you will thank you

### Safety Reminders
- ⚠️ NEVER enable live trading without paper trading validation
- ⚠️ ALWAYS test emergency stop procedures
- ⚠️ ALWAYS monitor daily drawdown
- ⚠️ START SMALL - 1 contract, then scale
- ⚠️ $800K is REAL MONEY - be conservative

### When in Doubt
- Check `CLAUDE.md` for architecture details
- Check `docs/HOWTO_NEW_STRATEGY.md` for strategy development
- Check `docs/TROUBLESHOOTING.md` for common issues
- Search past chats for context (available in claude.ai)

---

## 🚀 READY TO START?

**Recommended First Tasks** (in order):
1. [ ] Enable paper trading (15 min)
2. [ ] Implement Pushover notifications (2 hours)
3. [ ] Create daily performance reports (3 hours)
4. [ ] Monitor paper trading for 2 weeks
5. [ ] Fix or disable bearish_iv_scalp (varies)

**Questions? Blockers?**
- Document in `docs/QUESTIONS.md`
- Search past chats in claude.ai
- Review architecture in `CLAUDE.md`

**Let's build this systematically and safely. Good luck!** 🎯