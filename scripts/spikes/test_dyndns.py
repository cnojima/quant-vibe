#!/usr/bin/env python3
"""
Test script for Sonic.net DynDNS client.

Tests the DynDNS client functionality without requiring actual credentials.
Use environment variables to test with real credentials.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from quant_vibe.services.dyndns_client import SonicDynDNSClient


# Load environment variables
load_dotenv()


def test_api_ping():
    """Test API connectivity (no auth required)."""
    print("=" * 80)
    print("Test 1: API Ping (No Authentication)")
    print("=" * 80)

    # Create minimal client just for ping test
    client = SonicDynDNSClient(
        userid="test",
        apikey="test",
        hostname="test.sonic.net",
    )

    print("Testing API connectivity...")
    success = client.ping()

    if success:
        print("✅ API ping successful - Sonic.net API is reachable")
    else:
        print("❌ API ping failed - Check network connection")

    print()
    return success


def test_get_ip():
    """Test getting current public IP (no auth required)."""
    print("=" * 80)
    print("Test 2: Get Current Public IP (No Authentication)")
    print("=" * 80)

    # Create minimal client
    client = SonicDynDNSClient(
        userid="test",
        apikey="test",
        hostname="test.sonic.net",
    )

    print("Requesting current public IP...")
    ip = client.get_current_ip()

    if ip:
        print(f"✅ Current public IP: {ip}")
    else:
        print("❌ Failed to get public IP")

    print()
    return ip is not None


def test_authenticated_operations():
    """Test authenticated operations (requires credentials)."""
    print("=" * 80)
    print("Test 3: Authenticated Operations (Requires Credentials)")
    print("=" * 80)

    # Get credentials from environment
    userid = os.getenv("SONIC_DYNDNS_USERID")
    apikey = os.getenv("SONIC_DYNDNS_APIKEY")
    hostname = os.getenv("SONIC_DYNDNS_HOSTNAME")

    if not all([userid, apikey, hostname]):
        print("⚠️  Skipping authenticated tests - credentials not configured")
        print()
        print("To test authenticated operations, set these in .env:")
        print("  - SONIC_DYNDNS_USERID")
        print("  - SONIC_DYNDNS_APIKEY")
        print("  - SONIC_DYNDNS_HOSTNAME")
        print()
        return None

    print(f"Using credentials for: {hostname}")
    print()

    with SonicDynDNSClient(
        userid=userid,
        apikey=apikey,
        hostname=hostname,
    ) as client:
        # Test 3a: Check if update needed
        print("3a. Checking if DNS update is needed...")
        needs_update, current_ip = client.needs_update()
        print(f"   Current IP: {current_ip}")
        print(f"   Last known IP: {client.last_ip or 'unknown'}")
        print(f"   Update needed: {needs_update}")
        print()

        # Test 3b: Force update (dry run - asks user first)
        print("3b. Force DNS update (requires confirmation)")
        response = input("   Do you want to force a DNS update? (yes/no): ").strip().lower()

        if response == "yes":
            print("   Forcing DNS update...")
            success = client.force_update()
            if success:
                print(f"   ✅ DNS update successful: {hostname} -> {client.last_ip}")
            else:
                print("   ❌ DNS update failed - check credentials")
        else:
            print("   Skipped force update")

    print()
    return True


def test_update_if_changed():
    """Test conditional update (only if IP changed)."""
    print("=" * 80)
    print("Test 4: Conditional Update (Only if IP Changed)")
    print("=" * 80)

    # Get credentials from environment
    userid = os.getenv("SONIC_DYNDNS_USERID")
    apikey = os.getenv("SONIC_DYNDNS_APIKEY")
    hostname = os.getenv("SONIC_DYNDNS_HOSTNAME")

    if not all([userid, apikey, hostname]):
        print("⚠️  Skipping - credentials not configured")
        print()
        return None

    print(f"Checking DNS for: {hostname}")
    print()

    with SonicDynDNSClient(
        userid=userid,
        apikey=apikey,
        hostname=hostname,
    ) as client:
        # Get current state
        current_ip = client.get_current_ip()
        print(f"Current public IP: {current_ip}")

        # Simulate last known IP (for testing)
        # In production, this would be loaded from state file
        client.last_ip = current_ip  # Set to same to test "no update needed"

        print(f"Last known IP: {client.last_ip}")
        print()

        # Test update_if_changed
        print("Testing update_if_changed()...")
        success = client.update_if_changed()

        if success:
            print("✅ Check successful (no update was needed)")
        else:
            print("❌ Check failed")

    print()
    return success


def main():
    """Run all tests."""
    print()
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "Sonic.net DynDNS Client Test Suite" + " " * 24 + "║")
    print("╚" + "=" * 78 + "╝")
    print()

    results = []

    # Test 1: API ping (no auth)
    results.append(("API Ping", test_api_ping()))

    # Test 2: Get IP (no auth)
    results.append(("Get Public IP", test_get_ip()))

    # Test 3: Authenticated operations (requires credentials)
    auth_result = test_authenticated_operations()
    if auth_result is not None:
        results.append(("Authenticated Operations", auth_result))

    # Test 4: Conditional update (requires credentials)
    conditional_result = test_update_if_changed()
    if conditional_result is not None:
        results.append(("Conditional Update", conditional_result))

    # Summary
    print("=" * 80)
    print("Test Summary")
    print("=" * 80)
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status:8} - {test_name}")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    print()
    print(f"Results: {passed}/{total} tests passed")
    print("=" * 80)
    print()

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("⚠️  Some tests failed - check output above")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        print("Tests cancelled by user")
        sys.exit(1)
