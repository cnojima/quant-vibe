#!/usr/bin/env python3
"""Run the Token Management Service.

This script starts the centralized token management service that provides
OAuth tokens to all other services (streaming, live_trading, admin_ui).

Usage:
    python scripts/run_token_service.py
"""

import sys

# Add src to path for Docker container
sys.path.insert(0, "/app/src")

from token_service.service import main

if __name__ == "__main__":
    main()
