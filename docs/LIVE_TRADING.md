# How Live Trading Works in Quant-Vibe

## Architecture Overview

The live trading system is a real-time options trading engine that executes strategies on live market data from Schwab. It's built with a **modular architecture** consisting of 7 core components:

```
┌─────────────────────────────────────────────────────────────┐
│                    LiveTradingEngine                        │
│                   (Main Orchestrator)                       │
└────────────┬────────────────────────────────────────────────┘
             │
     ┌───────┴───────┬──────────┬──────────┬──────────┬────────┐
     │               │          │          │          │        │
┌────▼────┐  ┌──────▼─────┐  ┌─▼─────┐  ┌─▼────┐  ┌─▼──────┐ │
│ Data    │  │ Strategy   │  │Order  │  │Pos.  │  │State   │ │
│ Feed    │  │ Executor   │  │Mgr    │  │Mgr   │  │Store   │ │
└─────────┘  └────────────┘  └───────┘  └──────┘  └────────┘ │
     ↑                                                          │
     │                                                          │
┌────┴──────────┐                                             │
│ Schwab Stream │                                             │
│ (schwabdev)   │◄────────────────────────────────────────────┘
└───────────────┘
```

## Core Components

### 1. **LiveTradingEngine** (`engine.py`)
The main orchestrator that coordinates all components.

**Responsibilities:**
- Initialize all components
- Load configuration from `config/live_trading.yaml`
- Manage engine lifecycle (start/stop/shutdown)
- Handle market hours (auto-start at 9:29 AM, stop at 4:00 PM ET)
- Monitor system health
- Persist engine state

**Key Features:**
- **Paper Trading Mode** - Test strategies without real money (enabled by default)
- **Signal Handling** - Graceful shutdown on CTRL+C
- **State Recovery** - Resume from crashes
- **Health Checks** - Monitor data staleness, position limits

### 2. **RealtimeDataFeed** (`data_feed.py`)
Consumes live streaming data from Schwab and maintains a sliding window of recent bars.

**Data Flow:**
```
Schwab Stream → handle_message() → aggregate quotes → create 1-min bars → notify callbacks
```

**How it works:**
1. **Receive Stream Messages** - Schwab sends LEVELONE_OPTIONS messages via websocket
2. **Buffer Quotes** - Collect quotes for each symbol in a buffer
3. **Aggregate into Bars** - Every 60 seconds, aggregate quotes into OHLCV bars
4. **Maintain Window** - Keep last 100 bars in memory (configurable)
5. **Notify Strategies** - Call registered callbacks with new bars

**Data Structure:**
```python
bars = {
    'SPXW251226C06875000': deque([bar1, bar2, ..., bar100], maxlen=100),
    'SPXW251226P06850000': deque([bar1, bar2, ..., bar100], maxlen=100),
    ...
}
```

### 3. **StrategyExecutor** (`strategy_executor.py`)
Executes trading strategies on live data.

**Execution Loop:**
```python
def on_bar(underlying_data, options_data, current_time):
    # 1. Check if we're in trading hours
    if not is_market_open(current_time):
        return

    # 2. Daily reset (start of new trading day)
    if new_trading_day:
        reset_daily_stats()

    # 3. Execute each strategy
    for strategy in strategies:
        # Check entry signals
        if strategy.should_enter(...):
            position = strategy.construct_spread(...)
            submit_orders_for_position(position)

        # Check exit signals for active positions
        if strategy.has_active_position:
            if strategy.should_exit(...):
                close_position(strategy.active_position)
```

**Strategy Lifecycle:**
1. **Analyze Market** - Strategy analyzes current market conditions
2. **Entry Signal** - Check if entry conditions are met
3. **Construct Position** - Build multi-leg options spread
4. **Submit Orders** - Send orders to broker (or simulate in paper mode)
5. **Monitor Position** - Track P&L, check exit conditions
6. **Exit Signal** - Close position when conditions met

