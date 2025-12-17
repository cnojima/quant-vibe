# Live Trading Engine - Phase 2 Complete

## Overview

Phase 2 implements order submission and position tracking for the live trading engine. This phase enables the engine to open and close positions in both simulated and live modes.

**Status**: ✅ Complete (Simulated Mode) | ⚠️ Pending (Live Mode Integration)

## What Was Built

### 1. OrderManager (`src/quant_vibe/live/order_manager.py`)

**Purpose**: Submit and track orders in dual-mode architecture.

**Key Features**:

#### Simulated Mode (`paper_trading=True`)
- Process orders internally without broker interaction
- Simulate fills using current bid/ask quotes
- Apply realistic slippage based on DTE and price:
  - 0 DTE: 3% base (10% for options <$0.50)
  - 1 DTE: 2% base (8% for cheap options)
  - 2-7 DTE: 1.5%
  - 8+ DTE: 1%
- Instant fills (no waiting for broker)
- Full order lifecycle tracking

#### Live Mode (`paper_trading=False`)
- Schwab API integration (placeholder)
- Multi-leg spread order construction
- Order status polling
- Partial fill handling
- Slippage calculation

**Order Workflow**:
```python
# Entry
success, message, order = order_manager.submit_position_entry(
    position=options_position,
    options_data=current_quotes,
    strategy_name='my_strategy'
)

# Exit
success, message, order = order_manager.submit_position_exit(
    position=options_position,
    options_data=current_quotes,
    strategy_name='my_strategy'
)
```

**Classes**:
- `Order`: Represents a single order
- `OrderStatus`: Enum for order states (PENDING, FILLED, CANCELLED, etc.)
- `OrderSide`: BUY/SELL enum
- `OrderManager`: Main order management class

### 2. PositionManager (`src/quant_vibe/live/position_manager.py`)

**Purpose**: Track open positions and calculate real-time P&L.

**Key Features**:
- Track all open positions by strategy
- Update position values from streaming quotes
- Calculate unrealized P&L ($ and %)
- Monitor position limits
- Track daily statistics
- Position reconciliation (planned for live mode)

**Position Lifecycle**:
```python
# Add position
position_manager.add_position(
    position=options_position,
    strategy_name='my_strategy',
    fill_price=actual_fill_price
)

# Update values from streaming data
position_manager.update_position_values(options_data)

# Check P&L
pnl = position_manager.get_position_pnl(position_id)
pnl_pct = position_manager.get_position_pnl_pct(position_id)

# Close position
position_manager.close_position(
    position_id=position_id,
    exit_reason='profit_target',
    exit_price=exit_fill_price
)
```

**Tracking Features**:
- Open positions count
- Total capital deployed
- Daily opened/closed counts
- Daily P&L
- Win/loss tracking
- Capital usage metrics

### 3. Integration Updates

**Updated Files**:
- `src/quant_vibe/live/__init__.py` - Export new classes
- `src/quant_vibe/live/state_store.py` - Already supports orders and positions
- `scripts/test_phase2.py` - Comprehensive test suite

## Testing

**Test Script**: `scripts/test_phase2.py`

Validates:
1. Component initialization
2. Position creation (BullishVerticalPut example)
3. Position persistence to database
4. Order submission with slippage
5. Position tracking
6. Real-time P&L calculation
7. Position exit workflow
8. Daily statistics tracking

**Test Results**:
```
✅ OrderManager (simulated mode)
✅ Order submission with slippage modeling
✅ PositionManager tracking
✅ Real-time P&L calculations
✅ Position entry and exit workflow
✅ Daily statistics tracking
```

## Slippage Modeling

Simulated mode applies realistic slippage based on:

| DTE | Base Slippage | Cheap Options (<$0.50) |
|-----|---------------|------------------------|
| 0   | 3%            | 10%                    |
| 1   | 2%            | 8%                     |
| 2-7 | 1.5%          | N/A                    |
| 8+  | 1%            | N/A                    |

**Application**:
- Buy orders: Pay slippage above ask
- Sell orders: Receive slippage below bid
- Always unfavorable to trader (conservative)

## Database Schema

**Tables Used**:
- `live_positions` - Position tracking
- `live_orders` - Order tracking
- `live_events` - Audit log

**Position Data Stored**:
- Position ID, strategy name, spread type
- Entry/exit times and prices
- Legs (symbol, strike, expiration, quantity, price)
- Profit targets, stops
- Current value, P&L

**Order Data Stored**:
- Order ID, position ID, strategy name
- Status, submitted/filled times
- Expected vs filled prices
- Broker order ID (for live mode)
- Error messages

## Usage Examples

### Example 1: Simulated Order Entry

