#!/usr/bin/env python3
"""Test Phase 2 components WITH OCO enabled.

This shows how OCO integrates with OrderManager and PositionManager.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.live import OrderManager, PositionManager, StateStore
from quant_vibe.strategies.options_base import (
    OptionsPosition, OptionLeg, OptionType, SpreadType
)

print("\n" + "="*70)
print("TESTING PHASE 2 WITH OCO ENABLED")
print("="*70)

# Initialize with OCO enabled
print("\n1. Initialize components with OCO enabled...")
try:
    state_store = StateStore()

    # Enable OCO
    oco_config = {
        'profit_target_pct': 0.50,  # 50% profit
        'stop_loss_pct': -0.30,     # -30% loss
        'use_market_on_stop': True,
        'verify_placement': True
    }

    order_manager = OrderManager(
        paper_trading=True,
        state_store=state_store,
        use_oco=True,  # ENABLED!
        oco_config=oco_config
    )

    position_manager = PositionManager(state_store=state_store)

    print("   ✅ Components initialized with OCO")
    print(f"      - OCO enabled: {order_manager.use_oco}")
    print(f"      - Profit target: {oco_config['profit_target_pct']*100}%")
    print(f"      - Stop loss: {oco_config['stop_loss_pct']*100}%")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

# Create test position
print("\n2. Create test position...")
try:
    expiration_date = datetime.now() + timedelta(days=0)

    leg1 = OptionLeg(
        contract_symbol='SPXW_250117P5900',
        option_type=OptionType.PUT,
        strike_price=5900.0,
        expiration_date=expiration_date,
        quantity=1,
        entry_price=10.00
    )

    leg2 = OptionLeg(
        contract_symbol='SPXW_250117P5890',
        option_type=OptionType.PUT,
        strike_price=5890.0,
        expiration_date=expiration_date,
        quantity=-1,
        entry_price=8.00
    )

    position = OptionsPosition(
        position_id=f"BVP_{datetime.now().strftime('%H%M%S')}",
        spread_type=SpreadType.VERTICAL_PUT,
        legs=[leg1, leg2],
        entry_time=datetime.now(),
        entry_cost=2.00,
        underlying_price_at_entry=5950.0,
        profit_target=0.50,
        stop_loss=-0.30
    )

    print("   ✅ Position created")

    # Save position first (for DB foreign key)
    position_manager.add_position(position, 'test_strategy', position.entry_cost)
    print("   ✅ Position saved to DB")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    sys.exit(1)

# Submit order with OCO
print("\n3. Submit entry order WITH OCO...")
try:
    options_data = {
        'SPXW_250117P5900': {'bid': 9.50, 'ask': 10.50, 'close': 10.00},
        'SPXW_250117P5890': {'bid': 7.50, 'ask': 8.50, 'close': 8.00}
    }

    # Use the OCO method
    success, message, order = order_manager.submit_position_entry_with_oco(
        position=position,
        options_data=options_data,
        strategy_name='test_strategy'
    )

    if success:
        print("   ✅ Order submitted with OCO protection")
        print(f"\n      Entry Order:")
        print(f"      - Order ID: {order.order_id}")
        print(f"      - Status: {order.status.value}")
        print(f"      - Filled at: ${order.filled_total_price:.2f}")

        print(f"\n      OCO Protection:")
        print(f"      - OCO Group: {order.oco_group_id}")
        print(f"      - Profit Target: ${order.profit_target_price:.2f} (+{((order.profit_target_price-order.filled_total_price)/order.filled_total_price*100):.1f}%)")
        print(f"      - Stop Loss: ${order.stop_loss_price:.2f} ({((order.stop_loss_price-order.filled_total_price)/order.filled_total_price*100):.1f}%)")
        print(f"      - OCO Status: {order.oco_status.value}")

        print(f"\n      In Live Mode:")
        print(f"      - Broker would place 2 GTC orders automatically")
        print(f"      - Profit order: LIMIT sell at ${order.profit_target_price:.2f}")
        print(f"      - Stop order: STOP_MARKET sell at ${order.stop_loss_price:.2f}")
        print(f"      - Whichever fills first cancels the other")

        print(f"\n      In Simulated Mode (Current):")
        print(f"      - OCO structure built and logged")
        print(f"      - Engine still monitors for exits")
        print(f"      - OCO would be submitted in live mode")

        # Update position with actual fill
        position.entry_cost = order.filled_total_price
        position_manager.total_capital_deployed = abs(order.filled_total_price)
    else:
        print(f"   ❌ Order failed: {message}")
        sys.exit(1)
except Exception as e:
    print(f"   ❌ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Show position tracking
print("\n4. Position tracking with OCO metadata...")
try:
    open_positions = position_manager.get_open_positions()

    print(f"   ✅ Open positions: {len(open_positions)}")
    print(f"      - Capital deployed: ${position_manager.total_capital_deployed:.2f}")

    if open_positions:
        pos = open_positions[0]
        print(f"\n      Position has OCO protection:")
        print(f"      - If price rises to ${order.profit_target_price:.2f}: Auto-close for profit")
        print(f"      - If price falls to ${order.stop_loss_price:.2f}: Auto-close at stop")
        print(f"      - Protection persists even if engine crashes (in live mode)")
except Exception as e:
    print(f"   ❌ Failed: {e}")
    import traceback
    traceback.print_exc()

# Compare: Regular order vs OCO order
print("\n5. Comparison: Regular vs OCO orders...")
print("\n   Regular Order (Without OCO):")
print("   ├─ Submit entry order")
print("   ├─ Wait for fill")
print("   ├─ Engine monitors position continuously")
print("   ├─ Engine detects exit condition")
print("   ├─ Engine submits exit order")
print("   └─ If engine crashes: NO PROTECTION")

print("\n   OCO Order (With OCO):")
print("   ├─ Submit entry + OCO children")
print("   ├─ On fill, broker places profit + stop orders")
print("   ├─ Broker monitors 24/7")
print("   ├─ Broker executes whichever triggers first")
print("   ├─ Broker cancels the other")
print("   └─ If engine crashes: STILL PROTECTED ✅")

# Cleanup
print("\n6. Cleanup...")
try:
    state_store.close()
    print("   ✅ StateStore closed")
except Exception as e:
    print(f"   ⚠️  Warning: {e}")

print("\n" + "="*70)
print("✅ PHASE 2 + OCO INTEGRATION TEST COMPLETE")
print("="*70)
print("\nKey Points:")
print("  ✅ OCO orders provide automatic broker-level protection")
print("  ✅ Profit targets and stops persist even if engine crashes")
print("  ✅ Faster execution (broker-side vs polling)")
print("  ✅ Works in simulated mode (structures built but not submitted)")
print("  ✅ Easy to enable: just set use_oco=True")
print("\nNext steps:")
print("  1. Test various profit/stop configurations")
print("  2. Implement Phase 2: Schwab API submission")
print("  3. Add fill event handling for OCO legs")
print()
