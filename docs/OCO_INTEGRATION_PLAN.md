# OCO (One Cancels Other) Order Integration Plan

## Overview

Integrate Schwab's OCO order functionality into the live trading engine to provide automatic profit target and stop loss protection at the broker level.

## Benefits

- **Crash Protection**: Exit orders persist even if engine crashes
- **Network Resilience**: Works during temporary connection loss
- **Zero Monitoring Latency**: Broker executes exits instantly
- **Reduced Engine Complexity**: No continuous position monitoring needed
- **Better Execution**: Broker-side logic is more reliable than polling

## OCO Order Structure for Options Spreads

### Entry Order Structure
```json
{
  "orderStrategyType": "TRIGGER",
  "orderType": "NET_DEBIT",  // or "NET_CREDIT" for credit spreads
  "session": "NORMAL",
  "duration": "DAY",
  "price": 2.50,  // Max debit willing to pay (or min credit to receive)
  "orderLegCollection": [
    {
      "instruction": "BUY_TO_OPEN",
      "quantity": 1,
      "instrument": {
        "assetType": "OPTION",
        "symbol": "SPXW_250117P5900"
      }
    },
    {
      "instruction": "SELL_TO_OPEN",
      "quantity": 1,
      "instrument": {
        "assetType": "OPTION",
        "symbol": "SPXW_250117P5890"
      }
    }
  ],
  "childOrderStrategies": [
    {
      "orderStrategyType": "OCO",
      "childOrderStrategies": [
        // Profit Target (see below)
        // Stop Loss (see below)
      ]
    }
  ]
}
```

### Profit Target Child Order
```json
{
  "orderStrategyType": "SINGLE",
  "orderType": "NET_CREDIT",  // Selling the spread back
  "session": "NORMAL",
  "duration": "GOOD_TILL_CANCEL",
  "price": 3.75,  // Profit target price (150% of entry)
  "orderLegCollection": [
    {
      "instruction": "SELL_TO_CLOSE",
      "quantity": 1,
      "instrument": {
        "assetType": "OPTION",
        "symbol": "SPXW_250117P5900"
      }
    },
    {
      "instruction": "BUY_TO_CLOSE",
      "quantity": 1,
      "instrument": {
        "assetType": "OPTION",
        "symbol": "SPXW_250117P5890"
      }
    }
  ]
}
```

### Stop Loss Child Order
```json
{
  "orderStrategyType": "SINGLE",
  "orderType": "MARKET",  // Market order for fast exit on stop
  "session": "NORMAL",
  "duration": "GOOD_TILL_CANCEL",
  "stopPrice": 1.25,  // Stop loss trigger (50% of entry)
  "orderLegCollection": [
    // Same as profit target, but triggered at stop price
  ]
}
```

## Code Changes

### 1. OrderManager Enhancements

**File**: `src/quant_vibe/live/order_manager.py`

**New Features**:
- Add OCO order construction
- Calculate profit target and stop loss prices
- Build child order strategies
- Track parent-child order relationships

**New Methods**:
```python
def _build_oco_children(
    self,
    position: OptionsPosition,
    entry_price: float
) -> List[Dict]:
    """
    Build OCO child orders for profit target and stop loss.

    Args:
        position: Position with profit_target and stop_loss defined
        entry_price: Expected entry fill price

    Returns:
        List with OCO child order structures
    """

def _calculate_exit_prices(
    self,
    position: OptionsPosition,
    entry_price: float
) -> Tuple[float, float]:
    """
    Calculate profit target and stop loss exit prices.

    Args:
        position: Position with profit_target (%) and stop_loss (%) defined
        entry_price: Entry fill price

    Returns:
        (profit_target_price, stop_loss_price)
    """
```

**Updated Methods**:
```python
def submit_position_entry(
    self,
    position: OptionsPosition,
    options_data: Dict[str, Dict],
    strategy_name: str,
    use_oco: bool = True  # NEW PARAMETER
) -> Tuple[bool, str, Optional[Order]]:
    """Submit entry order, optionally with OCO children."""
```

### 2. Order Class Enhancement

**New Fields**:
```python
class Order:
    # ... existing fields ...

    # OCO tracking
    has_oco_children: bool = False
    profit_target_order_id: Optional[str] = None
    stop_loss_order_id: Optional[str] = None
    oco_status: Optional[str] = None  # 'pending', 'profit_filled', 'stop_filled'
```

