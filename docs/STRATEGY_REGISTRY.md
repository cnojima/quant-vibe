# Strategy Registry - Unified Parameter Management

## Overview

The **StrategyRegistry** provides a centralized, single-source-of-truth system for managing trading strategy parameters across all components:

- ✅ **Backtest Engine** - Validates params before backtesting
- ✅ **Live Trading Engine** - Validates params before live execution
- ✅ **Optimization Scripts** - Validates params before grid search
- ✅ **Admin UI** - Auto-generates metadata from Pydantic models

## Problem Solved

### Before (❌ Fragmented):
```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ Backtest Engine │  │ Live Trading    │  │ Optimizer       │
│ strategy_map    │  │ STRATEGY_REG    │  │ STRATEGY_MAP    │
│ (hardcoded)     │  │ (hardcoded)     │  │ (hardcoded)     │
└─────────────────┘  └─────────────────┘  └─────────────────┘
        ↓                    ↓                     ↓
    validate_and_      NO VALIDATION        NO VALIDATION
    normalize_params   (runtime errors)    (runtime errors)
```

**Issues:**
- 4 separate strategy registries (backtest, live, optimizer, Admin UI)
- 3 parameter definitions (Pydantic models, optimizer grids, Admin UI metadata)
- Only backtest validates - live trading and optimizer bypass validation
- Manual synchronization required across all locations
- Runtime errors due to parameter mismatches

### After (✅ Unified):
```
┌──────────────────────────────────────────────────────┐
│  StrategyRegistry (Single Source of Truth)           │
│  - Pydantic models (params.py)                       │
│  - Validation rules, defaults, descriptions          │
│  - Auto-generates metadata for all consumers         │
└──────────────────────────────────────────────────────┘
                         ↓
         ┌───────────────┼───────────────┐
         ↓               ↓               ↓
    Backtest        Live Trading    Optimizer
    validate()      validate()      validate()
```

**Benefits:**
- ✅ Single registry for all components
- ✅ Automatic validation before execution
- ✅ Clear error messages with valid parameter lists
- ✅ Auto-generates Admin UI metadata (no duplication)
- ✅ Type safety via Pydantic
- ✅ Fail-fast with helpful errors

## Architecture

### Core Components

1. **`src/quant_vibe/strategies/params.py`** - Pydantic models (source of truth)
   - Defines parameter schemas with types, defaults, validation rules
   - Example: `CoinTossParams`, `BullishVerticalPutParams`

2. **`src/quant_vibe/strategies/registry.py`** - Central registry
   - Maps strategy names to classes and Pydantic models
   - Provides validation, instantiation, metadata generation

3. **Consumers** - All use the registry:
   - `src/backtest/engine.py` - Backtest orchestrator
   - `src/live_trading_service/strategy_loader.py` - Live trading loader
   - `scripts/optimize_strategy.py` - Optimization script
   - `src/admin_ui/backend/api/strategies.py` - Admin UI API

## Usage

### Validate Parameters

```python
from quant_vibe.strategies.registry import StrategyRegistry

# Validate params (warns on unknown params)
params = {'target_price': 2.0, 'profit_target_pct': 1.0}
validated = StrategyRegistry.validate_params('coin_toss', params)

# Strict mode (raises on unknown params)
validated = StrategyRegistry.validate_params('coin_toss', params, strict=True)
```

### Create Strategy Instance

```python
from quant_vibe.strategies.registry import StrategyRegistry

# Create with validation
strategy = StrategyRegistry.create_strategy(
    strategy_name='coin_toss',
    params={'target_price': 2.0, 'profit_target_pct': 1.0},
    validate=True  # default
)

# Create without validation (fallback mode)
strategy = StrategyRegistry.create_strategy(
    strategy_name='coin_toss',
    params=params,
    validate=False
)
```

### Get Parameter Specifications

```python
from quant_vibe.strategies.registry import StrategyRegistry

# Get param specs (for UI forms, documentation)
specs = StrategyRegistry.get_param_specs('coin_toss')
# Returns:
# {
#     'target_price': {
#         'type': 'float',
#         'default': 2.0,
#         'description': 'Target contract price',
#         'ge': 0.0,  # Greater than or equal constraint
#     },
#     ...
# }

# Get default params
defaults = StrategyRegistry.get_default_params('coin_toss')
```

### Auto-Generate Metadata (Admin UI)

