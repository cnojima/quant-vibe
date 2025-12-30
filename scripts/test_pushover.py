#!/usr/bin/env python
"""Test Pushover notification system.

This script tests the Pushover notification integration.
Requires PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY in .env file.

Usage:
    python scripts/test_pushover.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.notifications import (
    PushoverNotifier,
    NotificationPriority,
    PushoverSound,
    TradingNotifier
)


def test_basic_notification():
    """Test basic notification sending."""
    print("="*70)
    print("Testing Basic Pushover Notification")
    print("="*70)

    notifier = PushoverNotifier()

    # Validate credentials
    print("\n1. Validating credentials...")
    if not notifier.validate():
        print("❌ Validation failed. Check your PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY")
        return False

    # Send test notification
    print("\n2. Sending test notification...")
    success = notifier.send(
        title="QuantVibe Test",
        message="This is a test notification from QuantVibe",
        priority=NotificationPriority.NORMAL
    )

    if success:
        print("✅ Test notification sent successfully!")
    else:
        print("❌ Failed to send notification")

    return success


def test_trading_notifications():
    """Test trading-specific notifications."""
    print("\n" + "="*70)
    print("Testing Trading Notifications")
    print("="*70)

    notifier = PushoverNotifier()

    tests = [
        ("Order Filled", lambda: notifier.send_order_filled(
            symbol="SPXW 251231P06200",
            quantity=1,
            price=2.50,
            order_type="Limit"
        )),
        ("Position Opened", lambda: notifier.send_position_opened(
            strategy="Bullish Put Spread",
            symbol="SPX 6200/6180",
            entry_price=250.00
        )),
        ("Position Closed (Profit)", lambda: notifier.send_position_closed(
            strategy="Bullish Put Spread",
            symbol="SPX 6200/6180",
            pnl=150.00,
            pnl_pct=60.0
        )),
        ("Position Closed (Loss)", lambda: notifier.send_position_closed(
            strategy="Bullish Put Spread",
            symbol="SPX 6200/6180",
            pnl=-100.00,
            pnl_pct=-40.0
        )),
        ("Warning Alert", lambda: notifier.send_warning(
            warning_type="Daily Loss Approaching",
            message="Current loss: $450 (Limit: $500)"
        )),
        ("Info Notification", lambda: notifier.send_info(
            title="Market Hours",
            message="Trading will end in 30 minutes"
        )),
    ]

    results = []
    for i, (name, test_func) in enumerate(tests, 1):
        print(f"\n{i}. Testing: {name}")
        try:
            success = test_func()
            if success:
                print(f"   ✅ {name} sent")
                results.append(True)
            else:
                print(f"   ❌ {name} failed")
                results.append(False)
        except Exception as e:
            print(f"   ❌ {name} error: {e}")
            results.append(False)

    print(f"\n" + "="*70)
    print(f"Results: {sum(results)}/{len(results)} notifications sent successfully")
    print("="*70)

    return all(results)


def test_trading_notifier():
    """Test TradingNotifier integration."""
    print("\n" + "="*70)
    print("Testing TradingNotifier")
    print("="*70)

    config = {
        "notify_on_start": True,
        "notify_on_position_open": True,
        "notify_on_position_close": True,
        "min_pnl_notify": 50.0,  # Only notify for P&L >= $50
    }

    notifier = TradingNotifier(config=config)

    # Test engine start
    print("\n1. Testing engine start notification...")
    notifier.on_engine_start(
        mode="paper",
        strategies=["Bullish Put Spread", "Iron Condor"]
    )

    # Test position opened
    print("2. Testing position opened...")
    notifier.on_position_opened(
        strategy="Bullish Put Spread",
        symbol="SPX 6200/6180",
        entry_price=250.00
    )

    # Test position closed (below threshold - should skip)
    print("3. Testing position closed (below P&L threshold)...")
    notifier.on_position_closed(
        strategy="Bullish Put Spread",
        symbol="SPX 6200/6180",
        pnl=25.00,  # Below $50 threshold
        pnl_pct=10.0
    )

    # Test position closed (above threshold - should send)
    print("4. Testing position closed (above P&L threshold)...")
    notifier.on_position_closed(
        strategy="Bullish Put Spread",
        symbol="SPX 6200/6180",
        pnl=75.00,  # Above $50 threshold
        pnl_pct=30.0
    )

    # Test risk alert
    print("5. Testing risk alert...")
    notifier.on_risk_alert(
        alert_type="Daily Loss Limit",
        message="Approaching daily loss limit: $480/$500",
        severity="warning"
    )

    print("\n✅ TradingNotifier tests completed")
    return True


def test_priority_levels():
    """Test different priority levels."""
    print("\n" + "="*70)
    print("Testing Priority Levels")
    print("="*70)
    print("\nNOTE: This test will send notifications with different priority levels.")
    print("Emergency priority requires acknowledgment on your device.")

    notifier = PushoverNotifier()

    priorities = [
        (NotificationPriority.LOWEST, "Lowest", None),
        (NotificationPriority.LOW, "Low", None),
        (NotificationPriority.NORMAL, "Normal", None),
        (NotificationPriority.HIGH, "High", PushoverSound.INCOMING),
    ]

    for priority, name, sound in priorities:
        print(f"\n  Testing: {name} priority")
        notifier.send(
            title=f"Priority Test: {name}",
            message=f"This is a {name} priority notification",
            priority=priority,
            sound=sound
        )

    print("\n⚠️  Skipping EMERGENCY priority test (requires acknowledgment)")
    print("    To test emergency priority, uncomment the code in this script")

    # Uncomment to test emergency priority (requires acknowledgment)
    # notifier.send(
    #     title="EMERGENCY Test",
    #     message="This requires acknowledgment",
    #     priority=NotificationPriority.EMERGENCY,
    #     sound=PushoverSound.SIREN,
    #     retry=30,
    #     expire=300
    # )

    print("\n✅ Priority tests completed")
    return True


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("PUSHOVER NOTIFICATION TEST SUITE")
    print("="*70)
    print("\nMake sure you have set up your .env file with:")
    print("  PUSHOVER_API_TOKEN=your_token_here")
    print("  PUSHOVER_USER_KEY=your_user_key_here")
    print("\nYou should receive notifications on your device(s).")
    input("\nPress Enter to continue...")

    tests = [
        ("Basic Notification", test_basic_notification),
        ("Trading Notifications", test_trading_notifications),
        ("Trading Notifier", test_trading_notifier),
        ("Priority Levels", test_priority_levels),
    ]

    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n❌ {name} failed with error: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")

    passed = sum(1 for _, r in results if r)
    total = len(results)
    print(f"\nTotal: {passed}/{total} test suites passed")
    print("="*70)


if __name__ == "__main__":
    main()