### 3. PositionManager Enhancements

**New Tracking**:
- Track which OCO leg filled (profit vs stop)
- Update exit reason based on OCO leg
- Handle broker-initiated exits (not engine-initiated)

**New Methods**:
```python
def handle_oco_fill(
    self,
    position_id: str,
    filled_order: str,  # 'profit_target' or 'stop_loss'
    exit_price: float
) -> bool:
    """Handle position exit when OCO leg fills."""
```

### 4. LiveTradingEngine Integration

**New Configuration**:
```yaml
engine:
  use_oco_orders: true  # Enable OCO protection
  oco_profit_target_default: 0.50  # 50% profit
  oco_stop_loss_default: -0.30  # -30% loss
```

**Event Handling**:
- Listen for order fill events from Schwab stream
- Detect OCO child order fills
- Update position status accordingly
- Log which OCO leg triggered

### 5. StateStore Enhancements

**Track OCO Relationships**:
```sql
ALTER TABLE live_orders ADD COLUMN parent_order_id TEXT;
ALTER TABLE live_orders ADD COLUMN order_relationship TEXT;  -- 'parent', 'profit_target', 'stop_loss'
ALTER TABLE live_orders ADD COLUMN oco_group_id TEXT;
```

## Implementation Phases

### Phase 1: Order Construction (Simulated Mode)
- Build OCO order structure in OrderManager
- Calculate exit prices based on position parameters
- Store OCO metadata in database
- **Simulated mode**: Still monitor and exit manually (OCO structure ignored)

### Phase 2: Live Mode Integration
- Implement Schwab API submission with childOrderStrategies
- Add order event listener for fill notifications
- Handle OCO child order fills
- Update position manager when broker closes position

### Phase 3: Monitoring & Recovery
- Reconcile positions with broker on startup
- Detect if OCO orders are still active
- Handle partial fills and cancellations
- Alert if OCO orders fail to place

## Safety Considerations

### Advantages
1. ✅ Protection persists even if engine crashes
2. ✅ Faster execution (broker-side)
3. ✅ No polling overhead
4. ✅ Works during network issues

### Potential Issues
1. ⚠️ Can't dynamically adjust profit target (e.g., trailing stop)
2. ⚠️ OCO orders might fail to place if entry order fills during volatility
3. ⚠️ Need to verify OCO orders were actually placed
4. ⚠️ More complex error handling

### Mitigations
1. **Verify OCO Placement**: After entry fill, confirm both child orders are active
2. **Fallback Monitoring**: If OCO fails to place, fall back to engine-based monitoring
3. **Hybrid Approach**: Use OCO for static stops, engine for dynamic (trailing) stops
4. **Alert on Failure**: Send critical alert if OCO orders don't place

## Hybrid Approach: Best of Both Worlds

**Recommended Strategy**:

1. **Use OCO for**:
   - Hard stop loss (disaster protection)
   - Minimum profit target (lock in some gains)

2. **Use Engine Monitoring for**:
   - Trailing stops (dynamic)
   - Time-based exits (e.g., 3:55 PM close)
   - Complex exit conditions (multiple criteria)

**Example**:
```python
# Entry: Buy spread at $2.00

# OCO Protection (broker-side):
- Stop loss: Sell at $1.00 (50% loss) - SAFETY NET
- Basic profit: Sell at $3.00 (50% profit) - MINIMUM TARGET

# Engine Monitoring (dynamic):
- Trailing stop: If profit > 100%, trail stop at 50%
- Time exit: Close at 3:55 PM regardless
- Strategy-specific: Exit if underlying breaks support
```

**Benefits**:
- Hard stop always active (crash protection)
- Can still implement sophisticated exit logic
- Best of both worlds

## Configuration

### Per-Strategy Configuration
```yaml
strategies:
  - name: bullish_vertical_put
    oco_settings:
      enabled: true
      profit_target_pct: 0.50  # 50%
      stop_loss_pct: -0.30     # -30%
      use_market_on_stop: true  # Market order for stop, limit for profit

  - name: iron_condor
    oco_settings:
      enabled: true
      profit_target_pct: 0.70  # Take profit earlier (tighter spread)
      stop_loss_pct: -0.50     # Allow more loss (wider spread)
```

### Global Fallback
```yaml
engine:
  oco_defaults:
    enabled: true
    profit_target_pct: 0.50
    stop_loss_pct: -0.30
    verify_placement: true  # Confirm OCO orders placed
    fallback_to_monitoring: true  # Fall back if OCO fails
```

