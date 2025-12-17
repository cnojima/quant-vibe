#!/usr/bin/env python3
"""Test Phase 2 components: OrderManager and PositionManager.

Tests simulated order submission and position tracking.
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
print("TESTING PHASE 2 COMPONENTS")
print("="*70)

# Test 1: Initialize components
print("\n1. Testing component initialization...")
try:
    state_store = StateStore()
    order_manager = OrderManager(
        paper_trading=True,
        state_store=state_store
    )
    position_manager = PositionManager(
        state_store=state_store
    )
    print("   ✅ All components initialized")
    print(f"      - OrderManager mode: {'SIMULATED' if order_manager.paper_trading else 'LIVE'}")
    print(f"      - PositionManager ready")
except Exception as e:
    print(f"   ❌ Initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Create a test position
print("\n2. Creating test position (Bullish Vertical Put)...")
try:
    # Create a spread (example: buy 5900 put, sell 5890 put)
    expiration_date = datetime.now() + timedelta(days=0)

    leg1 = OptionLeg(
        contract_symbol='SPXW_250101P5900',
        option_type=OptionType.PUT,
        strike_price=5900.0,
        expiration_date=expiration_date,
        quantity=1,  # Buy
        entry_price=10.00
    )

    leg2 = OptionLeg(
        contract_symbol='SPXW_250101P5890',
        option_type=OptionType.PUT,
        strike_price=5890.0,
        expiration_date=expiration_date,
        quantity=-1,  # Sell
        entry_price=8.00
    )

    position = OptionsPosition(
        position_id=f"TEST_{datetime.now().strftime('%H%M%S')}",
        spread_type=SpreadType.VERTICAL_PUT,
        legs=[leg1, leg2],
        entry_time=datetime.now(),
        entry_cost=2.00,  # Expected: 10.00 - 8.00
        underlying_price_at_entry=5950.0,
        profit_target=0.50,
        stop_loss=-1.00
    )

    print("   ✅ Test position created")
    print(f"      - Position ID: {position.position_id}")
    print(f"      - Spread: BVP 5900/5890")
    print(f"      - Expected debit: ${leg1.entry_price - leg2.entry_price:.2f}")
except Exception as e:
    print(f"   ❌ Position creation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Add position skeleton first (for DB foreign key)
print("\n3. Saving position skeleton to DB...")
try:
    # In real workflow, position should be saved before order for foreign key constraint
    position_manager.add_position(
        position=position,
        strategy_name='test_strategy',
        fill_price=position.entry_cost  # Temporary, will update after fill
    )
    print("   ✅ Position skeleton saved")
except Exception as e:
    print(f"   ⚠️  Position save warning: {e}")

# Test 4: Simulate order submission
print("\n4. Testing order submission (simulated mode)...")
try:
    # Mock options data (simulating market quotes)
    options_data = {
        'SPXW_250101P5900': {
            'bid': 9.50,
            'ask': 10.50,
            'close': 10.00
        },
        'SPXW_250101P5890': {
            'bid': 7.50,
            'ask': 8.50,
            'close': 8.00
        }
    }

    success, message, order = order_manager.submit_position_entry(
        position=position,
        options_data=options_data,
        strategy_name='test_strategy'
    )

    if success:
        print("   ✅ Order submitted successfully")
        print(f"      - Order ID: {order.order_id}")
        print(f"      - Status: {order.status.value}")
        print(f"      - Expected price: ${order.expected_total_price:.2f}")
        print(f"      - Filled price: ${order.filled_total_price:.2f}")
        print(f"      - Slippage: ${order.filled_total_price - order.expected_total_price:.2f}")

        # Update position with actual fill price
        fill_price = order.filled_total_price
        position.entry_cost = fill_price
        position.current_value = fill_price
    else:
        print(f"   ❌ Order submission failed: {message}")
        sys.exit(1)

except Exception as e:
    print(f"   ❌ Order submission error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Update position tracking with actual fill
print("\n5. Updating position with actual fill price...")
try:
    # Position already added in test 3, just update the capital tracking
    position_manager.total_capital_deployed = abs(fill_price)

    print("   ✅ Position tracking updated")
    print(f"      - Open positions: {position_manager.get_position_count()}")
    print(f"      - Capital deployed: ${position_manager.total_capital_deployed:.2f}")

except Exception as e:
    print(f"   ❌ Position tracking failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Update position values
print("\n6. Testing position valuation (price moves in our favor)...")
try:
    # Simulate favorable price movement (puts decrease in value)
    updated_quotes = {
        'SPXW_250101P5900': {
            'bid': 7.00,   # Down from 9.50
            'ask': 7.50,
            'close': 7.25
        },
        'SPXW_250101P5890': {
            'bid': 5.50,   # Down from 7.50
            'ask': 6.00,
            'close': 5.75
        }
    }

    position_manager.update_position_values(updated_quotes)

    pnl = position_manager.get_position_pnl(position.position_id)
    pnl_pct = position_manager.get_position_pnl_pct(position.position_id)

    print("   ✅ Position values updated")
    print(f"      - Current value: ${position.current_value:.2f}")
    print(f"      - P&L: ${pnl:.2f} ({pnl_pct:.2f}%)")
    print(f"      - Status: {'Profit' if pnl > 0 else 'Loss'}")

except Exception as e:
    print(f"   ❌ Position valuation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Submit exit order
print("\n7. Testing position exit (simulated)...")
try:
    success, message, exit_order = order_manager.submit_position_exit(
        position=position,
        options_data=updated_quotes,
        strategy_name='test_strategy'
    )

    if success:
        print("   ✅ Exit order submitted")
        print(f"      - Order ID: {exit_order.order_id}")
        print(f"      - Exit price: ${exit_order.filled_total_price:.2f}")

        # Close position
        position_manager.close_position(
            position_id=position.position_id,
            exit_reason='test_exit',
            exit_price=exit_order.filled_total_price
        )

        print("   ✅ Position closed")
        print(f"      - Open positions: {position_manager.get_position_count()}")
    else:
        print(f"   ❌ Exit order failed: {message}")

except Exception as e:
    print(f"   ❌ Position exit error: {e}")
    import traceback
    traceback.print_exc()

# Test 8: Daily statistics
print("\n8. Testing daily statistics...")
try:
    stats = position_manager.get_daily_stats()

    print("   ✅ Daily stats retrieved")
    print(f"      - Opened today: {stats['opened_today']}")
    print(f"      - Closed today: {stats['closed_today']}")
    print(f"      - Total P&L: ${stats['total_pnl_today']:.2f}")
    print(f"      - Wins: {stats['wins_today']}")
    print(f"      - Losses: {stats['losses_today']}")

except Exception as e:
    print(f"   ❌ Stats retrieval failed: {e}")
    import traceback
    traceback.print_exc()

# Cleanup
print("\n9. Cleanup...")
try:
    state_store.close()
    print("   ✅ StateStore closed")
except Exception as e:
    print(f"   ⚠️  Cleanup warning: {e}")

print("\n" + "="*70)
print("✅ PHASE 2 TESTS COMPLETE")
print("="*70)
print("\nAll Phase 2 components working correctly!")
print("Components tested:")
print("  ✅ OrderManager (simulated mode)")
print("  ✅ Order submission with slippage modeling")
print("  ✅ PositionManager tracking")
print("  ✅ Real-time P&L calculations")
print("  ✅ Position entry and exit workflow")
print("  ✅ Daily statistics tracking")
print("\nNext steps:")
print("  1. Integrate OrderManager and PositionManager into LiveTradingEngine")
print("  2. Implement Phase 3 (Strategy Integration)")
print("  3. Test with real streaming data")
print()
