#!/usr/bin/env python3
"""
Scheduler service for running periodic tasks at specific times.

This service runs the nightly backfill job at 3pm PST daily.
"""

import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytz
import schedule

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Define timezone
PST = pytz.timezone("America/Los_Angeles")


def run_backfill_job():
    """Execute the nightly backfill job."""
    logger.info("Starting nightly backfill job")

    try:
        # Get the project root directory
        project_root = Path(__file__).parent.parent

        # Run mark-expired job first
        logger.info("Running mark-expired backfill...")
        result1 = subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts" / "backfill" / "backfill_stream_greeks.py"),
                "--mark-expired",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(project_root / "src")},
        )

        if result1.returncode != 0:
            logger.error(f"Mark-expired backfill failed with exit code {result1.returncode}")
            logger.error(f"stdout: {result1.stdout}")
            logger.error(f"stderr: {result1.stderr}")
            return

        logger.info("Mark-expired backfill completed successfully")
        if result1.stdout:
            logger.info(f"Output: {result1.stdout}")

        # Run active-only backfill with batch-size 500
        logger.info("Running active-only backfill with batch-size 500...")
        result2 = subprocess.run(
            [
                sys.executable,
                str(project_root / "scripts" / "backfill" / "backfill_stream_greeks.py"),
                "--active-only",
                "--batch-size",
                "500",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(project_root / "src")},
        )

        if result2.returncode != 0:
            logger.error(f"Active-only backfill failed with exit code {result2.returncode}")
            logger.error(f"stdout: {result2.stdout}")
            logger.error(f"stderr: {result2.stderr}")
            return

        logger.info("Active-only backfill completed successfully")
        if result2.stdout:
            logger.info(f"Output: {result2.stdout}")

        logger.info("Nightly backfill job completed successfully")

    except Exception as e:
        logger.error(f"Error running backfill job: {e}", exc_info=True)


def log_next_run():
    """Log the next scheduled run time."""
    next_run = schedule.next_run()
    if next_run:
        logger.info(f"Next scheduled run: {next_run} (UTC)")
        pst_time = next_run.replace(tzinfo=pytz.UTC).astimezone(PST)
        logger.info(f"Next scheduled run (PST): {pst_time}")


def main():
    """Main scheduler loop."""
    logger.info("Starting scheduler service")
    logger.info(f"Current time (UTC): {datetime.utcnow()}")
    logger.info(f"Current time (PST): {datetime.now(PST)}")

    # Schedule the job to run at 3pm PST daily
    # Convert PST time to UTC for scheduling (PST is UTC-8, PDT is UTC-7)
    # Using "15:00" in PST timezone
    schedule.every().day.at("15:00").do(run_backfill_job).tag("backfill")

    # Note: schedule library doesn't natively support timezones
    # We need to calculate UTC time for 3pm PST
    # PST = UTC-8, so 3pm PST = 11pm UTC (23:00)
    # PDT = UTC-7, so 3pm PDT = 10pm UTC (22:00)
    # To handle DST properly, we'll use a different approach

    # Clear the simple schedule and use a timezone-aware approach
    schedule.clear("backfill")

    # Create a function that checks if it's 3pm PST
    def run_at_3pm_pst():
        now = datetime.now(PST)
        if now.hour == 15 and now.minute == 0:
            run_backfill_job()

    # Check every minute if it's 3pm PST
    schedule.every(1).minutes.do(run_at_3pm_pst)

    logger.info("Scheduled nightly backfill job at 3:00 PM PST")
    log_next_run()

    # Run the scheduler loop
    while True:
        try:
            schedule.run_pending()
            # Sleep for a short time to prevent busy-waiting
            import time

            time.sleep(30)  # Check every 30 seconds
        except KeyboardInterrupt:
            logger.info("Scheduler stopped by user")
            break
        except Exception as e:
            logger.error(f"Error in scheduler loop: {e}", exc_info=True)
            # Continue running even if there's an error


if __name__ == "__main__":
    main()