## Testing Strategy

### Phase 1: Unit Tests
- Test OCO order construction
- Validate price calculations
- Test order structure serialization

### Phase 2: Simulated Mode
- Build OCO structures but don't submit
- Log what would be submitted
- Verify correct prices

### Phase 3: Small Live Test
- Submit 1-2 real OCO orders with small size
- Verify broker accepts them
- Let one fill naturally
- Verify correct execution

### Phase 4: Full Integration
- Enable for all strategies
- Monitor for failures
- Verify protection works as expected

## Database Schema Changes

```sql
-- Track OCO relationships
ALTER TABLE live_orders ADD COLUMN IF NOT EXISTS parent_order_id TEXT;
ALTER TABLE live_orders ADD COLUMN IF NOT EXISTS order_relationship TEXT;
ALTER TABLE live_orders ADD COLUMN IF NOT EXISTS oco_group_id TEXT;

-- Index for looking up OCO children
CREATE INDEX IF NOT EXISTS idx_orders_oco_group
ON live_orders(oco_group_id);

-- Add OCO metadata to positions
ALTER TABLE live_positions ADD COLUMN IF NOT EXISTS oco_enabled BOOLEAN DEFAULT FALSE;
ALTER TABLE live_positions ADD COLUMN IF NOT EXISTS profit_target_price NUMERIC;
ALTER TABLE live_positions ADD COLUMN IF NOT EXISTS stop_loss_price NUMERIC;
ALTER TABLE live_positions ADD COLUMN IF NOT EXISTS oco_status TEXT;
```

## Monitoring & Alerts

**Critical Alerts**:
- OCO orders failed to place after entry fill
- Entry filled but no child orders detected
- One OCO leg cancelled unexpectedly

**Warning Alerts**:
- OCO order rejected by broker
- Profit target too close to entry (< 10%)
- Stop loss too far from entry (> 100%)

**Info Logs**:
- OCO orders placed successfully
- OCO leg filled (profit vs stop)
- Fallback to engine monitoring (if OCO failed)

## Example Implementation

```python
# In OrderManager

def submit_position_entry_with_oco(
    self,
    position: OptionsPosition,
    options_data: Dict,
    strategy_name: str
) -> Tuple[bool, str, Optional[Order]]:
    """Submit entry order with OCO profit target and stop loss."""

    # Calculate entry price
    entry_price = self._calculate_expected_price(position.legs, options_data)

    # Calculate OCO exit prices
    profit_price = entry_price * (1 + position.profit_target)
    stop_price = entry_price * (1 + position.stop_loss)  # stop_loss is negative

    # Build OCO children
    oco_children = self._build_oco_children(
        position=position,
        profit_price=profit_price,
        stop_price=stop_price
    )

    # Create order with children
    order = self._create_order_with_oco(
        position=position,
        entry_price=entry_price,
        oco_children=oco_children
    )

    if self.paper_trading:
        # Simulated mode: still just simulate entry, monitor exits manually
        return self._simulate_fill(order, options_data)
    else:
        # Live mode: submit to Schwab with OCO
        return self._submit_to_schwab_with_oco(order)
```

## Success Metrics

**Phase 1 (Construction)**:
- OCO orders constructed correctly 100% of time
- Price calculations match expected
- Database tracking works

**Phase 2 (Live Mode)**:
- 95%+ OCO placement success rate
- Zero missed stop losses due to OCO failure
- Faster exit execution vs manual monitoring

**Phase 3 (Full Deployment)**:
- All positions protected by OCO
- Engine survives crashes without loss of protection
- Better risk-adjusted returns due to consistent protection

## Timeline

- **Week 1**: Design and unit tests (OCO construction)
- **Week 2**: Simulated mode integration (log OCO structures)
- **Week 3**: Live mode implementation (Schwab API)
- **Week 4**: Small live test (1-2 positions)
- **Week 5**: Full rollout and monitoring

## Next Steps

1. Review and approve this integration plan
2. Decide: Full OCO vs Hybrid approach?
3. Implement Phase 1 (order construction)
4. Test in simulated mode
5. Small live test before full rollout

---

**Status**: 📋 Design Complete - Awaiting Implementation
**Priority**: 🔴 High (Risk Protection)
**Complexity**: 🟡 Medium
**Risk**: 🟢 Low (Improves safety)