```python
from quant_vibe.strategies.registry import StrategyRegistry

# Get metadata for all strategies
metadata = StrategyRegistry.get_all_metadata()
# Returns:
# {
#     'coin_toss': {
#         'description': 'Naive strategy that randomly picks...',
#         'default_params': {'target_price': 2.0, ...}
#     },
#     ...
# }

# Get metadata for one strategy
metadata = StrategyRegistry.get_metadata_for_admin_ui('coin_toss')
```

### List Available Strategies

```python
from quant_vibe.strategies.registry import StrategyRegistry

strategies = StrategyRegistry.list_strategies()
# Returns: ['bearish_iv_scalp', 'bollinger_band', 'coin_toss', ...]
```

## Adding a New Strategy

### Step 1: Create Pydantic Model (params.py)

```python
# src/quant_vibe/strategies/params.py

class MyNewStrategyParams(BaseStrategyParams):
    """Parameters for My New Strategy."""

    my_param: float = Field(
        default=10.0,
        ge=0.0,
        le=100.0,
        description="Description of my parameter"
    )
    another_param: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Another parameter"
    )

# Add to registry map
STRATEGY_PARAMS_MAP = {
    'my_new_strategy': MyNewStrategyParams,
    # ... existing strategies
}
```

### Step 2: Register in Registry (registry.py)

```python
# src/quant_vibe/strategies/registry.py

from quant_vibe.strategies.my_new_strategy import MyNewStrategy

class StrategyRegistry:
    _STRATEGY_CLASSES = {
        'my_new_strategy': MyNewStrategy,
        # ... existing strategies
    }

    _MODULE_PATHS = {
        'my_new_strategy': 'quant_vibe.strategies.my_new_strategy.MyNewStrategy',
        # ... existing strategies
    }

    _DESCRIPTIONS = {
        'my_new_strategy': 'Brief description for UI',
        # ... existing strategies
    }
```

### Step 3: Test

```python
from quant_vibe.strategies.registry import StrategyRegistry

# Verify registration
print(StrategyRegistry.list_strategies())

# Test validation
params = {'my_param': 15.0, 'another_param': 3}
validated = StrategyRegistry.validate_params('my_new_strategy', params)
print(validated)

# Create instance
strategy = StrategyRegistry.create_strategy('my_new_strategy', params)

# Verify Admin UI metadata generation
metadata = StrategyRegistry.get_metadata_for_admin_ui('my_new_strategy')
print(f"Description: {metadata['description']}")
print(f"Defaults: {metadata['default_params']}")
```

**That's it!** The strategy is now available in:
- ✅ Backtest engine (`src/backtest/engine.py`)
- ✅ Live trading engine (`src/live_trading_service/strategy_loader.py`)
- ✅ Optimization scripts (`scripts/optimize_strategy.py`)
- ✅ Admin UI (`src/admin_ui/backend/api/strategies.py` - auto-generated metadata)

**No Admin UI code changes needed!** The UI will automatically:
- Show the new strategy in the strategies list
- Display the description from `_DESCRIPTIONS`
- Show all parameters with correct defaults from Pydantic model
- Validate parameters before saving to config

## Error Messages

### Unknown Strategy

```
ValueError: Unknown strategy: 'invalid_name'
Available strategies: bearish_iv_scalp, bollinger_band, coin_toss, ...
```

### Invalid Parameters (Strict Mode)

```
ValueError: Warning: Unknown parameters for strategy 'coin_toss': ['profit_target_min']
Valid parameters: ['buy_limit', 'max_dte', 'max_trades_daily', 'min_dte',
                   'price_tolerance', 'profit_target_pct', 'quantity',
                   'sell_target', 'stop_loss_pct', 'target_price']
```

### Type/Range Violations

```
ValueError: Invalid parameters for strategy 'coin_toss':
1 validation error for CoinTossParams
target_price
  Input should be greater than or equal to 0.0 [type=greater_than_equal, ...]
```

## Migration Guide

### Backtest Engine (Already Migrated ✅)

Before:
```python
strategy_map = {
    'coin_toss': 'quant_vibe.strategies.coin_toss.CoinTossStrategy',
}
module_path = strategy_map[strategy_name]
module_name, class_name = module_path.rsplit('.', 1)
module = __import__(module_name, fromlist=[class_name])
strategy_class = getattr(module, class_name)
strategy = strategy_class(**params)
```

After:
```python
from quant_vibe.strategies.registry import StrategyRegistry

strategy = StrategyRegistry.create_strategy(
    strategy_name=strategy_name,
    params=params,
    validate=True
)
```

### Live Trading Loader (Already Migrated ✅)