### 4. **OrderManager** (`order_manager.py`)
Manages order submission, tracking, and execution.

**Order Types:**
- **Market Orders** - Execute immediately at market price
- **Limit Orders** - Execute only at specified price or better
- **OCO Orders** - One-Cancels-Other (profit target + stop loss)

**Order Lifecycle:**
```
PENDING → SUBMITTED → FILLED (or REJECTED/CANCELLED)
```

**How it works:**
```python
# 1. Create order
order = Order(
    symbol="SPXW251226C06875000",
    quantity=1,
    side=OrderSide.BUY,
    order_type="MARKET",
    position_id="pos_123"
)

# 2. Submit order
if paper_trading:
    simulate_fill(order)  # Instant fill in paper mode
else:
    schwab_client.place_order(order)  # Real broker API

# 3. Track order status
order_manager.update_order_status(order_id, OrderStatus.FILLED)
```

### 5. **PositionManager** (`position_manager.py`)
Tracks all open positions and calculates P&L.

**Position Tracking:**
```python
positions = {
    'pos_123': OptionsPosition(
        position_id='pos_123',
        legs=[
            OptionLeg(symbol='SPXW251226C06875000', quantity=1, ...),   # Long call
            OptionLeg(symbol='SPXW251226C06900000', quantity=-1, ...),  # Short call
        ],
        entry_price=2.50,
        current_price=3.00,
        pnl=50.00,  # (3.00 - 2.50) * 100 per contract
    )
}
```

**P&L Calculation:**
```python
def update_position_value(position, current_options_data):
    total_value = 0.0

    for leg in position.legs:
        # Get current bid/ask for this leg
        current_price = get_mark_price(leg.symbol, current_options_data)

        # Calculate leg value
        leg_value = current_price * leg.quantity * 100  # Options multiplier
        total_value += leg_value

    # Calculate P&L
    position.current_value = total_value
    position.pnl = total_value - position.entry_cost
```

### 6. **StateStore** (`state_store.py`)
Persists state to disk for crash recovery.

**What's Stored:**
- **Engine State** - Current state (RUNNING, STOPPED, etc.)
- **Open Positions** - All active positions and their details
- **Orders** - All orders (pending, filled, cancelled)
- **Daily Stats** - P&L, win/loss counts, drawdown
- **Events Log** - Timestamped event history

**Storage Format:**
```
state/
├── engine_state.json       # Current engine state
├── positions.json          # Open positions
├── orders.json             # Order history
├── daily_stats.json        # Performance metrics
└── events.log              # Event log
```

### 7. **StrategyLoader** (`strategy_loader.py`)
Loads strategies from configuration.

**Config Format:**
```yaml
strategies:
  enabled:
    - name: bullish_vertical_call
      module: quant_vibe.strategies.bullish_vertical_call
      class: BullishVerticalCallStrategy
      params:
        spread_width: 25
        profit_target_pct: 0.50
        stop_loss_pct: 0.30
        min_dte: 0
        max_dte: 2
```

## Complete Data Flow

### Startup Sequence

```
1. Load Configuration
   ├── engine.yaml (paper trading, limits, etc.)
   ├── strategies.yaml (which strategies to run)
   └── risk.yaml (risk limits)

2. Initialize Components
   ├── StateStore → Load previous state (if resuming)
   ├── Schwab Client → Connect to broker API
   ├── OrderManager → Initialize order tracking
   ├── PositionManager → Load open positions
   └── StrategyExecutor → Load and initialize strategies

3. Connect Data Feed
   ├── Create schwabdev Stream client
   ├── Get list of contracts to stream (based on DTE/strike filters)
   └── Subscribe to LEVELONE_OPTIONS for each contract

4. Start Main Loop
   ├── Wait for market open (9:30 AM ET)
   ├── Start streaming
   └── Process data in real-time
```

### Real-Time Execution Loop

