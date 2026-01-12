"""
Simple test for live Schwab order submission.

Tests basic order submission with hardcoded, safe parameters.
Order will submit but never fill (price = $0.01).
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from quant_vibe.data.schwab_dev_client import SchwabDevClient
from quant_vibe.strategies.options_base import OptionsPosition, OptionLeg, OptionType, SpreadType
from quant_vibe.utils import now_utc, ensure_utc_aware
from live_trading_service.order_manager import OrderManager


def main():
    print("\n" + "="*60)
    print("SIMPLE SCHWAB ORDER TEST")
    print("="*60)

    # YOU MUST UPDATE THESE VALUES MANUALLY:
    TEST_SYMBOL = "SPXW  250117C06050000"  # Update with actual symbol
    TEST_STRIKE = 6050.0                    # Update with actual strike
    TEST_EXPIRATION = "2025-01-17"          # Update with actual expiration
    TEST_UNDERLYING_PRICE = 6000.0          # Update with current SPX price

    print(f"\nTest parameters:")
    print(f"  Symbol: {TEST_SYMBOL}")
    print(f"  Strike: ${TEST_STRIKE}")
    print(f"  Expiration: {TEST_EXPIRATION}")
    print(f"  Underlying: ${TEST_UNDERLYING_PRICE}")
    print(f"  Price: $0.01 (NEVER FILLS)")

    confirm = input("\n⚠️  This submits a REAL order. Continue? (yes/no): ")
    if confirm.lower() != 'yes':
        print("Cancelled.")
        return

    # Initialize clients
    print("\nInitializing...")
    schwab_client = SchwabDevClient()
    order_manager = OrderManager(
        paper_trading=False,  # LIVE MODE
        schwab_client=schwab_client,
        state_store=None
    )

    # Create test position
    exp_date = ensure_utc_aware(datetime.strptime(TEST_EXPIRATION, "%Y-%m-%d"))
    leg = OptionLeg(
        contract_symbol=TEST_SYMBOL,
        option_type=OptionType.CALL,
        strike_price=TEST_STRIKE,
        expiration_date=exp_date,
        quantity=1,
        entry_price=0.01
    )

    position = OptionsPosition(
        position_id=f"TEST_{now_utc().strftime('%Y%m%d_%H%M%S')}",
        spread_type=SpreadType.SINGLE,  # Single leg position
        legs=[leg],
        entry_time=now_utc(),
        entry_cost=1.0,  # $0.01 per share * 100 shares = $1.00
        underlying_price_at_entry=TEST_UNDERLYING_PRICE,
        profit_target_pct=0.50  # 50% profit target
    )

    # Mock options data
    # IMPORTANT: Use $0.01 to ensure order never fills
    options_data = {
        TEST_SYMBOL: {
            'symbol': TEST_SYMBOL,
            'bid': 0.01,  # $0.01 ensures no fill
            'ask': 0.01,  # $0.01 ensures no fill
            'last': 0.01
        }
    }

    # Submit order
    print("\nSubmitting order...")
    success, message, order = order_manager.submit_position_entry(
        position=position,
        options_data=options_data,
        strategy_name="simple_test"
    )

    if success:
        print(f"\n✓ SUCCESS!")
        print(f"  Order ID: {order.order_id}")
        print(f"  Broker ID: {order.broker_order_id}")
        print(f"  Status: {order.status.value}")

        # Cancel?
        cancel = input("\nCancel order? (yes/no): ")
        if cancel.lower() == 'yes':
            success, msg = order_manager.cancel_order(order.order_id)
            print(f"\n{'✓' if success else '✗'} {msg}")
        else:
            print(f"\n⚠️  MANUALLY CANCEL: Broker ID {order.broker_order_id}")
    else:
        print(f"\n✗ FAILED: {message}")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    main()
