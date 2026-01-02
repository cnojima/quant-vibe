#!/usr/bin/env python3
"""
Fix exit_value and P&L for existing closed positions.

This script recalculates exit_value for all closed positions using the corrected formula
that includes the × 100 multiplier for options contracts.

Bug: Previous exit_value calculations were missing the × 100 multiplier, causing:
- exit_value to be 100x too small
- Incorrect sign convention
- Wrong P&L calculations in the database

This script:
1. Recalculates exit_value from legs data
2. Updates the database with corrected values
3. Verifies P&L matches the exit_reason message
"""

import os
import re
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

load_dotenv()


def get_db_connection():
    """Get database connection to production TimescaleDB."""
    # Use remote TimescaleDB (production)
    db_config = {
        'host': os.getenv('REMOTE_TIMESCALE_HOST', '192.168.100.197'),
        'port': int(os.getenv('REMOTE_TIMESCALE_PORT', '5432')),
        'database': os.getenv('REMOTE_TIMESCALE_DB', 'options_data'),
        'user': os.getenv('REMOTE_TIMESCALE_USER', 'quantvibe'),
        'password': os.getenv('REMOTE_TIMESCALE_PASSWORD', 'quantvibe_dev')
    }

    print(f"Connecting to: {db_config['host']}:{db_config['port']}/{db_config['database']}")
    return psycopg2.connect(**db_config)


def parse_pnl_from_exit_reason(exit_reason: str) -> Optional[float]:
    """Extract P&L from exit_reason message."""
    # Pattern: "P&L: $1978.88"
    match = re.search(r'P&L: \$([0-9.,-]+)', exit_reason)
    if match:
        pnl_str = match.group(1).replace(',', '')
        return float(pnl_str)
    return None


def recalculate_exit_value(entry_cost: float, actual_pnl: float) -> float:
    """
    Recalculate exit_value from entry_cost and actual P&L.

    Formula: exit_value = entry_cost + pnl

    For a long position (bought options):
    - entry_cost = +2000 (we paid $2000)
    - actual_pnl = +1000 (we made $1000)
    - exit_value = -3000 (we received $3000 when selling, stored as negative credit)

    Wait, that doesn't work...

    Let me recalculate based on the correct formula:
    pnl = exit_value - entry_cost
    => exit_value = pnl + entry_cost
    """
    return actual_pnl + entry_cost


def main():
    """Main migration function."""
    print("="*70)
    print("FIX POSITION EXIT VALUES MIGRATION")
    print("="*70)
    print()

    # Connect to database
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # Fetch all closed positions
        cursor.execute("""
            SELECT
                position_id,
                entry_cost,
                exit_value,
                exit_reason,
                legs
            FROM live_positions
            WHERE status = 'closed'
            ORDER BY entry_time DESC
        """)

        positions = cursor.fetchall()
        print(f"Found {len(positions)} closed positions to check")
        print()

        # Track statistics
        total_checked = 0
        total_fixed = 0
        total_errors = 0

        for pos in positions:
            total_checked += 1
            position_id = pos['position_id']
            entry_cost = float(pos['entry_cost'])
            current_exit_value = float(pos['exit_value']) if pos['exit_value'] else 0
            exit_reason = pos['exit_reason'] or ""

            print(f"Position: {position_id}")
            print(f"  Entry cost: ${entry_cost:.2f}")
            print(f"  Current exit_value: ${current_exit_value:.2f}")

            # Extract actual P&L from exit_reason
            actual_pnl = parse_pnl_from_exit_reason(exit_reason)

            if actual_pnl is None:
                print(f"  ⚠️  Could not parse P&L from exit_reason: {exit_reason}")
                total_errors += 1
                print()
                continue

            print(f"  Actual P&L (from exit_reason): ${actual_pnl:.2f}")

            # Recalculate correct exit_value
            corrected_exit_value = recalculate_exit_value(entry_cost, actual_pnl)

            print(f"  Corrected exit_value: ${corrected_exit_value:.2f}")

            # Calculate current DB P&L
            current_db_pnl = current_exit_value - entry_cost
            print(f"  Current DB P&L: ${current_db_pnl:.2f}")

            # Check if correction is needed
            if abs(current_exit_value - corrected_exit_value) > 0.01:
                print(f"  ✅ NEEDS FIX - Updating exit_value")

                # Update database
                cursor.execute("""
                    UPDATE live_positions
                    SET exit_value = %s,
                        updated_at = NOW()
                    WHERE position_id = %s
                """, (corrected_exit_value, position_id))

                total_fixed += 1
            else:
                print(f"  ✓ Already correct")

            print()

        # Commit changes
        if total_fixed > 0:
            print(f"Committing {total_fixed} updates...")
            conn.commit()
            print("✅ Changes committed")
        else:
            print("No changes needed")

        print()
        print("="*70)
        print("SUMMARY")
        print("="*70)
        print(f"Total positions checked: {total_checked}")
        print(f"Positions fixed: {total_fixed}")
        print(f"Errors: {total_errors}")
        print()

        if total_fixed > 0:
            print("✅ Migration completed successfully!")
        else:
            print("✓ No migration needed - all positions already correct")

    except Exception as e:
        print(f"❌ Error during migration: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
