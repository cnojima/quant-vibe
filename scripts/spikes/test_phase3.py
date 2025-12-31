#!/usr/bin/env python3
"""
Test Phase 3: Strategy Integration

Tests the StrategyExecutor and strategy loading system.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import pytz

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.live.state_store import StateStore
from quant_vibe.live.order_manager import OrderManager
from quant_vibe.live.position_manager import PositionManager
from quant_vibe.live.strategy_executor import StrategyExecutor
from quant_vibe.live.strategy_loader import StrategyLoader
from quant_vibe.strategies.bullish_vertical_put import BullishVerticalPutStrategy

print("="*70)
print("TESTING PHASE 3 COMPONENTS")
print("="*70)
print()

# ============================================================================
# Test 1: Strategy Loading
# ============================================================================
print("1. Testing strategy loading...")
try:
    # Test configuration
    config = {
        'strategies': {
            'enabled': [
                {
                    'name': 'bullish_vertical_put',
                    'enabled': True,
                    'params': {
                        'spread_width': 10.0,
                        'observation_period': 30,
                        'pullback_amount': 50.0,
                        'profit_target_min': 0.5,
                        'profit_target_max': 1.0,
                        'trailing_stop_pct': 0.05,
                        'min_dte': 0,
                        'max_dte': 45,
                        'num_spreads': 10,
                        'min_volume': 50,
                        'min_bid_ask_spread_pct': 10.0,
                    }
                }
            ]
        }
    }

    strategies = StrategyLoader.load_strategies(config)

    print(f"   ✅ Loaded {len(strategies)} strategies")
    for strategy in strategies:
        print(f"      - {strategy.name}")

except Exception as e:
    print(f"   ❌ Strategy loading failed: {e}")
    sys.exit(1)

# ============================================================================
# Test 2: StrategyExecutor Initialization
# ============================================================================
print()
print("2. Testing StrategyExecutor initialization...")
try:
    # Initialize components
    state_store = StateStore()
    order_manager = OrderManager(
        schwab_client=None,  # Not needed for test
        state_store=state_store,
        paper_trading=True,
    )
    position_manager = PositionManager(
        state_store=state_store,
    )

    # Create executor
    executor = StrategyExecutor(
        strategies=strategies,
        order_manager=order_manager,
        position_manager=position_manager,
        state_store=state_store,
        underlying_ticker="SPX",
        enabled=True,
    )

    print(f"   ✅ StrategyExecutor initialized")
    print(f"      - Strategies: {len(executor.strategies)}")
    print(f"      - Enabled: {executor.enabled}")

except Exception as e:
    print(f"   ❌ StrategyExecutor initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# Test 3: Create mock market data
# ============================================================================
print()
print("3. Creating mock market data...")
try:
    # Create mock underlying data
    et_tz = pytz.timezone('America/New_York')
    utc_tz = pytz.UTC

    # Start time: 9:30 AM ET (market open)
    start_time_et = et_tz.localize(datetime.now().replace(hour=9, minute=30, second=0, microsecond=0))
    start_time_utc = start_time_et.astimezone(utc_tz)

    # Create 1 hour of 1-minute bars
    timestamps = [start_time_utc + timedelta(minutes=i) for i in range(60)]

    # Simulate price movement: opens high, pulls back
    base_price = 6000.0
    prices = []
    for i in range(60):
        if i < 30:
            # Opening rally
            price = base_price + (i * 2)  # Goes up to 6060
        else:
            # Pullback
            price = 6060 - ((i - 30) * 3)  # Pulls back
        prices.append(price)

    underlying_data = pd.DataFrame({
        'Open': prices,
        'High': [p + 2 for p in prices],
        'Low': [p - 2 for p in prices],
        'Close': prices,
        'Volume': [1000000] * 60,
    }, index=timestamps)

    # Create mock options data
    current_time = timestamps[-1]
    current_price = prices[-1]

    # Create some put options around current price
    strikes = [current_price - 20, current_price - 10, current_price, current_price + 10, current_price + 20]
    expiration_date = pd.Timestamp((datetime.now() + timedelta(days=30)).date())

    options_rows = []
    for strike in strikes:
        # Put option
        options_rows.append({
            'contract_symbol': f'SPXW_{strike}P',
            'option_type': 'P',
            'strike_price': strike,
            'expiration_date': expiration_date,
            'bid': 5.0,
            'ask': 5.5,
            'mark': 5.25,
            'volume': 100,
            'open_interest': 500,
        })

    options_data = pd.DataFrame(options_rows)

    print(f"   ✅ Mock data created")
    print(f"      - Underlying bars: {len(underlying_data)}")
    print(f"      - Price range: ${underlying_data['Close'].min():.2f} - ${underlying_data['Close'].max():.2f}")
    print(f"      - Current price: ${current_price:.2f}")
    print(f"      - Options contracts: {len(options_data)}")

except Exception as e:
    print(f"   ❌ Mock data creation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# Test 4: Execute strategy on mock data
# ============================================================================
print()
print("4. Testing strategy execution...")
try:
    # Execute strategy at current time
    print(f"   Executing at {current_time}")

    executor.on_bar(
        underlying_data=underlying_data,
        options_data=options_data,
        current_time=current_time,
    )

    print(f"   ✅ Strategy executed")

    # Check for positions
    active_positions = executor.get_active_positions()
    print(f"      - Active positions: {len(active_positions)}")

    # Check stats
    stats = executor.get_strategy_stats()
    for strategy_name, strategy_stats in stats.items():
        print(f"\n      Strategy: {strategy_name}")
        print(f"        Opened: {strategy_stats['positions_opened']}")
        print(f"        Closed: {strategy_stats['positions_closed']}")
        print(f"        Wins: {strategy_stats['wins']}")
        print(f"        Losses: {strategy_stats['losses']}")

except Exception as e:
    print(f"   ❌ Strategy execution failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# Test 5: Test daily reset
# ============================================================================
print()
print("5. Testing daily reset...")
try:
    # Save last reset date
    last_reset = executor.last_reset_date

    # Trigger reset (simulate next day)
    next_day = datetime.now().date() + timedelta(days=1)
    executor._perform_daily_reset(next_day)

    print(f"   ✅ Daily reset executed")
    print(f"      - Last reset: {last_reset}")
    print(f"      - New reset: {executor.last_reset_date}")

    # Verify strategies were reset
    for strategy in strategies:
        assert strategy.observation_complete == False
        assert strategy.has_traded_today == False

    print(f"      - Strategy states reset: ✅")

except Exception as e:
    print(f"   ❌ Daily reset failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ============================================================================
# Test 6: Test enable/disable
# ============================================================================
print()
print("6. Testing enable/disable...")
try:
    # Disable
    executor.disable()
    assert executor.enabled == False
    print(f"   ✅ Executor disabled")

    # Enable
    executor.enable()
    assert executor.enabled == True
    print(f"   ✅ Executor enabled")

except Exception as e:
    print(f"   ❌ Enable/disable failed: {e}")
    sys.exit(1)

# ============================================================================
# Cleanup
# ============================================================================
print()
print("7. Cleanup...")
try:
    state_store.close()
    print("   ✅ StateStore closed")
except Exception as e:
    print(f"   ⚠️  Cleanup warning: {e}")

# ============================================================================
# Summary
# ============================================================================
print()
print("="*70)
print("✅ PHASE 3 TESTS COMPLETE")
print("="*70)
print()
print("All Phase 3 components working correctly!")
print("Components tested:")
print("  ✅ StrategyLoader (dynamic strategy loading)")
print("  ✅ StrategyExecutor (strategy execution orchestration)")
print("  ✅ Strategy execution on market data")
print("  ✅ Daily state reset")
print("  ✅ Enable/disable controls")
print()
print("Next steps:")
print("  1. Test with live streaming data")
print("  2. Implement Phase 4 (Risk Management)")
print("  3. Add monitoring and alerts (Phase 5)")
