#!/usr/bin/env python3
"""Run the watcher service for monitoring system health."""

import sys

# Add src to path for Docker container
sys.path.insert(0, "/app/src")

from watcher_service.watcher import WatcherService


def main():
    """Main entry point."""
    print("Starting Watcher Service...")
    print("Press Ctrl+C to stop")

    watcher = WatcherService()
    watcher.run()


if __name__ == "__main__":
    main()
