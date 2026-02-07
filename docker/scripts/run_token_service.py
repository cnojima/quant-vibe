#!/usr/bin/env python3
"""Run the Token Management Service.

This script starts the centralized token management service that provides
OAuth tokens to all other services (streaming, live_trading, admin_ui).

Usage:
    python scripts/run_token_service.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from token_service.service import main

if __name__ == "__main__":
    main()
