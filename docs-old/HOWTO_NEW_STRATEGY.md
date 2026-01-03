# HOWTO: Add and Enable a New Trading Strategy

This guide walks you through creating, testing, and deploying a new trading strategy in the quant-vibe system.

## Table of Contents

1. [Overview](#overview)
2. [Step 1: Create Strategy Class](#step-1-create-strategy-class)
3. [Step 2: Add Unit Tests](#step-2-add-unit-tests)
4. [Step 3: Register Strategy](#step-3-register-strategy)
5. [Step 4: Configure for Backtesting](#step-4-configure-for-backtesting)
6. [Step 5: Run Backtest](#step-5-run-backtest)
7. [Step 6: Configure for Live Trading](#step-6-configure-for-live-trading)
8. [Step 7: Expose to Admin UI](#step-7-expose-to-admin-ui)
9. [Step 8: Deploy Live](#step-8-deploy-live)
10. [Strategy Templates](#strategy-templates)
11. [Best Practices](#best-practices)

---

## Overview

The quant-vibe system uses a unified strategy interface that works across:
- **Backtesting** - Test strategies on historical data
- **Live Trading** - Execute strategies in real-time (paper or live)

Strategies inherit from base classes:
- `OptionsStrategy` - For multi-leg options strategies
- `Strategy` - For simple stock/ETF strategies (future)

### Workflow Summary

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. Create Strategy Class (src/quant_vibe/strategies/my_strategy.py)│
└─────────────────────┬───────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────────┐
│ 2. Add Unit Tests (tests/unit/test_strategies.py)                  │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────────────┐
│ 3. Register Strategy (src/backtest/engine.py, live/engine.py)      │
└─────────────────────┬───────────────────────────────────────────────┘
                      │
                      ├────────────────────────────────────────────────┐
                      │                                                │
┌─────────────────────▼─────────────┐   ┌────────────────────────────▼┐
│ 4. Configure for Backtesting      │   │ 6. Configure for Live       │
│    (config/backtest.yaml)         │   │    (config/live_trading.yaml│
└─────────────────────┬─────────────┘   └────────────────────────────┬┘
                      │                                                │
┌─────────────────────▼─────────────┐   ┌────────────────────────────▼┐
│ 5. Run Backtest                   │   │ 7. Expose to Admin UI       │
│    - Test on historical data      │   │    (backend/api/strategies) │
│    - Analyze performance          │   └────────────────────────────┬┘
│    - Iterate and optimize         │                                │
└───────────────────────────────────┘   ┌────────────────────────────▼┐
                                        │ 8. Deploy Live              │
                                        │    - Paper trading first    │
                                        │    - Monitor via Admin UI   │
                                        │    - Enable real trading    │
                                        └─────────────────────────────┘
```

### Admin UI Integration

The **Admin UI** provides a web-based interface for strategy management:

- **Strategies Page** (`/strategies`):
  - View all available strategies
  - Enable/disable strategies with one click
  - View and configure strategy parameters
  - Auto-sync with YAML configuration files

- **Live Trading Monitor** (`/live`):
  - Real-time position monitoring
  - Strategy performance tracking
  - Order history and execution logs

- **Config Editor** (`/config`):
  - Edit YAML configuration files
  - Toggle paper trading mode
  - Adjust global risk parameters

- **Services Page** (`/services`):
  - Start/stop/restart trading services
  - View service status and logs
  - Manage Docker containers

**Access:** `http://localhost:5173` (default development)

---

## Step 1: Create Strategy Class

### 1.1 Choose Strategy Type

**Options Strategy** (recommended for SPX/SPXW):
```python
# src/quant_vibe/strategies/my_strategy.py
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

from quant_vibe.strategies.options_base import (
    OptionLeg,
    OptionType,
    OptionsPosition,
    OptionsStrategy,
    SpreadType,
)


class MyStrategy(OptionsStrategy):
    """
    Brief description of your strategy.

    Strategy Logic:
    - Entry conditions
    - Position construction
    - Exit conditions

    Parameters:
    - param1: Description
    - param2: Description
    """

    def __init__(
        self,
        param1: float = 10.0,
        param2: int = 0,
        profit_target: float = 0.50,
        stop_loss: float = 2.0,
        trailing_stop: float | None = None,
        max_dte: int = 45,
        min_dte: int = 0,
    ):
        super().__init__(
            profit_target=profit_target,
            stop_loss=stop_loss,
            trailing_stop=trailing_stop,
            max_dte=max_dte,
            min_dte=min_dte,
        )
        self.param1 = param1
        self.param2 = param2
```

### 1.2 Implement Required Methods

#### analyze_market()
Analyze market conditions and generate entry signals:

```python
    def analyze_market(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
    ) -> dict[str, Any]:
        """
        Analyze market conditions for entry signals.

        Args:
            underlying_data: DataFrame with columns [timestamp, close, ...]
            options_data: DataFrame with options chains
            current_time: Current bar timestamp

        Returns:
            Dict with analysis results (direction, signal, etc.)
        """
        # Get current underlying price
        current_price = underlying_data.loc[
            underlying_data["timestamp"] == current_time, "close"
        ].iloc[0]

        # Add your analysis logic
        # Example: Check if price above moving average
        recent_data = underlying_data[
            underlying_data["timestamp"] <= current_time
        ].tail(20)
        ma_20 = recent_data["close"].mean()

        bullish = current_price > ma_20

        return {
            "current_price": current_price,
            "ma_20": ma_20,
            "direction": "bullish" if bullish else "bearish",
            "signal": bullish,  # Entry signal
        }
```

#### should_enter()
Decide whether to enter a position:

```python
    def should_enter(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        analysis: dict[str, Any],
    ) -> bool:
        """
        Decide whether to enter a new position.

        Args:
            underlying_data: Underlying price data
            options_data: Options chain data
            current_time: Current bar timestamp
            analysis: Results from analyze_market()

        Returns:
            True to enter position
        """
        # Only one position at a time
        if self.active_position is not None:
            return False

        # Check entry signal
        if not analysis.get("signal", False):
            return False

        # Check time constraints (e.g., no entries after 3:00 PM)
        if current_time.hour >= 15:
            return False

        return True
```

#### construct_spread()
Build the multi-leg options position:

```python
    def construct_spread(
        self,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
        analysis: dict[str, Any],
    ) -> OptionsPosition | None:
        """
        Construct the options spread.

        Args:
            underlying_data: Underlying price data
            options_data: Options chain data
            current_time: Current bar timestamp
            analysis: Results from analyze_market()

        Returns:
            OptionsPosition or None if cannot construct
        """
        current_price = analysis["current_price"]

        # Filter options for current timestamp
        current_options = options_data[
            (options_data["timestamp"] == current_time)
            & (options_data["contract_type"] == "call")  # or "put"
        ].copy()

        if current_options.empty:
            return None

        # Calculate DTE
        current_options["dte"] = (
            pd.to_datetime(current_options["expiration_date"]) - current_time
        ).dt.days

        # Filter by DTE
        current_options = current_options[
            (current_options["dte"] >= self.min_dte)
            & (current_options["dte"] <= self.max_dte)
        ]

        if current_options.empty:
            return None

        # Find ATM strike
        current_options["distance_from_atm"] = abs(
            current_options["strike_price"] - current_price
        )
        atm_strike = current_options.loc[
            current_options["distance_from_atm"].idxmin(), "strike_price"
        ]

        # Example: Bullish Vertical Call Spread
        # Buy ATM call
        buy_strike = atm_strike
        buy_contract = current_options[
            current_options["strike_price"] == buy_strike
        ]

        # Sell OTM call (spread_width above)
        sell_strike = buy_strike + self.param1  # spread_width
        sell_contract = current_options[
            current_options["strike_price"] == sell_strike
        ]

        if buy_contract.empty or sell_contract.empty:
            return None

        # Get contract details
        buy_row = buy_contract.iloc[0]
        sell_row = sell_contract.iloc[0]

        # Calculate entry price (mark = mid of bid/ask)
        buy_mark = (buy_row["bid"] + buy_row["ask"]) / 2
        sell_mark = (sell_row["bid"] + sell_row["ask"]) / 2
        spread_cost = buy_mark - sell_mark

        # Create position
        legs = [
            OptionLeg(
                contract_symbol=buy_row["option_ticker"],
                strike_price=buy_row["strike_price"],
                option_type=OptionType.CALL,
                expiration_date=buy_row["expiration_date"],
                quantity=1,  # Long
                entry_price=buy_mark,
                bid=buy_row["bid"],
                ask=buy_row["ask"],
            ),
            OptionLeg(
                contract_symbol=sell_row["option_ticker"],
                strike_price=sell_row["strike_price"],
                option_type=OptionType.CALL,
                expiration_date=sell_row["expiration_date"],
                quantity=-1,  # Short
                entry_price=sell_mark,
                bid=sell_row["bid"],
                ask=sell_row["ask"],
            ),
        ]

        position = OptionsPosition(
            position_id=f"pos_{current_time.strftime('%Y%m%d_%H%M%S')}",
            entry_time=current_time,
            legs=legs,
            spread_type=SpreadType.VERTICAL_CALL,
            spread_cost=spread_cost,
            max_profit=self.param1 - spread_cost,  # spread_width - cost
            max_loss=spread_cost,
        )

        return position
```

#### should_exit()
Check exit conditions:

```python
    def should_exit(
        self,
        position: OptionsPosition,
        underlying_data: pd.DataFrame,
        options_data: pd.DataFrame,
        current_time: datetime,
    ) -> tuple[bool, str | None]:
        """
        Check if position should be exited.

        Args:
            position: Current active position
            underlying_data: Underlying price data
            options_data: Options chain data
            current_time: Current bar timestamp

        Returns:
            (should_exit, exit_reason)
        """
        # Update position value
        self.update_position_value(position, options_data, current_time)

        # Check profit target
        if self.check_profit_target(position):
            return True, "Profit target"

        # Check stop loss
        if position.unrealized_pnl <= -position.spread_cost * self.stop_loss:
            return True, "Stop loss"

        # Check trailing stop
        if self.trailing_stop and self.check_trailing_stop(position):
            return True, "Trailing stop"

        # Check expiration (close 15 min before market close)
        if current_time.hour == 15 and current_time.minute >= 45:
            return True, "End of day"

        return False, None
```

### 1.3 Export Strategy

Add to `src/quant_vibe/strategies/__init__.py`:

```python
from quant_vibe.strategies.my_strategy import MyStrategy

__all__ = [
    # ... existing strategies ...
    "MyStrategy",
]
```

---

## Step 2: Add Unit Tests

Create test file `tests/unit/test_strategies.py` (or add to existing):

```python
import pandas as pd
import pytest
from datetime import datetime, timedelta

from quant_vibe.strategies.my_strategy import MyStrategy


def test_my_strategy_initialization():
    """Test strategy initialization with parameters."""
    strategy = MyStrategy(
        param1=15.0,
        param2=1,
        profit_target=0.60,
        stop_loss=2.5,
    )

    assert strategy.param1 == 15.0
    assert strategy.param2 == 1
    assert strategy.profit_target == 0.60
    assert strategy.stop_loss == 2.5


def test_my_strategy_analyze_market():
    """Test market analysis logic."""
    strategy = MyStrategy()

    # Create sample data
    timestamps = pd.date_range("2025-12-01 09:30", periods=30, freq="1min")
    underlying_data = pd.DataFrame({
        "timestamp": timestamps,
        "close": [5900 + i for i in range(30)],  # Uptrend
    })

    options_data = pd.DataFrame()  # Empty for this test
    current_time = timestamps[25]

    analysis = strategy.analyze_market(
        underlying_data, options_data, current_time
    )

    assert "direction" in analysis
    assert "signal" in analysis
    assert analysis["direction"] in ["bullish", "bearish"]


def test_my_strategy_should_enter():
    """Test entry logic."""
    strategy = MyStrategy()

    # Create sample data
    current_time = datetime(2025, 12, 1, 10, 0)
    underlying_data = pd.DataFrame({
        "timestamp": [current_time],
        "close": [5900.0],
    })

    analysis = {"signal": True, "direction": "bullish"}

    # Should enter when no active position
    assert strategy.should_enter(
        underlying_data, pd.DataFrame(), current_time, analysis
    )


# Add more tests for construct_spread(), should_exit(), etc.
```

Run tests:
```bash
pytest tests/unit/test_strategies.py -v
```

---

## Step 3: Register Strategy

Add your strategy to the strategy registry in `src/backtest/engine.py`:

```python
def _load_strategy(
    self, strategy_name: str, strategy_config: dict[str, Any]
) -> OptionsStrategy:
    """Load and instantiate a strategy by name."""

    # Strategy class mapping
    strategy_map = {
        'bullish_vertical_put': 'quant_vibe.strategies.bullish_vertical_put.BullishVerticalPutStrategy',
        'bullish_vertical_call': 'quant_vibe.strategies.bullish_vertical_call.BullishVerticalCallStrategy',
        'bearish_iv_scalp': 'quant_vibe.strategies.bearish_iv_scalp.BearishIVScalpStrategy',
        'my_strategy': 'quant_vibe.strategies.my_strategy.MyStrategy',  # Add this line
    }

    # ... rest of method
```

---

## Step 4: Configure for Backtesting

Add strategy configuration to `config/backtest.yaml`:

```yaml
strategies:
  enabled:
    # ... existing strategies ...

    - name: my_strategy
      enabled: true  # Set to false to disable
      params:
        param1: 20.0
        param2: 0
        profit_target: 0.50
        stop_loss: 2.0
        trailing_stop: null
        max_dte: 45
        min_dte: 0
```

**Configuration Options:**

- `enabled`: Enable/disable strategy
- `params`: Strategy-specific parameters
  - Include all constructor parameters
  - Use `null` for None values
  - Use snake_case naming

---

## Step 5: Run Backtest

### 5.1 Test Single Strategy

```bash
# Activate environment
source venv/bin/activate

# Run specific strategy
python scripts/run_backtest.py --strategy my_strategy

# Use custom config
python scripts/run_backtest.py --strategy my_strategy --config config/my_test.yaml
```

### 5.2 Run All Enabled Strategies

```bash
# Run all strategies marked enabled: true
python scripts/run_backtest.py
```

### 5.3 Review Results

Output location: `backtest_results/{strategy_name}/`

Files generated:
- `{strategy_name}_log_{timestamp}.txt` - Execution log
- `{strategy_name}_trades_{timestamp}.csv` - Trade details
- `{strategy_name}_equity_{timestamp}.csv` - Equity curve

**Key Metrics to Review:**
- Total Return
- Sharpe Ratio (> 1.0 is good)
- Max Drawdown (< 20% is good)
- Win Rate
- Average Win/Loss
- Profit Factor (> 1.5 is good)

### 5.4 Iterate and Optimize

1. **Analyze losing trades** - Why did they lose?
2. **Test parameter variations** - Adjust profit_target, stop_loss, etc.
3. **Validate entry signals** - Are entries well-timed?
4. **Check exit logic** - Are exits too early/late?
5. **Review edge cases** - Handle missing data, expiration, etc.

---

## Step 6: Configure for Live Trading

Once backtesting shows promising results, configure for live trading.

### 6.1 Add to Live Trading Config

Edit `config/live_trading.yaml`:

```yaml
strategies:
  enabled:
    # ... existing strategies ...

    - name: my_strategy
      enabled: true  # Set to false to disable
      params:
        param1: 20.0
        param2: 0
        profit_target: 0.50
        stop_loss: 2.0
        trailing_stop: null
        max_dte: 45
        min_dte: 0

      # Live trading specific settings
      position_size: 1  # Number of contracts per leg
      max_positions: 1  # Max concurrent positions
      symbols:
        - SPXW
        - SPX
```

### 6.2 Paper Trading First

**IMPORTANT:** Always test in paper trading mode before live:

```yaml
# config/live_trading.yaml
engine:
  paper_trading: true  # Enable paper trading (NO REAL MONEY)
  use_redis_feed: true
```

### 6.3 Register in Live Engine

Add strategy to `src/quant_vibe/live/engine.py` if not using dynamic loading:

```python
# In LiveTradingEngine._load_strategies()
from quant_vibe.strategies.my_strategy import MyStrategy

strategy_classes = {
    'bullish_vertical_put': BullishVerticalPutStrategy,
    'bullish_vertical_call': BullishVerticalCallStrategy,
    'bearish_iv_scalp': BearishIVScalpStrategy,
    'my_strategy': MyStrategy,  # Add this line
}
```

---

## Step 7: Expose to Admin UI

The Admin UI provides a web interface for managing strategies. To expose your new strategy in the UI, you need to update both the backend API and ensure the frontend can display it.

### 7.1 Add Strategy Metadata to Backend

Edit `src/admin_ui/backend/api/strategies.py` and add your strategy to `STRATEGY_METADATA`:

```python
# src/admin_ui/backend/api/strategies.py

STRATEGY_METADATA = {
    "bullish_vertical_put": {
        "description": "Credit spread strategy (sell put, buy lower put) for bullish markets",
        "default_params": { ... },
    },
    "bullish_vertical_call": {
        "description": "Debit spread strategy (buy call, sell higher call) for bullish markets",
        "default_params": { ... },
    },
    "bearish_iv_scalp": {
        "description": "Credit spread strategy (sell call, buy higher call) targeting IV spikes during bearish moves (0DTE scalping)",
        "default_params": { ... },
    },
    # Add your strategy here
    "my_strategy": {
        "description": "Brief description of your strategy for the UI",
        "default_params": {
            "param1": 20.0,
            "param2": 0,
            "profit_target_min": 0.50,
            "profit_target_max": 1.0,
            "trailing_stop_pct": 0.05,
            "stop_loss_pct": 2.0,
            "min_dte": 0,
            "max_dte": 45,
            "spread_width": 20.0,
            "observation_period": 30,
            "num_spreads": 10,
            "max_trades_daily": 1,
            # Add all constructor parameters with their default values
        },
    },
}
```

**Important Notes:**
- **`description`**: Short description shown in the UI (1-2 sentences)
- **`default_params`**: All strategy constructor parameters with default values
  - Must match your strategy's `__init__()` parameters
  - Use snake_case naming
  - Include all parameters (DTE, profit targets, stops, etc.)

### 7.2 Verify Backend API

The backend API automatically exposes your strategy once it's in `STRATEGY_METADATA`:

**Available Endpoints:**
- `GET /api/strategies/list` - List all available strategies
- `GET /api/strategies/{strategy_name}` - Get specific strategy details
- `POST /api/strategies/{strategy_name}/toggle` - Enable/disable strategy
- `PUT /api/strategies/{strategy_name}/params` - Update strategy parameters

### 7.3 Frontend Display (Automatic)

The frontend (`src/admin_ui/frontend/src/pages/StrategiesManager.tsx`) automatically displays all strategies from the backend API. No code changes needed!

The UI provides:
- ✅ Strategy list with enabled/disabled status
- ✅ Enable/disable toggle buttons
- ✅ Expandable parameter views
- ✅ Parameter editing (future enhancement)
- ✅ Restart warnings

### 7.4 Test Admin UI Integration

**Start the Admin UI:**
```bash
# Start backend (FastAPI)
cd src/admin_ui/backend
source ../../../venv/bin/activate
python -m uvicorn admin_ui.backend.main:app --reload --host 0.0.0.0 --port 8000

# Start frontend (React/Vite) - in a new terminal
cd src/admin_ui/frontend
npm install  # First time only
npm run dev
```

**Access the UI:**
1. Open browser: `http://localhost:5173`
2. Login with credentials from `.env` file
3. Navigate to **"Strategies"** page
4. Verify your strategy appears in the list
5. Test enable/disable toggle
6. Expand parameters to verify they display correctly

### 7.5 Verify Strategy Registration

Check that your strategy is properly registered in the live trading engine:

```bash
# Test loading strategies
python -c "
from quant_vibe.live.engine import LiveTradingEngine
from pathlib import Path

# Simulate loading config
config_path = Path('config/live_trading.yaml')
engine = LiveTradingEngine(config_path=str(config_path))

# Check if strategy can be loaded
try:
    # This will be called during engine initialization
    print('Strategy registration successful!')
except Exception as e:
    print(f'Error: {e}')
"
```

### 7.6 Admin UI Workflow

**Typical User Workflow:**
1. **View strategies** - See all available strategies with descriptions
2. **Enable strategy** - Toggle on to add to live trading config
3. **Configure parameters** - Adjust strategy parameters (future: inline editing)
4. **Restart service** - Use Services page to restart `live_trading` service
5. **Monitor execution** - Use Live Trading Monitor to watch strategy performance

**Current Capabilities:**
- ✅ List all strategies
- ✅ Enable/disable strategies
- ✅ View parameters
- ✅ Auto-sync with YAML config

**Future Enhancements:**
- Parameter editing in UI (currently view-only)
- Strategy performance metrics in UI
- Backtest runner integration
- Real-time strategy logs

### 7.7 Docker Deployment

If deploying via Docker, ensure the Admin UI container is updated:

```bash
# Rebuild Admin UI container
docker-compose build admin_ui

# Restart Admin UI services
docker-compose up -d admin_ui

# Check logs
docker-compose logs -f admin_ui
```

The Admin UI container (`quant-vibe-admin-ui`) includes both backend and frontend.

---

## Step 8: Deploy Live

### 8.1 Pre-Deployment Checklist

- [ ] Backtests show positive results over multiple time periods
- [ ] Unit tests pass
- [ ] Strategy handles edge cases (missing data, expiration, etc.)
- [ ] Paper trading tested for at least 1 week
- [ ] Risk parameters validated (stop_loss, position_size)
- [ ] Emergency stop procedures documented
- [ ] Logging and monitoring enabled

### 8.2 Start Paper Trading

**Option A: Via Admin UI (Recommended)**
```bash
# Start Admin UI if not running
docker-compose up -d admin_ui

# Access UI
# 1. Open browser: http://localhost:5173
# 2. Navigate to "Strategies" page
# 3. Enable your strategy
# 4. Navigate to "Services" page
# 5. Restart "live_trading" service
```

**Option B: Via CLI**
```bash
# Start streaming service (if not already running)
docker-compose up -d

# Verify Redis is running
docker ps | grep redis

# Start live trading in paper mode
source venv/bin/activate
python scripts/run_live_trading.py

# Monitor logs
tail -f logs/live_trading/live_trading_*.log
```

### 8.3 Monitor Paper Trading

**Admin UI Monitoring:**
1. Navigate to **Live Trading Monitor** page
2. Watch real-time positions and P&L
3. Check strategy execution logs
4. Review order history

**CLI Monitoring:**

**Key Metrics:**
- Position entry/exit timing
- Actual fill prices vs. expected
- P&L tracking accuracy
- Order execution success rate
- System stability

**Monitor for:**
- Network errors
- API rate limits
- Data feed interruptions
- Unexpected market conditions

### 8.4 Enable Live Trading

**WARNING:** Only after successful paper trading!

**Option A: Via Admin UI (Recommended)**
1. Navigate to **Config Editor** page
2. Select `live_trading.yaml`
3. Set `engine.paper_trading: false`
4. Adjust position sizes conservatively
5. Save configuration
6. Navigate to **Services** page
7. Restart `live_trading` service

**Option B: Via CLI**
```yaml
# config/live_trading.yaml
engine:
  paper_trading: false  # ENABLE REAL TRADING
  use_redis_feed: true
```

**Start with small position sizes:**
```yaml
strategies:
  enabled:
    - name: my_strategy
      position_size: 1  # Start with 1 contract
```

### 8.5 Production Monitoring

Set up monitoring:
- Log aggregation (centralized logging)
- Alerts for errors/failures
- Daily P&L reports
- Position tracking dashboard
- API health checks

---

## Strategy Templates

### Template 1: Vertical Spread (Call or Put)

```python
class MyVerticalStrategy(OptionsStrategy):
    """Vertical spread strategy template."""

    def __init__(self, spread_width: float = 20.0, **kwargs):
        super().__init__(**kwargs)
        self.spread_width = spread_width

    def analyze_market(self, underlying_data, options_data, current_time):
        # Trend analysis
        current_price = underlying_data.loc[
            underlying_data["timestamp"] == current_time, "close"
        ].iloc[0]

        return {
            "current_price": current_price,
            "signal": True,  # Add your signal logic
        }

    def should_enter(self, underlying_data, options_data, current_time, analysis):
        return (
            self.active_position is None
            and analysis["signal"]
            and current_time.hour < 15
        )

    def construct_spread(self, underlying_data, options_data, current_time, analysis):
        # Filter for calls (or puts)
        current_options = options_data[
            (options_data["timestamp"] == current_time)
            & (options_data["contract_type"] == "call")
        ].copy()

        # Find ATM strike
        current_price = analysis["current_price"]
        current_options["distance_from_atm"] = abs(
            current_options["strike_price"] - current_price
        )
        atm_strike = current_options.loc[
            current_options["distance_from_atm"].idxmin(), "strike_price"
        ]

        # Build spread (buy ATM, sell OTM)
        buy_strike = atm_strike
        sell_strike = buy_strike + self.spread_width

        # Get contracts and build legs
        # ... (see full example in construct_spread() above)

    def should_exit(self, position, underlying_data, options_data, current_time):
        self.update_position_value(position, options_data, current_time)

        if self.check_profit_target(position):
            return True, "Profit target"

        if position.unrealized_pnl <= -position.spread_cost * self.stop_loss:
            return True, "Stop loss"

        if current_time.hour == 15 and current_time.minute >= 45:
            return True, "End of day"

        return False, None
```

### Template 2: IV-Based Entry

```python
class IVBasedStrategy(OptionsStrategy):
    """Enter positions based on implied volatility conditions."""

    def __init__(self, iv_threshold: float = 0.15, **kwargs):
        super().__init__(**kwargs)
        self.iv_threshold = iv_threshold

    def analyze_market(self, underlying_data, options_data, current_time):
        # Get ATM IV
        current_price = underlying_data.loc[
            underlying_data["timestamp"] == current_time, "close"
        ].iloc[0]

        current_options = options_data[
            options_data["timestamp"] == current_time
        ].copy()

        if current_options.empty:
            return {"signal": False}

        # Find ATM IV
        current_options["distance_from_atm"] = abs(
            current_options["strike_price"] - current_price
        )
        atm_option = current_options.loc[
            current_options["distance_from_atm"].idxmin()
        ]

        iv = atm_option["implied_volatility"]

        return {
            "current_price": current_price,
            "iv": iv,
            "signal": iv > self.iv_threshold,  # Enter when IV is high
        }

    # ... implement other methods
```

---

## Best Practices

### Code Quality

1. **Type hints** - Use type annotations for all parameters and returns
2. **Docstrings** - Document all methods with Args/Returns
3. **Error handling** - Handle missing data, empty DataFrames gracefully
4. **Logging** - Use `self.logger` for debugging (inherited from base class)
5. **Constants** - Define magic numbers as class attributes

### Strategy Design

1. **Start simple** - Test basic logic before adding complexity
2. **One strategy, one edge** - Don't mix multiple concepts
3. **Realistic assumptions** - Model slippage, commissions, bid/ask spreads
4. **Risk management** - Always have stop losses and position limits
5. **Market hours** - Respect market open/close, avoid edge times

### Testing

1. **Unit tests first** - Test components in isolation
2. **Multiple time periods** - Backtest across different market conditions
3. **Out-of-sample testing** - Test on data not used for development
4. **Paper trading** - Always paper trade before live
5. **Edge cases** - Test missing data, expiration, extreme moves

### Risk Management

1. **Position sizing** - Start small, scale up gradually
2. **Stop losses** - Always define maximum loss per trade
3. **Diversification** - Don't put all capital in one strategy
4. **Monitoring** - Set up alerts and daily reviews
5. **Emergency procedures** - Know how to manually close positions

### Production Deployment

1. **Version control** - Tag releases, track changes
2. **Configuration management** - Use YAML configs, not hardcoded values
3. **Logging** - Comprehensive logging for debugging
4. **Monitoring** - Track performance, errors, API health
5. **Rollback plan** - Be ready to disable strategy quickly

---

## Troubleshooting

### Strategy Not Running

**Check:**
- Is strategy `enabled: true` in config?
- Is strategy registered in `engine.py`?
- Are there any import errors? Check logs
- Is Redis running for live trading?

### No Trades Generated

**Check:**
- Is market data available for the time period?
- Are entry conditions too strict?
- Is `should_enter()` returning True?
- Are options available at desired strikes/expirations?

### Backtest Crashes

**Check:**
- Are DataFrame columns correct? (timestamp, close, bid, ask, etc.)
- Are there any NaN values in critical columns?
- Is data sorted by timestamp?
- Are option chains empty for some timestamps?

### Poor Performance

**Check:**
- Are bid/ask spreads too wide?
- Are stop losses too tight?
- Is profit target realistic?
- Are entries timed correctly?
- Is there overfitting to backtest data?

---

## Next Steps

1. **Read existing strategies** - Study `bullish_vertical_put.py`, `bearish_iv_scalp.py`
2. **Review backtest results** - Analyze winning strategies
3. **Join community** - Share strategies, get feedback
4. **Iterate and improve** - Trading is a continuous learning process

---

## Quick Reference: Files to Modify

When adding a new strategy, you'll need to modify these files:

| File | Purpose | Required? |
|------|---------|-----------|
| `src/quant_vibe/strategies/my_strategy.py` | Strategy implementation | ✅ Yes |
| `src/quant_vibe/strategies/__init__.py` | Export strategy class | ✅ Yes |
| `src/backtest/engine.py` | Register for backtesting | ✅ Yes |
| `src/quant_vibe/live/engine.py` | Register for live trading | ✅ Yes |
| `src/admin_ui/backend/api/strategies.py` | Add to Admin UI | ✅ Yes |
| `config/backtest.yaml` | Backtest configuration | ✅ Yes |
| `config/live_trading.yaml` | Live trading config | ✅ Yes |
| `tests/unit/test_strategies.py` | Unit tests | ✅ Recommended |

---

## References

- **Architecture**: `CLAUDE.md`
- **Backtesting utilities**: `CLAUDE.md` → "Backtest Utilities"
- **Options data**: `docs/TIMESCALE_SETUP.md`
- **Live trading config**: `config/live_trading.yaml`
- **Backtest config**: `config/backtest.yaml`
- **Testing**: `tests/unit/test_strategies.py`
- **Admin UI API**: `src/admin_ui/backend/api/strategies.py`
- **Admin UI Frontend**: `src/admin_ui/frontend/src/pages/StrategiesManager.tsx`

---

## Summary: 5-Minute Checklist

**Quick checklist for experienced developers:**

- [ ] 1. Create `src/quant_vibe/strategies/my_strategy.py` (inherit from `OptionsStrategy`)
- [ ] 2. Implement: `analyze_market()`, `should_enter()`, `construct_spread()`, `should_exit()`
- [ ] 3. Export in `src/quant_vibe/strategies/__init__.py`
- [ ] 4. Add to `src/backtest/engine.py` → `strategy_map`
- [ ] 5. Add to `src/quant_vibe/live/engine.py` → `strategy_classes`
- [ ] 6. Add to `src/admin_ui/backend/api/strategies.py` → `STRATEGY_METADATA`
- [ ] 7. Configure in `config/backtest.yaml` → `strategies.enabled`
- [ ] 8. Configure in `config/live_trading.yaml` → `strategies.enabled`
- [ ] 9. Run backtest: `python scripts/run_backtest.py --strategy my_strategy`
- [ ] 10. Test in Admin UI: Enable strategy, verify parameters, restart service
- [ ] 11. Paper trade for 1+ week before enabling live trading

---

**Questions?** Check the docs or raise an issue on GitHub.

**WARNING:** Trading involves risk. Past performance does not guarantee future results. Always test thoroughly before deploying live.
