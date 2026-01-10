#!/usr/bin/env python3
"""Test script to verify EST-based log rotation."""

import sys
from pathlib import Path
from datetime import datetime
import pytz

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.logging import setup_normalized_logging


def main():
    """Test log rotation with EST timezone."""

    # Setup logger with EST rotation
    logger = setup_normalized_logging(
        app_name="rotation_test",
        log_dir="logs/rotation_test",
    )

    # Get current time in EST
    eastern = pytz.timezone('America/New_York')
    utc = pytz.UTC
    est_now = datetime.now(tz=eastern)
    utc_now = datetime.now(tz=utc)

    print(f"\n{'='*60}")
    print(f"Log Rotation Test - EST Timezone")
    print(f"{'='*60}")
    print(f"Current EST time: {est_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"Current UTC time: {utc_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"{'='*60}\n")

    # Log some test messages
    logger.info("Testing log rotation based on EST calendar day")
    logger.info(f"Current EST time: {est_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    logger.debug("Debug message - detailed logging")
    logger.warning("Warning message - something to watch")

    # Test multi-line message
    logger.info("Multi-line message test:\nLine 2\nLine 3")

    # Test exception logging
    try:
        raise ValueError("Test exception for logging")
    except ValueError:
        logger.error("Caught test exception", exc_info=True)

    logger.info("Log rotation test complete")

    # Display log file information
    log_dir = Path("logs/rotation_test")
    if log_dir.exists():
        print(f"\nLog files in {log_dir}:")
        for log_file in sorted(log_dir.glob("*.log*")):
            size = log_file.stat().st_size
            print(f"  - {log_file.name} ({size} bytes)")

    print(f"\n{'='*60}")
    print("Log rotation configured to rotate at midnight EST")
    print("Rotated files will have suffix: YYYY-MM-DD_EST")
    print("Keeping last 30 days of logs")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
