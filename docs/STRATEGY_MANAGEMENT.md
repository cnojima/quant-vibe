# Strategy Management Guide

## Overview

The Admin UI now provides a web interface to manage trading strategies for the live_trading service. You can enable, disable, and view strategy configurations through the browser.

## Features

### Strategy Management Page (`/strategies`)

- **List all available strategies** with their current status (enabled/disabled)
- **Enable/disable strategies** with a single click
- **View strategy parameters** for each strategy
- **Real-time status updates** (polls every 5 seconds)
- **Configuration persistence** to `config/live_trading.yaml`

### Available Strategies

1. **Bullish Vertical Put** (`bullish_vertical_put`)
   - Credit spread strategy (sell put, buy lower put)
   - For bullish market conditions
   - Configurable spread width, profit targets, stop losses

2. **Bullish Vertical Call** (`bullish_vertical_call`)
   - Debit spread strategy (buy call, sell higher call)
   - For bullish market conditions
   - Optimized for 0-2 DTE trading

## How to Use

### Via Admin UI (Recommended)

1. Navigate to **Strategies** in the sidebar
2. View list of all available strategies
3. Click **Enable** or **Disable** to toggle a strategy
4. Click **Show Parameters** to view strategy configuration
5. **Restart the live_trading service** for changes to take effect

### Via Configuration File

Edit `config/live_trading.yaml`:

```yaml
strategies:
  enabled:
    - name: bullish_vertical_put
      enabled: true
      params:
        spread_width: 10.0
        observation_period: 30
        # ... other params
```

### Restart Requirement

⚠️ **Important**: Changes to strategy configuration require restarting the `live_trading` service.

**To restart:**
1. Go to **Services** page in Admin UI
2. Find `live_trading` service
3. Click **Restart**

Or via command line:
```bash
docker restart quant-vibe-live-trading
```

## API Endpoints

The strategy management API provides the following endpoints:

### GET `/api/strategies/list`

List all available strategies with their status.

**Response:**
```json
{
  "strategies": [
    {
      "name": "bullish_vertical_put",
      "enabled": true,
      "description": "Credit spread strategy...",
      "params": { ... }
    }
  ],
  "count": 2
}
```

### GET `/api/strategies/{strategy_name}`

Get details for a specific strategy.

**Response:**
```json
{
  "name": "bullish_vertical_put",
  "enabled": true,
  "description": "Credit spread strategy...",
  "params": {
    "spread_width": 10.0,
    "max_trades_daily": 1,
    ...
  }
}
```

### POST `/api/strategies/{strategy_name}/toggle`

Enable or disable a strategy.

**Request:**
```json
{
  "enabled": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Strategy 'bullish_vertical_put' enabled",
  "requires_restart": true
}
```

### PUT `/api/strategies/{strategy_name}/params`

Update parameters for a strategy.

**Request:**
```json
{
  "params": {
    "spread_width": 15.0,
    "max_trades_daily": 2
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Parameters updated for strategy 'bullish_vertical_put'",
  "requires_restart": true
}
```

## Architecture

### Backend

**File**: `src/admin_ui/backend/api/strategies.py`

- **Strategy Registry**: Maps strategy names to metadata (descriptions, default params)
- **Configuration Management**: Reads/writes `config/live_trading.yaml`
- **API Endpoints**: RESTful API for strategy CRUD operations

**Key Functions:**
- `list_strategies()`: Returns all available strategies
- `toggle_strategy()`: Enable/disable a strategy
- `update_strategy_params()`: Update strategy parameters

### Frontend

**File**: `src/admin_ui/frontend/src/pages/StrategiesManager.tsx`

- **React Component**: Displays strategies in card format
- **React Query Hooks**: Automatic refetching and cache management
- **Toggle Buttons**: Enable/disable strategies
- **Expandable Cards**: Show/hide strategy parameters

**API Client**: `src/admin_ui/frontend/src/api/queries.ts`

- `useStrategies()`: List all strategies
- `useToggleStrategy()`: Toggle strategy enabled state
- `useUpdateStrategyParams()`: Update strategy parameters

### Configuration Flow

