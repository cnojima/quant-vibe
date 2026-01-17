#!/usr/bin/env python3
"""
Test script for Schwab transactions API - exploring various parameter combinations.

This script tests different variations of the client.transactions() call to understand:
1. What transaction types are valid
2. What date ranges work
3. What data is returned
"""

import json
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any

from quant_vibe.data.schwab_dev_client import SchwabDevClient
from quant_vibe.logging import setup_normalized_logging, get_logger


def test_transactions(
    client,
    account_hash: str,
    start_date: datetime,
    end_date: datetime,
    transaction_type: str,
    test_name: str
) -> Dict[str, Any]:
    """Test a specific transaction query configuration."""
    print(f"\n{'='*60}")
    print(f"Test: {test_name}")
    print(f"Account: ...{account_hash[-8:]}")
    print(f"Date Range: {start_date.date()} to {end_date.date()} ({(end_date - start_date).days} days)")
    print(f"Type: '{transaction_type}'")
    print(f"{'-'*60}")

    result = {
        'test_name': test_name,
        'account_hash': account_hash,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'transaction_type': transaction_type,
        'success': False,
        'count': 0,
        'error': None,
        'sample': None
    }

    try:
        response = client.transactions(
            accountHash=account_hash,
            startDate=start_date,
            endDate=end_date,
            types=transaction_type
        )

        print(f"Response Status: {response.status_code}")

        if response.status_code == 200:
            transactions = response.json()
            result['success'] = True
            result['count'] = len(transactions)

            print(f"✅ Found {len(transactions)} transactions")

            if transactions:
                # Analyze first transaction
                first_txn = transactions[0]
                result['sample'] = first_txn

                print("\nFirst Transaction Details:")
                print(f"  Activity ID: {first_txn.get('activityId')}")
                print(f"  Type: {first_txn.get('type')}")
                print(f"  Status: {first_txn.get('status')}")
                print(f"  Time: {first_txn.get('time')}")
                print(f"  Trade Date: {first_txn.get('tradeDate')}")
                print(f"  Sub Account: {first_txn.get('subAccount')}")
                print(f"  Net Amount: ${first_txn.get('netAmount', 0):.2f}")

                # Check transfer items
                transfer_items = first_txn.get('transferItems', [])
                if transfer_items:
                    print(f"\n  Transfer Items ({len(transfer_items)}):")
                    for i, item in enumerate(transfer_items[:3]):  # Show first 3
                        instrument = item.get('instrument', {})
                        print(f"    [{i+1}] {instrument.get('assetType')} - {instrument.get('symbol')}")
                        print(f"        Amount: {item.get('amount', 0)}")
                        print(f"        Cost: ${item.get('cost', 0):.2f}")
                        print(f"        Price: ${item.get('price', 0):.2f} " if item.get('price') else "")
                        print(f"        Position Effect: {item.get('positionEffect')}" if item.get('positionEffect') else "")
                        print(f"        Fee Type: {item.get('feeType')}" if item.get('feeType') else "")

                # Analyze all transactions
                print(f"\nTransaction Summary:")
                types_count = {}
                statuses_count = {}
                position_effects = {}

                for txn in transactions:
                    # Count types
                    tx_type = txn.get('type', 'UNKNOWN')
                    types_count[tx_type] = types_count.get(tx_type, 0) + 1

                    # Count statuses
                    status = txn.get('status', 'UNKNOWN')
                    statuses_count[status] = statuses_count.get(status, 0) + 1

                    # Count position effects from transfer items
                    for item in txn.get('transferItems', []):
                        effect = item.get('positionEffect')
                        if effect:
                            position_effects[effect] = position_effects.get(effect, 0) + 1

                print(f"  Types: {types_count}")
                print(f"  Statuses: {statuses_count}")
                if position_effects:
                    print(f"  Position Effects: {position_effects}")

        else:
            error_text = response.text[:200] if response.text else "No error message"
            result['error'] = f"HTTP {response.status_code}: {error_text}"
            print(f"❌ Error: {result['error']}")

    except Exception as e:
        result['error'] = str(e)
        print(f"❌ Exception: {e}")

    return result