Before:
```python
STRATEGY_REGISTRY = {
    'coin_toss': CoinTossStrategy,
}
strategy_class = STRATEGY_REGISTRY[strategy_name]
strategy = strategy_class(**params)
```

After:
```python
from quant_vibe.strategies.registry import StrategyRegistry

strategy = StrategyRegistry.create_strategy(
    strategy_name=strategy_name,
    params=params,
    validate=True
)
```

### Optimizer (Already Migrated ✅)

Before:
```python
STRATEGY_MAP = {
    'coin_toss': CoinTossStrategy,
}
# No validation - runtime errors!
```

After:
```python
from quant_vibe.strategies.registry import StrategyRegistry

# Validate before running optimization
sample_params = {**fixed_params}
for key, values in param_grid.items():
    sample_params[key] = values[0]

StrategyRegistry.validate_params(strategy_name, sample_params, strict=True)
# Now safe to run optimization!
```

### Admin UI (Already Migrated ✅)

Before:
```python
# Static metadata loaded at module import time
STRATEGY_METADATA = {
    'coin_toss': {
        'description': '...',
        'default_params': {
            'target_price': 2.0,
            # ... manually duplicated from Pydantic
        }
    }
}

# Used in endpoints
@router.get("/list")
async def list_strategies():
    for name, metadata in STRATEGY_METADATA.items():  # Static!
        # ...
```

After:
```python
from quant_vibe.strategies.registry import StrategyRegistry

def get_strategy_metadata() -> dict[str, dict[str, Any]]:
    """Get strategy metadata from central registry (dynamic!)."""
    return StrategyRegistry.get_all_metadata()

# Used in endpoints - called dynamically each time
@router.get("/list")
async def list_strategies():
    strategy_metadata = get_strategy_metadata()  # Fresh data!
    for name, metadata in strategy_metadata.items():
        # ...
```

**Key Improvement:** Metadata is now generated **dynamically** on each API call, not cached at module load time. This means:
- ✅ New strategies appear immediately in Admin UI
- ✅ Parameter changes reflect without server restart
- ✅ Always in sync with registry state

## Testing

Run the test suite:

```bash
# Test registry import
python -c "from quant_vibe.strategies.registry import StrategyRegistry; print(StrategyRegistry.list_strategies())"

# Test validation
python -c "
from quant_vibe.strategies.registry import StrategyRegistry
params = {'target_price': 2.0, 'profit_target_pct': 1.0}
validated = StrategyRegistry.validate_params('coin_toss', params)
print('Validation passed:', validated)
"

# Test strict mode (should fail on unknown params)
python -c "
from quant_vibe.strategies.registry import StrategyRegistry
params = {'profit_target_min': 0.5}  # WRONG param name
try:
    StrategyRegistry.validate_params('coin_toss', params, strict=True)
except ValueError as e:
    print('Correctly caught:', e)
"
```

## Admin UI Integration Details

### Dynamic Metadata Loading

The Admin UI now uses **dynamic metadata generation** instead of static caching:

**File:** `src/admin_ui/backend/api/strategies.py`

```python
def get_strategy_metadata() -> dict[str, dict[str, Any]]:
    """Get fresh metadata from registry on each call."""
    return StrategyRegistry.get_all_metadata()

@router.get("/list")
async def list_strategies(current_user: User = Depends(get_current_user)):
    # Called dynamically - always fresh!
    strategy_metadata = get_strategy_metadata()
    for name, metadata in strategy_metadata.items():
        # ... build response
```

**All Endpoints Updated:**
- ✅ `GET /api/strategies/list` - List all strategies
- ✅ `GET /api/strategies/{strategy_name}` - Get strategy details
- ✅ `POST /api/strategies/{strategy_name}/toggle` - Enable/disable strategy
- ✅ `PUT /api/strategies/{strategy_name}/params` - Update parameters

**Benefits:**
- New strategies appear immediately (no server restart)
- Parameter changes reflect instantly
- Always in sync with Pydantic models
- Zero manual metadata duplication

### Complete Workflow Example

**1. Add Strategy to Registry**
```python
# src/quant_vibe/strategies/params.py
class MyStrategyParams(BaseStrategyParams):
    my_param: float = Field(default=5.0, ge=0.0, description="My parameter")

STRATEGY_PARAMS_MAP = {
    'my_strategy': MyStrategyParams,
}

# src/quant_vibe/strategies/registry.py
_STRATEGY_CLASSES = {
    'my_strategy': MyStrategy,
}
_DESCRIPTIONS = {
    'my_strategy': 'My strategy description',
}
```