```
┌─────────────────┐
│   Admin UI      │
│   (Browser)     │
└────────┬────────┘
         │ HTTP POST /api/strategies/{name}/toggle
         ▼
┌─────────────────┐
│  FastAPI        │
│  Backend        │
└────────┬────────┘
         │ yaml.dump()
         ▼
┌─────────────────┐
│ live_trading.   │
│     yaml        │
└────────┬────────┘
         │ Read on startup
         ▼
┌─────────────────┐
│ Live Trading    │
│    Engine       │
└─────────────────┘
```

## Adding New Strategies

### 1. Implement Strategy Class

Create strategy in `src/quant_vibe/strategies/`:

```python
from quant_vibe.strategies.options_base import OptionsStrategy

class MyNewStrategy(OptionsStrategy):
    def __init__(self, param1: float, param2: int):
        super().__init__()
        self.param1 = param1
        self.param2 = param2
        self.name = "my_new_strategy"

    # Implement required methods...
```

### 2. Register in StrategyLoader

Edit `src/live_trading_service/strategy_loader.py`:

```python
from quant_vibe.strategies.my_new_strategy import MyNewStrategy

class StrategyLoader:
    STRATEGY_REGISTRY = {
        'bullish_vertical_put': BullishVerticalPutStrategy,
        'bullish_vertical_call': BullishVerticalCallStrategy,
        'my_new_strategy': MyNewStrategy,  # Add this
    }
```

### 3. Add Metadata to Admin UI

Edit `src/admin_ui/backend/api/strategies.py`:

```python
STRATEGY_METADATA = {
    # ... existing strategies ...
    "my_new_strategy": {
        "description": "My awesome new strategy",
        "default_params": {
            "param1": 1.0,
            "param2": 10,
        },
    },
}
```

### 4. Restart Services

1. Restart `admin_ui` to load new API metadata:
   ```bash
   docker restart quant-vibe-admin-ui
   ```

2. Strategy will now appear in Admin UI
3. Enable it and restart `live_trading`

## Frontend Development

The frontend dev server (`npm run dev`) automatically hot-reloads when you modify:
- `StrategiesManager.tsx` - Main strategy management page
- `queries.ts` - API client functions
- `api.ts` - TypeScript types

**Backend changes** require restarting the Docker container:
```bash
docker restart quant-vibe-admin-ui
```

## Testing

### Test API Endpoints

Using the Admin UI Swagger docs (http://localhost:8000/docs):
1. Authenticate with `/api/auth/login`
2. Test `/api/strategies/list`
3. Test `/api/strategies/{name}/toggle`

### Test Frontend

1. Navigate to http://localhost:3000/strategies
2. Click **Enable** on a disabled strategy
3. Verify the badge changes to green "Enabled"
4. Check `config/live_trading.yaml` for the change
5. Restart `live_trading` service
6. Verify strategy is loaded in logs

## Troubleshooting

### Strategy Not Appearing

- Check `STRATEGY_METADATA` in `src/admin_ui/backend/api/strategies.py`
- Restart `admin_ui` container
- Check browser console for errors

### Toggle Not Working

- Check browser console for API errors
- Verify JWT token is valid (login again if needed)
- Check `admin_ui` logs: `docker logs quant-vibe-admin-ui`

### Strategy Not Loading in Live Trading

- Verify strategy is `enabled: true` in `config/live_trading.yaml`
- Restart `live_trading` service
- Check logs: `tail -f logs/live_trading/*.log`
- Verify strategy is in `STRATEGY_REGISTRY` in `strategy_loader.py`

### Configuration File Corrupted

A backup is automatically created when saving:
```bash
cp config/live_trading.yaml.backup config/live_trading.yaml
```

## Security

- All API endpoints require JWT authentication
- Configuration changes create automatic backups
- Only authorized users can modify strategies
- Changes are logged for audit trail

## Future Enhancements

- [ ] Edit strategy parameters via UI
- [ ] Duplicate strategies with different params
- [ ] Strategy performance metrics dashboard
- [ ] Hot-reload strategies without restart
- [ ] Strategy scheduling (time-based enable/disable)
- [ ] Strategy backtesting from UI
- [ ] Multi-strategy optimization
- [ ] Risk allocation per strategy

## Related Documentation

- [Live Trading Configuration](../config/live_trading.yaml) - Strategy configuration file
- [Strategy Loader](../src/live_trading_service/strategy_loader.py) - Strategy loading logic
- [Options Strategy Base](../src/quant_vibe/strategies/options_base.py) - Base class for strategies
- [Admin UI API](../src/admin_ui/backend/api/strategies.py) - Strategy management API
