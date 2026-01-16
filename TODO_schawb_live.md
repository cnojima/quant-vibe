## LIVE ORDERS - STATUS

### ✅ COMPLETED
- [x] Live order submission (`_submit_to_schwab`)
- [x] Order structure builder (`_build_schwab_order_structure`)
- [x] Live order cancellation (`_cancel_schwab_order`)
- [x] OCO order submission (`_submit_schwab_oco_order`)
- [x] Multi-leg spread orders support
- [x] Opening and closing orders (BUY_TO_OPEN, SELL_TO_CLOSE, etc.)
- [x] LIMIT and MARKET order types
- [x] Broker order ID tracking
- [x] Account number auto-fetch and caching

### 🧪 TESTING
**Test Scripts Available**:
1. `test_live_order_simple.py` - Quick manual test with hardcoded symbol
2. `test_live_order_submission.py` - Auto-finds ATM SPXW option

⚠️ **IMPORTANT**: These place REAL orders at $0.01 (never fills). See `scripts/TEST_LIVE_ORDERS_README.md` for details.

**Quick Start**:
```bash
source venv/bin/activate
python scripts/test_live_order_submission.py  # Automatic
# or
python scripts/test_live_order_simple.py      # Manual symbol
```

**Safety**:
- Orders submitted at $0.01 (way below market)
- Will NOT fill during test
- Automatic cancellation option
- Always verify in Schwab account after test

### 📋 TODO
- [x] Order status polling/monitoring
- [x] Handle partial fills
- [x] Position reconciliation with broker
- [x] Multiple account support (currently uses account[0])
- [x] Retry logic for API failures
- [x] Rate limiting / throttling

### ✅ NEWLY COMPLETED (2026-01-15)

#### Order Status Polling/Monitoring
- `poll_order_status()` - Poll individual order status from Schwab
- `poll_all_active_orders()` - Poll all active orders
- `_map_schwab_status()` - Map Schwab order statuses to internal OrderStatus enum
- `_extract_filled_price()` - Extract actual fill price from order response
- Automatic status updates (pending → submitted → filled/cancelled/rejected)
- Persists status changes to state store

#### Partial Fill Handling
- Added `filled_quantity`, `remaining_quantity` tracking to Order class
- `_extract_fill_quantities()` - Extract fill quantities from Schwab response
- `OrderStatus.PARTIALLY_FILLED` state
- Automatic detection of partial fills during status polling
- Partial fill data persisted in order metadata

#### Position Reconciliation
- `get_broker_positions()` - Fetch current positions from Schwab
- `reconcile_positions()` - Compare internal vs broker positions
- Detects discrepancies:
  - Missing positions (in broker but not internal)
  - Extra positions (in internal but not broker)
  - Quantity mismatches
- Detailed reconciliation report with per-symbol differences

#### Multiple Account Support
- `account_index` parameter to select which Schwab account to use
- `_get_account_number()` - Centralized account number fetching
- `list_available_accounts()` - List all linked Schwab accounts
- `switch_account()` - Switch between accounts at runtime
- Account caching to minimize API calls
- All API calls updated to use selected account

#### Retry Logic for API Failures
- `_retry_with_backoff()` - Exponential backoff retry wrapper
- Configurable retry settings (max_retries, delays, backoff_factor)
- Retries on transient errors:
  - HTTP 429 (Too Many Requests)
  - HTTP 500/502/503/504 (Server errors)
  - Network timeouts/connection errors
- Applied to all critical API calls:
  - Order placement
  - Order cancellation
  - Order status polling
  - Position fetching
- Detailed logging of retry attempts

#### Rate Limiting/Throttling
- `_apply_rate_limit()` - Automatic rate limiting before API calls
- Tracks request timestamps (per-second and per-minute)
- Enforces Schwab API limits (120 requests/minute, 2/second)
- Automatic sleep/wait when approaching limits
- `get_rate_limit_stats()` - Query current rate limit utilization
- Configurable rate limits
- Can be disabled for testing

### 📝 Implementation Notes

**Usage Example:**
```python
from live_trading_service.order_manager import OrderManager

# Initialize with all features enabled
order_manager = OrderManager(
    paper_trading=False,
    schwab_client=schwab_client,
    state_store=state_store,
    account_index=0,  # Use first account
    retry_config={
        'max_retries': 3,
        'initial_delay': 1.0,
        'backoff_factor': 2.0
    },
    rate_limit_config={
        'requests_per_second': 2,
        'requests_per_minute': 120,
        'enable_throttling': True
    }
)

# Submit order (automatically rate-limited and retried on failure)
success, message, order = order_manager.submit_position_entry(
    position, options_data, strategy_name
)

# Poll order status
success, status, message = order_manager.poll_order_status(order.order_id)

# Poll all active orders
results = order_manager.poll_all_active_orders()

# Reconcile positions
success, report, error = order_manager.reconcile_positions(internal_positions)

# Check rate limit usage
stats = order_manager.get_rate_limit_stats()
print(f"API utilization: {stats['utilization_pct']:.1f}%")
```

**Key Features:**
- All API calls automatically rate-limited
- Transient failures automatically retried with exponential backoff
- Partial fills tracked and logged
- Position mismatches detected and reported
- Multi-account support with easy switching
- Comprehensive logging throughout