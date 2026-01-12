#!/usr/bin/env python3
"""
Test live Schwab order submission with a never-fillable order.

This script tests the Schwab API order submission logic by placing an order
that will submit successfully but never fill (buy at $0.01).

IMPORTANT: This places REAL orders to Schwab, but with prices that will never fill.
The order should be cancelled at the end, but verify in your broker account.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from quant_vibe.data.schwab_dev_client import SchwabDevClient
from quant_vibe.strategies.options_base import OptionsPosition, OptionLeg, OptionType, SpreadType
from quant_vibe.utils import now_utc, ensure_utc_aware
from live_trading_service.order_manager import OrderManager


def get_spxw_chain_data(schwab_client: SchwabDevClient, target_date: datetime) -> Dict:
    """
    Get SPX option chain for a specific date.

    Args:
        schwab_client: Schwab API client
        target_date: Target expiration date

    Returns:
        Option chain data
    """
    print(f"Fetching SPX option chain for {target_date.date()}...")

    # Schwab uses $SPX for index options
    response = schwab_client.client.option_chains(
        "$SPX",
        contractType="CALL",
        includeUnderlyingQuote=True,
        fromDate=target_date.strftime("%Y-%m-%d"),
        toDate=target_date.strftime("%Y-%m-%d")
    )
    response.raise_for_status()
    return response.json()


def find_atm_option(chain_data: Dict) -> tuple[Dict, float]:
    """
    Find ATM option from chain data.

    Args:
        chain_data: Option chain data from Schwab

    Returns:
        Tuple of (ATM option contract data, underlying price)
    """
    # Get current SPX price
    underlying_price = chain_data.get("underlyingPrice", 0)
    print(f"SPX underlying price: ${underlying_price:.2f}")

    # Find calls near ATM
    call_exp_map = chain_data.get("callExpDateMap", {})
    if not call_exp_map:
        raise ValueError("No call options found in chain")

    # Get first expiration date
    first_exp = list(call_exp_map.keys())[0]
    strikes = call_exp_map[first_exp]

    # Find closest strike to ATM
    closest_strike = None
    min_diff = float('inf')

    for strike_key in strikes.keys():
        strike = float(strike_key)
        diff = abs(strike - underlying_price)
        if diff < min_diff:
            min_diff = diff
            closest_strike = strike

    if closest_strike is None:
        raise ValueError("Could not find ATM strike")

    # Get the ATM option
    atm_option = strikes[str(closest_strike)][0]  # First contract at this strike

    print(f"Found ATM option: Strike ${closest_strike}, Current bid/ask: ${atm_option.get('bid', 0):.2f}/${atm_option.get('ask', 0):.2f}")

    return atm_option, underlying_price


def create_test_position(option_data: Dict, underlying_price: float) -> OptionsPosition:
    """
    Create a test position from option data.

    Args:
        option_data: Option contract data

    Returns:
        OptionsPosition object
    """
    # Parse expiration date
    exp_date_str = option_data['expirationDate']  # Format: "2025-01-17T21:00:00.000+00:00"

    # Handle both date-only and ISO datetime formats
    if 'T' in exp_date_str:
        # ISO format with timestamp - parse and convert
        exp_date = datetime.fromisoformat(exp_date_str.replace('+00:00', '+0000'))
        # Extract just the date part (options expire on a specific date)
        exp_date = exp_date.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        # Date-only format
        exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d")

    exp_date = ensure_utc_aware(exp_date)

    # Create a single leg position
    leg = OptionLeg(
        contract_symbol=option_data['symbol'],
        option_type=OptionType.CALL,
        strike_price=option_data['strikePrice'],
        expiration_date=exp_date,
        quantity=1,  # Buy 1 contract
        entry_price=0.01  # We'll buy for $0.01 (never fills)
    )

    position = OptionsPosition(
        position_id=f"TEST_{now_utc().strftime('%Y%m%d_%H%M%S')}",
        spread_type=SpreadType.SINGLE,  # Single leg position
        legs=[leg],
        entry_time=now_utc(),
        entry_cost=1.0,  # $0.01 per share * 100 shares = $1.00
        underlying_price_at_entry=underlying_price,
        profit_target_pct=0.50  # 50% profit target
    )

    return position


def main():
    """Main test function."""
    print("\n" + "="*70)
    print("SCHWAB LIVE ORDER SUBMISSION TEST")
    print("Testing order placement with never-fillable price ($0.01)")
    print("="*70 + "\n")

    # Initialize Schwab client
    print("1. Initializing Schwab client...")
    try:
        schwab_client = SchwabDevClient()
        print("   ✓ Schwab client initialized\n")
    except Exception as e:
        print(f"   ✗ Failed to initialize Schwab client: {e}")
        return

    # Initialize OrderManager in LIVE mode
    print("2. Initializing OrderManager (LIVE MODE)...")
    order_manager = OrderManager(
        paper_trading=False,  # LIVE MODE
        schwab_client=schwab_client,
        state_store=None  # No persistence for test
    )
    print("   ✓ OrderManager initialized in LIVE mode\n")

    # Find next week's Friday expiration
    print("3. Finding next week's SPXW expiration...")
    today = now_utc()
    days_until_friday = (4 - today.weekday()) % 7  # 4 = Friday
    if days_until_friday < 7:
        days_until_friday += 7  # Next Friday, not this Friday
    target_date = today + timedelta(days=days_until_friday)
    print(f"   Target expiration: {target_date.date()}\n")

    # Get option chain
    print("4. Fetching SPX option chain...")
    try:
        chain_data = get_spxw_chain_data(schwab_client, target_date)
        print("   ✓ Option chain fetched\n")
    except Exception as e:
        print(f"   ✗ Failed to fetch option chain: {e}")
        return

    # Find ATM option
    print("5. Finding ATM option...")
    try:
        atm_option, underlying_price = find_atm_option(chain_data)
        print(f"   ✓ ATM option found: {atm_option['symbol']}\n")
    except Exception as e:
        print(f"   ✗ Failed to find ATM option: {e}")
        return

    # Create test position
    print("6. Creating test position...")
    position = create_test_position(atm_option, underlying_price)
    print(f"   Position ID: {position.position_id}")
    print(f"   Contract: {position.legs[0].contract_symbol}")
    print(f"   Strike: ${position.legs[0].strike_price}")
    print(f"   Entry Price: ${position.legs[0].entry_price:.2f} (NEVER FILLS)")
    print()

    # Create mock options data for order submission
    # IMPORTANT: Override with $0.01 to ensure order never fills
    options_data = {
        position.legs[0].contract_symbol: {
            'symbol': atm_option['symbol'],
            'bid': 0.01,  # Override with $0.01
            'ask': 0.01,  # Override with $0.01
            'last': 0.01
        }
    }

    print(f"   Overriding market price (ask=${atm_option.get('ask', 0):.2f}) with $0.01")
    print()

    # Submit order
    print("7. Submitting order to Schwab...")
    print("   ⚠️  This will submit a REAL order to Schwab!")
    print("   Price is $0.01 so it will NEVER fill")
    print()

    confirm = input("   Continue? (yes/no): ").strip().lower()
    if confirm != 'yes':
        print("\n   Test cancelled by user")
        return

    try:
        success, message, order = order_manager.submit_position_entry(
            position=position,
            options_data=options_data,
            strategy_name="test_live_submission"
        )

        if success:
            print(f"\n   ✓ Order submitted successfully!")
            print(f"   Order ID: {order.order_id}")
            print(f"   Broker Order ID: {order.broker_order_id}")
            print(f"   Status: {order.status.value}")
            print()

            # Ask to cancel
            print("8. Cancel order?")
            cancel = input("   Cancel the order? (yes/no): ").strip().lower()

            if cancel == 'yes':
                print("\n   Cancelling order...")
                success, cancel_msg = order_manager.cancel_order(order.order_id)

                if success:
                    print(f"   ✓ Order cancelled: {cancel_msg}")
                else:
                    print(f"   ✗ Failed to cancel: {cancel_msg}")
                    print("   ⚠️  IMPORTANT: Manually cancel order in Schwab account!")
            else:
                print("\n   ⚠️  Order NOT cancelled - you MUST cancel manually in Schwab!")
                print(f"   Broker Order ID: {order.broker_order_id}")
        else:
            print(f"\n   ✗ Order submission failed: {message}")

    except Exception as e:
        print(f"\n   ✗ Error during order submission: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "="*70)
    print("Test complete!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
