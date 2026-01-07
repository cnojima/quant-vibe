#!/usr/bin/env python3
"""
DynDNS Update Service

Periodically updates Sonic.net DynDNS records to maintain remote access.
Runs as a daemon and updates DNS when public IP changes.
"""

import os
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from quant_vibe.logging import setup_normalized_logging
from quant_vibe.services.dyndns_client import SonicDynDNSClient


# Load environment variables
load_dotenv()


def main():
    """Run DynDNS update service."""
    # Configuration from environment
    sonic_userid = os.getenv("SONIC_DYNDNS_USERID")
    sonic_apikey = os.getenv("SONIC_DYNDNS_APIKEY")
    sonic_hostname = os.getenv("SONIC_DYNDNS_HOSTNAME")
    record_type = os.getenv("SONIC_DYNDNS_RECORD_TYPE", "A")
    ttl = int(os.getenv("SONIC_DYNDNS_TTL", "300"))
    update_interval = int(os.getenv("SONIC_DYNDNS_UPDATE_INTERVAL", "300"))  # 5 min
    force_update_on_start = os.getenv("SONIC_DYNDNS_FORCE_UPDATE", "true").lower() == "true"

    # Validate configuration
    if not all([sonic_userid, sonic_apikey, sonic_hostname]):
        print("ERROR: Missing required DynDNS configuration")
        print("Required environment variables:")
        print("  - SONIC_DYNDNS_USERID")
        print("  - SONIC_DYNDNS_APIKEY")
        print("  - SONIC_DYNDNS_HOSTNAME")
        sys.exit(1)

    # Setup logging
    logger = setup_normalized_logging(
        app_name="dyndns",
        log_dir="logs/dyndns",
    )

    logger.info("=" * 80)
    logger.info("DynDNS Update Service Starting")
    logger.info("=" * 80)
    logger.info(f"Hostname: {sonic_hostname}")
    logger.info(f"Record Type: {record_type}")
    logger.info(f"TTL: {ttl} seconds")
    logger.info(f"Update Interval: {update_interval} seconds")
    logger.info(f"Force Update on Start: {force_update_on_start}")

    # Initialize DynDNS client
    with SonicDynDNSClient(
        userid=sonic_userid,
        apikey=sonic_apikey,
        hostname=sonic_hostname,
    ) as client:
        # Test API connectivity
        logger.info("Testing API connectivity...")
        if not client.ping():
            logger.error("Failed to connect to Sonic.net DynDNS API")
            sys.exit(1)
        logger.info("API connection successful")

        # Force initial update if configured
        if force_update_on_start:
            logger.info("Performing initial DNS update...")
            if client.force_update(record_type=record_type, ttl=ttl):
                logger.info("Initial update successful")
            else:
                logger.error("Initial update failed")
        else:
            # Just get current IP to establish baseline
            current_ip = client.get_current_ip()
            if current_ip:
                logger.info(f"Current public IP: {current_ip}")
                client.last_ip = current_ip
            else:
                logger.warning("Failed to get initial IP address")

        logger.info("Entering update loop...")
        logger.info(f"Checking for IP changes every {update_interval} seconds")

        # Main update loop
        update_count = 0
        error_count = 0

        try:
            while True:
                try:
                    # Check if update needed and perform if necessary
                    success = client.update_if_changed(
                        record_type=record_type,
                        ttl=ttl,
                    )

                    if success:
                        update_count += 1
                        error_count = 0  # Reset error count on success
                    else:
                        error_count += 1
                        logger.warning(
                            f"Update check failed (consecutive errors: {error_count})"
                        )

                        # Exit if too many consecutive errors
                        if error_count >= 10:
                            logger.error(
                                "Too many consecutive errors, exiting"
                            )
                            sys.exit(1)

                    # Log stats periodically
                    if update_count % 12 == 0:  # Every hour at 5-min intervals
                        logger.info(
                            f"Stats: {update_count} successful checks, "
                            f"current IP: {client.last_ip or 'unknown'}"
                        )

                except Exception as e:
                    error_count += 1
                    logger.error(f"Error in update loop: {e}", exc_info=True)

                    if error_count >= 10:
                        logger.error("Too many errors, exiting")
                        sys.exit(1)

                # Sleep until next update
                time.sleep(update_interval)

        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)

    logger.info("DynDNS service stopped")


if __name__ == "__main__":
    main()
