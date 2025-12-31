#!/usr/bin/env python3
"""Test OCO (One Cancels Other) order construction.

Tests Phase 1 of OCO integration: order structure construction.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.live import OrderManager, StateStore, OCOStatus
from quant_vibe.strategies.options_base import (
    OptionsPosition, OptionLeg, OptionType, SpreadType
)

print("\n" + "="*70)
print("TESTING OCO ORDER CONSTRUCTION (Phase 1)")
print("="*70)

# Test 1: Initialize OrderManager with OCO enabled
print("\n1. Initialize OrderManager with OCO...")
try:
    state_store = StateStore()

    # Enable OCO with custom config
    oco_config = {
        'profit_target_pct': 0.60,  # 60% profit target
        'stop_loss_pct': -0.25,     # -25% stop loss
        'use_market_on_stop': True,
        'verify_placement': True
    }

    order_manager = OrderManager(
        paper_trading=True,
        state_store=state_store,
        use_oco=True,
        oco_config=oco_config
    )

    print("   ✅ OrderManager initialized with OCO")
    print(f"      - OCO enabled: {order_manager.use_oco}")
    print(f"      - Profit target: {oco_config['profit_target_pct']*100}%")
    print(f"      - Stop loss: {oco_config['stop_loss_pct']*100}%")

except Exception as e:
    print(f"   ❌ Initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Create test position
print("\n2. Create test position (Bullish Vertical Put)...")
try:
    expiration_date = datetime.now() + timedelta(days=0)  # 0 DTE

    leg1 = OptionLeg(
        contract_symbol='SPXW_250117P5900',
        option_type=OptionType.PUT,
        strike_price=5900.0,
        expiration_date=expiration_date,
        quantity=1,  # Buy
        entry_price=10.00
    )

    leg2 = OptionLeg(
        contract_symbol='SPXW_250117P5890',
        option_type=OptionType.PUT,
        strike_price=5890.0,
        expiration_date=expiration_date,
        quantity=-1,  # Sell
        entry_price=8.00
    )

    position = OptionsPosition(
        position_id=f"OCO_TEST_{datetime.now().strftime('%H%M%S')}",
        spread_type=SpreadType.VERTICAL_PUT,
        legs=[leg1, leg2],
        entry_time=datetime.now(),
        entry_cost=2.00,  # Expected: 10.00 - 8.00
        underlying_price_at_entry=5950.0,
        profit_target=0.50,  # 50% profit target (will be overridden by OCO config)
        stop_loss=-0.30      # -30% stop loss
    )

    print("   ✅ Test position created")
    print(f"      - Position ID: {position.position_id}")
    print(f"      - Spread: BVP 5900/5890")
    print(f"      - Expected entry: $2.00 debit")

except Exception as e:
    print(f"   ❌ Position creation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Test OCO price calculation
print("\n3. Test OCO exit price calculation...")
try:
    entry_price = 2.00

    profit_price, stop_price = order_manager._calculate_oco_exit_prices(
        position, entry_price
    )

    print("   ✅ OCO prices calculated")
    print(f"      - Entry price: ${entry_price:.2f}")
    print(f"      - Profit target: ${profit_price:.2f} ({((profit_price-entry_price)/entry_price*100):.1f}%)")
    print(f"      - Stop loss: ${stop_price:.2f} ({((stop_price-entry_price)/entry_price*100):.1f}%)")

    # Verify calculations (position has 50% profit, -30% stop, overriding OCO config)
    # OCO uses position's targets if defined, otherwise uses config defaults
    expected_profit = entry_price * (1 + position.profit_target)  # 50%
    expected_stop = entry_price * (1 + position.stop_loss)        # -30%

    assert abs(profit_price - expected_profit) < 0.01, "Profit price mismatch"
    assert abs(stop_price - expected_stop) < 0.01, "Stop price mismatch"

    print("      - ✓ Calculations verified (using position's targets)")
    print("      - Note: Position targets override OCO config defaults")

except Exception as e:
    print(f"   ❌ Price calculation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Test OCO children construction
print("\n4. Test OCO child order construction...")
try:
    oco_children = order_manager._build_oco_children(
        position, profit_price, stop_price
    )

    print("   ✅ OCO children constructed")
    print(f"      - Number of children: {len(oco_children)}")

    # Validate profit child
    profit_child = oco_children[0]
    print(f"\n      Profit Target Child:")
    print(f"      - Order ID: {profit_child['order_id']}")
    print(f"      - Order type: {profit_child['order_type']}")
    print(f"      - Price: ${profit_child['price']:.2f}")
    print(f"      - Duration: {profit_child['duration']}")
    print(f"      - Legs: {len(profit_child['legs'])}")

    # Validate stop child
    stop_child = oco_children[1]
    print(f"\n      Stop Loss Child:")
    print(f"      - Order ID: {stop_child['order_id']}")
    print(f"      - Order type: {stop_child['order_type']}")
    print(f"      - Stop price: ${stop_child['stop_price']:.2f}")
    print(f"      - Duration: {stop_child['duration']}")
    print(f"      - Legs: {len(stop_child['legs'])}")

    # Verify leg instructions are reversed (SELL_TO_CLOSE and BUY_TO_CLOSE)
    for child in oco_children:
        for leg in child['legs']:
            assert leg['instruction'] in ['SELL_TO_CLOSE', 'BUY_TO_CLOSE'], \
                f"Invalid instruction: {leg['instruction']}"

    print("\n      - ✓ OCO children validated")

except Exception as e:
    print(f"   ❌ OCO construction failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Test full Schwab OCO structure
print("\n5. Test Schwab API OCO structure construction...")
try:
    # Create a mock entry order
    from quant_vibe.live.order_manager import Order

    entry_order = Order(
        order_id='TEST_ENTRY_001',
        position_id=position.position_id,
        strategy_name='test_strategy',
        legs=[
            {
                'symbol': 'SPXW_250117P5900',
                'quantity': 1,
                'side': 'buy'
            },
            {
                'symbol': 'SPXW_250117P5890',
                'quantity': 1,
                'side': 'sell'
            }
        ]
    )
    entry_order.expected_total_price = 2.00

    schwab_structure = order_manager._build_schwab_oco_structure(
        entry_order, oco_children
    )

    print("   ✅ Schwab OCO structure built")
    print(f"      - Order strategy type: {schwab_structure['orderStrategyType']}")
    print(f"      - Entry legs: {len(schwab_structure['orderLegCollection'])}")
    print(f"      - Has child strategies: {len(schwab_structure['childOrderStrategies'])}")

    # Pretty print the structure
    print("\n      Full Schwab OCO Structure:")
    print("      " + "-"*60)
    print(json.dumps(schwab_structure, indent=6))
    print("      " + "-"*60)

    # Validate structure
    assert schwab_structure['orderStrategyType'] == 'TRIGGER', "Must be TRIGGER order"
    assert len(schwab_structure['childOrderStrategies']) == 1, "Must have 1 OCO strategy"
    assert schwab_structure['childOrderStrategies'][0]['orderStrategyType'] == 'OCO', "Must be OCO"
    assert len(schwab_structure['childOrderStrategies'][0]['childOrderStrategies']) == 2, "Must have 2 OCO children"

    print("\n      - ✓ Schwab structure validated")

except Exception as e:
    print(f"   ❌ Schwab structure construction failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Test full order submission with OCO
print("\n6. Test order submission with OCO (simulated mode)...")
try:
    # Mock options data
    options_data = {
        'SPXW_250117P5900': {
            'bid': 9.50,
            'ask': 10.50,
            'close': 10.00
        },
        'SPXW_250117P5890': {
            'bid': 7.50,
            'ask': 8.50,
            'close': 8.00
        }
    }

    success, message, order = order_manager.submit_position_entry_with_oco(
        position=position,
        options_data=options_data,
        strategy_name='test_strategy'
    )

    if success:
        print("   ✅ Order submitted with OCO")
        print(f"      - Order ID: {order.order_id}")
        print(f"      - Status: {order.status.value}")
        print(f"      - Entry price: ${order.filled_total_price:.2f}")
        print(f"      - Has OCO children: {order.has_oco_children}")
        print(f"      - OCO group ID: {order.oco_group_id}")
        print(f"      - Profit target order ID: {order.profit_target_order_id}")
        print(f"      - Stop loss order ID: {order.stop_loss_order_id}")
        print(f"      - Profit target price: ${order.profit_target_price:.2f}")
        print(f"      - Stop loss price: ${order.stop_loss_price:.2f}")
        print(f"      - OCO status: {order.oco_status.value if order.oco_status else 'N/A'}")

        # Verify OCO metadata
        assert order.has_oco_children, "Order should have OCO children"
        assert order.oco_group_id is not None, "OCO group ID should be set"
        assert order.profit_target_order_id is not None, "Profit target order ID should be set"
        assert order.stop_loss_order_id is not None, "Stop loss order ID should be set"
        assert order.oco_status == OCOStatus.PENDING, "OCO status should be PENDING"

        print("\n      - ✓ OCO metadata validated")
    else:
        print(f"   ❌ Order submission failed: {message}")
        sys.exit(1)

except Exception as e:
    print(f"   ❌ Order submission error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Verify OCO structure was logged
print("\n7. Verify OCO structure logging...")
try:
    assert order.oco_children is not None, "OCO children should be stored"
    assert len(order.oco_children) >= 2, "Should have at least 2 OCO children"

    print("   ✅ OCO structure logged")
    print(f"      - OCO children stored: {len(order.oco_children)}")
    print(f"      - Schwab format included: {'schwab_format' in str(order.oco_children)}")

    print("\n      Note: In simulated mode, OCO structure is built and logged")
    print("      but not submitted to broker. Engine monitoring is still used.")

except Exception as e:
    print(f"   ❌ Verification failed: {e}")
    import traceback
    traceback.print_exc()

# Cleanup
print("\n8. Cleanup...")
try:
    state_store.close()
    print("   ✅ StateStore closed")
except Exception as e:
    print(f"   ⚠️  Cleanup warning: {e}")

print("\n" + "="*70)
print("✅ OCO CONSTRUCTION TESTS COMPLETE (Phase 1)")
print("="*70)
print("\nAll OCO construction components working correctly!")
print("\nTested:")
print("  ✅ OCO price calculation (profit target & stop loss)")
print("  ✅ OCO child order construction")
print("  ✅ Schwab API OCO structure formatting")
print("  ✅ Order submission with OCO metadata")
print("  ✅ OCO structure logging for inspection")
print("\nStatus:")
print("  📋 Phase 1 Complete: OCO structure construction")
print("  🔜 Phase 2: Live mode Schwab API integration")
print("  🔜 Phase 3: OCO fill event handling")
print("\nNext steps:")
print("  1. Review logged OCO structures")
print("  2. Integrate with LiveTradingEngine")
print("  3. Implement Phase 2 (Schwab API submission)")
print()