def main():
    """Run comprehensive transaction API tests."""
    logger = get_logger(__name__)

    print("="*80)
    print("SCHWAB TRANSACTIONS API TEST SUITE")
    print("="*80)

    # Initialize client
    print("\nInitializing Schwab client...")
    try:
        schwab_dev = SchwabDevClient()
        client = schwab_dev.client
        print("✅ Client initialized successfully")
    except Exception as e:
        print(f"❌ Failed to initialize client: {e}")
        return 1

    # Get accounts
    print("\nFetching linked accounts...")
    accounts_resp = client.linked_accounts()
    accounts = accounts_resp.json()

    if not accounts:
        print("❌ No linked accounts found")
        return 1

    print(f"✅ Found {len(accounts)} account(s):")
    for acc in accounts:
        print(f"  - {acc.get('accountNumber')} (Hash: ...{acc['hashValue'][-8:]})")

    # Prepare test variations
    now = datetime.now()
    test_results = []

    # Test each account
    for account in accounts:
        account_hash = account['hashValue']
        account_num = account.get('accountNumber')

        print(f"\n{'='*80}")
        print(f"TESTING ACCOUNT {account_num}")
        print(f"{'='*80}")

        # Test 1: Standard TRADE type with various date ranges
        date_ranges = [
            (now - timedelta(days=7), now, "Last 7 days"),
            (now - timedelta(days=30), now, "Last 30 days"),
            (now - timedelta(days=90), now, "Last 90 days"),
            (now - timedelta(days=180), now, "Last 180 days"),
            (now - timedelta(days=365), now, "Last 365 days"),
        ]

        for start_date, end_date, range_name in date_ranges:
            result = test_transactions(
                client, account_hash, start_date, end_date,
                "TRADE", f"TRADE - {range_name}"
            )
            test_results.append(result)

            # If we found transactions, no need to test longer ranges
            if result['count'] > 0:
                print(f"  ✓ Found transactions in {range_name}, skipping longer ranges")
                break

        # Test 2: Try different transaction type values
        # Based on API documentation and common transaction types
        transaction_types_to_test = [
            "TRADE",
            "RECEIVE_AND_DELIVER",
            "DIVIDEND_OR_INTEREST",
            "ACH_RECEIPT",
            "ACH_DISBURSEMENT",
            "CASH_RECEIPT",
            "CASH_DISBURSEMENT",
            "ELECTRONIC_FUND",
            "WIRE_OUT",
            "WIRE_IN",
            "JOURNAL",
            "MEMORANDUM",
            "MARGIN_CALL",
            "MONEY_MARKET",
            "SMA_ADJUSTMENT"
        ]

        print(f"\n{'='*60}")
        print("Testing Various Transaction Types (Last 365 days)")
        print(f"{'='*60}")

        start_date = now - timedelta(days=365)

        for tx_type in transaction_types_to_test:
            # Quick test - just check if type is valid and returns data
            print(f"\nTrying type: '{tx_type}'...", end=" ")
            try:
                response = client.transactions(
                    accountHash=account_hash,
                    startDate=start_date,
                    endDate=now,
                    types=tx_type
                )

                if response.status_code == 200:
                    txns = response.json()
                    if txns:
                        print(f"✅ Found {len(txns)} transactions")
                        # Do a detailed test for this type
                        result = test_transactions(
                            client, account_hash, start_date, now,
                            tx_type, f"Type: {tx_type}"
                        )
                        test_results.append(result)
                    else:
                        print(f"✓ Valid but no transactions")
                elif response.status_code == 400:
                    error_msg = response.json().get('message', '')
                    if 'not a valid value' in error_msg:
                        print(f"✗ Invalid type")
                    else:
                        print(f"✗ Bad request: {error_msg[:50]}")
                else:
                    print(f"✗ HTTP {response.status_code}")

            except Exception as e:
                print(f"✗ Exception: {str(e)[:50]}")

    # Summary Report
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")

    successful_tests = [r for r in test_results if r['success']]
    failed_tests = [r for r in test_results if not r['success']]
    tests_with_data = [r for r in test_results if r['count'] > 0]

    print(f"\nTotal Tests Run: {len(test_results)}")
    print(f"Successful: {len(successful_tests)}")
    print(f"Failed: {len(failed_tests)}")
    print(f"Tests with Data: {len(tests_with_data)}")

    if tests_with_data:
        print(f"\n✅ TESTS THAT FOUND TRANSACTIONS:")
        for test in tests_with_data:
            print(f"  - {test['test_name']}: {test['count']} transactions")
    else:
        print(f"\n⚠️  No tests found any transactions")

    # Save detailed results to file
    output_file = f"transaction_test_results_{now.strftime('%Y%m%d_%H%M%S')}.json"
    with open(output_file, 'w') as f:
        json.dump(test_results, f, indent=2, default=str)
    print(f"\nDetailed results saved to: {output_file}")

    return 0


if __name__ == "__main__":
    sys.exit(main())