```python
from quant_vibe.live import OrderManager, PositionManager, StateStore
from quant_vibe.strategies.options_base import OptionsPosition, OptionLeg

# Initialize
state_store = StateStore()
order_mgr = OrderManager(paper_trading=True, state_store=state_store)
position_mgr = PositionManager(state_store=state_store)

# Create position (from strategy)
position = OptionsPosition(...)

# Save position skeleton first (for DB foreign key)
position_mgr.add_position(position, 'my_strategy', position.entry_cost)

# Submit order
success, msg, order = order_mgr.submit_position_entry(
    position, options_data, 'my_strategy'
)

if success:
    # Update position with actual fill
    position.entry_cost = order.filled_total_price
    position_mgr.total_capital_deployed = abs(order.filled_total_price)
```

### Example 2: Position Tracking

```python
# Get open positions
open_positions = position_mgr.get_open_positions('my_strategy')

# Update values from streaming data
position_mgr.update_position_values(current_options_quotes)

# Check P&L
for pos in open_positions:
    pnl = position_mgr.get_position_pnl(pos.position_id)
    pnl_pct = position_mgr.get_position_pnl_pct(pos.position_id)
    print(f"Position {pos.position_id}: ${pnl:.2f} ({pnl_pct:.2f}%)")

# Get daily stats
stats = position_mgr.get_daily_stats()
print(f"Today: {stats['wins_today']}W / {stats['losses_today']}L")
print(f"P&L: ${stats['total_pnl_today']:.2f}")
```

### Example 3: Position Exit

```python
# Submit exit order
success, msg, exit_order = order_mgr.submit_position_exit(
    position, options_data, 'my_strategy'
)

if success:
    # Close position
    position_mgr.close_position(
        position_id=position.position_id,
        exit_reason='profit_target',
        exit_price=exit_order.filled_total_price
    )
```

## What's NOT Included (Yet)

The following will be implemented in future phases or enhancements:

❌ Live Schwab API order submission (Phase 2 enhancement)
❌ Partial fill handling (Live mode)
❌ Order cancellation API integration (Live mode)
❌ Position reconciliation with broker (Live mode)
❌ Integration with LiveTradingEngine (Phase 3)
❌ Strategy executor (Phase 3)

## Key Design Decisions

1. **Dual-Mode Architecture**: Single codebase supports both simulated and live trading via config flag
2. **Conservative Slippage**: Simulated slippage is intentionally unfavorable to avoid over-optimism
3. **Position-First Workflow**: Position skeleton saved to DB before order submission (for foreign key integrity)
4. **Instant Simulated Fills**: No artificial delay in simulated mode (can be added if needed)
5. **Comprehensive Tracking**: Every order and position logged to database for audit trail

## Performance Considerations

**Simulated Mode**:
- Instant order processing (< 1ms)
- No network latency
- No broker API rate limits

**Live Mode** (when implemented):
- Network latency to Schwab API (typically 100-500ms)
- Order status polling overhead
- API rate limits apply

## Error Handling

**OrderManager**:
- Validates options_data exists for all legs
- Returns (success, message, order) tuple
- Logs errors with full context
- Persists order status including errors

**PositionManager**:
- Handles missing quotes gracefully
- Continues on position update errors
- Logs warnings for missing data
- Tracks partial position updates

## Next Steps - Phase 3

Phase 3 will integrate OrderManager and PositionManager into the LiveTradingEngine:

1. **StrategyExecutor** - Execute strategies on streaming data
2. **Strategy Integration** - Adapt backtest strategies for live trading
3. **Real-Time Execution Loop** - Call strategies on each new bar
4. **Position Monitoring** - Check exit conditions continuously
5. **End-of-Day Handling** - Close positions, reset state

See: `docs/LIVE_TRADING_PLAN.md` for complete Phase 3 details

## Testing Phase 2

```bash
# Run comprehensive tests
python scripts/test_phase2.py

# Expected output: All tests pass
# - Component initialization
# - Position creation
# - Order submission with slippage
# - Position tracking
# - P&L calculations
# - Exit workflow
# - Daily statistics
```

## Troubleshooting

**Issue**: Foreign key constraint error
**Solution**: Ensure position is saved to DB before submitting order

**Issue**: AttributeError on OptionLeg
**Solution**: Use `strike_price` not `strike`, `expiration_date` not `expiration`

**Issue**: P&L calculation seems wrong
**Solution**: Remember entry_cost can be negative (credit spreads). P&L = current_value - entry_cost works for both debit and credit spreads.

**Issue**: Slippage seems too high
**Solution**: Slippage models are intentionally conservative. Adjust `_get_slippage_model()` if needed.

## Support

For issues or questions:
1. Check test output: `python scripts/test_phase2.py`
2. Query database: `SELECT * FROM live_orders ORDER BY submitted_time DESC LIMIT 10;`
3. Check logs: `logs/live_trading/`
4. Review code: `src/quant_vibe/live/order_manager.py` and `position_manager.py`

---

**Last Updated**: 2025-12-17
**Version**: 1.0
**Status**: Phase 2 Complete (Simulated Mode) ✅
**Next**: Phase 3 - Strategy Integration