**2. Access Admin UI**
- Navigate to `http://localhost:5173/strategies`
- Strategy appears immediately in list
- Parameters show with correct defaults and descriptions
- Enable/disable toggle works
- Parameter editing validates against Pydantic model

**3. Configuration Auto-Updates**
- Enabling strategy adds to `config/live_trading.yaml`:
```yaml
strategies:
  enabled:
    - name: my_strategy
      enabled: true
      params:
        my_param: 5.0  # From Pydantic default
        min_dte: 0     # From BaseStrategyParams
        max_dte: 45
```

## Benefits Summary

1. **Single Source of Truth** - Pydantic models define everything
2. **Fail-Fast Validation** - Errors caught before execution
3. **Zero Duplication** - Auto-generate metadata, grids, defaults
4. **Clear Error Messages** - Shows valid params when validation fails
5. **Type Safety** - Pydantic enforces types and ranges
6. **Easy Maintenance** - Add new strategy = update 2 files (params.py, registry.py)
7. **Backward Compatible** - Existing code continues to work
8. **Future-Proof** - Easy to add new consumers (e.g., CLI tools, notebooks)
9. **Dynamic Admin UI** - New strategies appear instantly without server restart
10. **Zero UI Code** - Admin UI requires no changes for new strategies

## Recent Additions (2026-01-01)

### Bollinger Band Strategies

Two new educational/experimental strategies were added to demonstrate the registry system:

**1. `bollinger_band` (Market Orders)**
- Uses Bollinger Bands for directional signals
- Buys calls at lower band, puts at upper band
- Market order execution (simulated)
- Parameters: `bb_period`, `bb_std`, `bb_threshold`, `target_price`, etc.

**2. `bollinger_band_limit` (Limit Orders)**
- Same directional logic as `bollinger_band`
- Limit order execution: buy at $1, sell at $2
- Additional parameters: `limit_buy_price`, `profit_target_price`, `order_expiry_minutes`

**Integration Steps Completed:**
1. ✅ Created `BollingerBandParams` and `BollingerBandLimitParams` in `params.py`
2. ✅ Added to `STRATEGY_PARAMS_MAP`
3. ✅ Registered in `StrategyRegistry._STRATEGY_CLASSES`
4. ✅ Added module paths to `_MODULE_PATHS`
5. ✅ Added descriptions to `_DESCRIPTIONS`
6. ✅ Admin UI automatically detected both strategies (zero UI code changes)

**Verification:**
```bash
# List all strategies (should include bollinger_band and bollinger_band_limit)
python -c "from quant_vibe.strategies.registry import StrategyRegistry; print(StrategyRegistry.list_strategies())"

# Get metadata for bollinger_band
python -c "from quant_vibe.strategies.registry import StrategyRegistry; import json; print(json.dumps(StrategyRegistry.get_metadata_for_admin_ui('bollinger_band'), indent=2))"
```

## Troubleshooting

### "Unknown strategy" error

**Cause:** Strategy not registered in `StrategyRegistry._STRATEGY_CLASSES`

**Fix:** Add your strategy to the registry in `src/quant_vibe/strategies/registry.py`

**Example:** See the Bollinger Band strategies registration above

### "Unknown parameters" warning

**Cause:** Parameter name doesn't match Pydantic model

**Fix:** Check `src/quant_vibe/strategies/params.py` for correct parameter names

**Debugging:**
```python
from quant_vibe.strategies.registry import StrategyRegistry
specs = StrategyRegistry.get_param_specs('your_strategy')
print("Valid parameters:", list(specs.keys()))
```

### "Validation error"

**Cause:** Parameter value violates constraints (type, range, etc.)

**Fix:** Check the error message for constraints (ge, le, etc.) and adjust values

**Debugging:**
```python
from quant_vibe.strategies.registry import StrategyRegistry
specs = StrategyRegistry.get_param_specs('your_strategy')
print(f"Constraints for 'my_param': {specs['my_param']}")
```

### Admin UI not showing new strategy

**Cause:** Strategy not in registry or missing Pydantic model

**Fix:**
1. Verify strategy is in `StrategyRegistry._STRATEGY_CLASSES` (registry.py)
2. Verify Pydantic model exists in `STRATEGY_PARAMS_MAP` (params.py)
3. Check browser console for errors
4. The Admin UI now uses **dynamic** metadata, so no server restart needed!

**Verification:**
```bash
# Test metadata generation
python -c "from admin_ui.backend.api.strategies import get_strategy_metadata; print(get_strategy_metadata().keys())"
```