```
[Every 60 seconds when new bar is created]

1. Data Feed → Flush quote buffer
   ├── Aggregate quotes into OHLCV bar
   ├── Add bar to sliding window
   └── Call callbacks with new data

2. Strategy Executor → on_bar() triggered
   ├── Check market hours
   ├── Daily reset (if new trading day)
   └── For each strategy:
       ├── Analyze market (calculate indicators, etc.)
       ├── Check entry conditions
       │   ├── If signal → construct_spread()
       │   └── Submit orders via OrderManager
       └── Check exit conditions for active positions
           ├── Update position value
           ├── Check profit target / stop loss
           └── If exit → close position

3. Order Manager → Process orders
   ├── Submit new orders (paper or live)
   ├── Track order status
   └── Notify PositionManager on fills

4. Position Manager → Update positions
   ├── Add new positions from filled orders
   ├── Update P&L for all positions
   └── Remove closed positions

5. State Store → Persist state
   ├── Save positions
   ├── Save orders
   └── Log events
```

## Configuration

### Engine Configuration (`config/live_trading.yaml`)

```yaml
engine:
  paper_trading: true              # IMPORTANT: Start with paper trading!
  max_positions: 5                 # Max concurrent positions
  max_capital_per_trade: 10000     # Max $ per trade
  daily_loss_limit_pct: 0.05       # Stop trading if down 5% for day

data_feed:
  window_size: 100                 # Keep last 100 bars in memory
  aggregate_interval_seconds: 60   # 1-minute bars
  max_dte: 45                      # Max days to expiration to stream
  min_dte: 0                       # Min days to expiration
  strike_range_pct: 0.10           # Stream strikes within ±10% of ATM

risk:
  max_total_exposure: 100000       # Max total portfolio exposure
  max_drawdown_pct: 0.10           # Stop if drawdown > 10%
  position_concentration_limit: 0.30  # Max 30% in one position

monitoring:
  status_update_interval_seconds: 60    # Log status every minute
  health_check_interval_seconds: 30     # Check health every 30s

logging:
  log_dir: logs/live_trading
  log_level: INFO
```

## Safety Features

### 1. **Paper Trading Mode**
- Enabled by default
- Simulates order fills instantly
- No real money at risk
- Full strategy testing capability

### 2. **Risk Limits**
- Maximum positions
- Maximum capital per trade
- Daily loss limits
- Drawdown limits
- Position concentration limits

### 3. **State Persistence**
- Auto-save state every minute
- Crash recovery
- Resume from last state
- Full audit trail

### 4. **Health Monitoring**
- Data staleness checks
- Position limit checks
- Connection monitoring
- Automatic alerts

### 5. **Graceful Shutdown**
- CTRL+C handling
- Close all positions (optional)
- Save final state
- Clean disconnection

## Usage Example

```bash
# 1. Start in paper trading mode
python -m quant_vibe.live.engine

# Or use a script
python scripts/run_live_trading.py

# The engine will:
# - Load configuration
# - Initialize all components
# - Wait for market open (9:30 AM ET)
# - Start streaming data
# - Execute strategies on each new bar
# - Log all activity
# - Stop at market close (4:00 PM ET)
```

## Key Files

- **Main Engine:** `src/quant_vibe/live/engine.py`
- **Data Feed:** `src/quant_vibe/live/data_feed.py`
- **Strategy Executor:** `src/quant_vibe/live/strategy_executor.py`
- **Order Manager:** `src/quant_vibe/live/order_manager.py`
- **Position Manager:** `src/quant_vibe/live/position_manager.py`
- **State Store:** `src/quant_vibe/live/state_store.py`
- **Utilities:** `src/quant_vibe/live/utils.py`

## Related Documentation

- [CLAUDE.md](../CLAUDE.md) - Project overview and development guide
- [Symbol Normalization](SYMBOL_NORMALIZATION.md) - How option symbols are normalized
- [SPXW Quick Reference](QUICKREF_SPXW.md) - SPXW contract details

This architecture provides a robust, safe, and extensible live trading system for options strategies!
