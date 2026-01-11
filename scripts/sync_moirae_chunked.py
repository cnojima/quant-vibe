#!/usr/bin/env python3
"""Wrapper script to sync long date ranges in 1-month chunks."""

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

def generate_monthly_chunks(start_date, end_date):
    """
    Generate 1-month chunks between start and end dates.

    Args:
        start_date: datetime object for start
        end_date: datetime object for end (inclusive)

    Returns:
        List of (start, end) tuples for each chunk
    """
    chunks = []
    current = start_date

    while current <= end_date:
        # Calculate next month boundary
        # Add 1 month by going to first day of next month
        if current.month == 12:
            next_month = datetime(current.year + 1, 1, 1)
        else:
            next_month = datetime(current.year, current.month + 1, 1)

        # Chunk end is either next month boundary or final end_date
        chunk_end = min(next_month, end_date + timedelta(days=1))  # +1 day because until is exclusive

        chunks.append((current, chunk_end))
        current = chunk_end

    return chunks


def run_sync_chunk(since, until, script_path):
    """
    Run sync_moirae.py for a single chunk.

    Args:
        since: Start date (datetime)
        until: End date (datetime, exclusive)
        script_path: Path to sync_moirae.py

    Returns:
        True if successful, False otherwise
    """
    since_str = since.strftime('%Y-%m-%d')
    until_str = until.strftime('%Y-%m-%d')

    print(f"\n{'='*80}")
    print(f"📦 CHUNK: {since_str} to {until_str}")
    print(f"{'='*80}\n")

    cmd = [
        sys.executable,
        str(script_path),
        '--since', since_str,
        '--until', until_str
    ]

    try:
        result = subprocess.run(cmd, check=True)
        print(f"\n✅ Successfully synced chunk: {since_str} to {until_str}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Failed to sync chunk: {since_str} to {until_str}")
        print(f"   Error: {e}")
        return False


def main():
    """Main sync orchestration."""
    # Date range
    START_DATE = datetime(2024, 1, 22)
    END_DATE = datetime(2025, 11, 30)

    # Path to sync script
    script_dir = Path(__file__).parent
    sync_script = script_dir / 'sync_moirae.py'

    if not sync_script.exists():
        print(f"❌ ERROR: sync_moirae.py not found at {sync_script}")
        sys.exit(1)

    print(f"\n{'='*80}")
    print(f"🚀 CHUNKED SYNC: {START_DATE.date()} to {END_DATE.date()}")
    print(f"{'='*80}")
    print(f"Strategy: 1-month chunks")
    print(f"Script: {sync_script}")
    print()

    # Generate chunks
    chunks = generate_monthly_chunks(START_DATE, END_DATE)
    total_chunks = len(chunks)

    print(f"📋 Generated {total_chunks} chunks:")
    for i, (start, end) in enumerate(chunks, 1):
        print(f"   {i:2d}. {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")

    # Confirm before starting
    response = input(f"\n❓ Proceed with syncing {total_chunks} chunks? [y/N]: ")
    if response.lower() not in ['y', 'yes']:
        print("Aborted.")
        sys.exit(0)

    # Run each chunk
    success_count = 0
    failed_chunks = []

    for i, (start, end) in enumerate(chunks, 1):
        print(f"\n{'='*80}")
        print(f"PROGRESS: Chunk {i}/{total_chunks}")
        print(f"{'='*80}")

        success = run_sync_chunk(start, end, sync_script)

        if success:
            success_count += 1
        else:
            failed_chunks.append((start, end))

    # Final summary
    print(f"\n{'='*80}")
    print(f"📊 SYNC SUMMARY")
    print(f"{'='*80}")
    print(f"Total chunks: {total_chunks}")
    print(f"✅ Successful: {success_count}")
    print(f"❌ Failed: {len(failed_chunks)}")

    if failed_chunks:
        print(f"\n⚠️  Failed chunks:")
        for start, end in failed_chunks:
            print(f"   - {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}")
        sys.exit(1)
    else:
        print(f"\n🎉 All chunks synced successfully!")
        sys.exit(0)


if __name__ == '__main__':
    main()
