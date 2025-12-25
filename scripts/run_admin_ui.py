#!/usr/bin/env python3
"""
Run the Admin UI service.

Usage:
    python scripts/run_admin_ui.py [--host HOST] [--port PORT] [--reload]

Examples:
    # Run on default host:port (0.0.0.0:8000)
    python scripts/run_admin_ui.py

    # Run on specific port
    python scripts/run_admin_ui.py --port 8080

    # Run with auto-reload for development
    python scripts/run_admin_ui.py --reload
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import uvicorn


def main():
    """Main entry point for Admin UI service."""
    parser = argparse.ArgumentParser(description="Run Quant-Vibe Admin UI service")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to bind to (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Log level (default: info)",
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Quant-Vibe Admin UI")
    print("=" * 80)
    print(f"Host: {args.host}")
    print(f"Port: {args.port}")
    print(f"Reload: {args.reload}")
    print(f"Log Level: {args.log_level}")
    print("=" * 80)
    print()
    print("API Documentation: http://localhost:8000/docs")
    print("API Base: http://localhost:8000/api")
    print("WebSocket: ws://localhost:8000/ws/events")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 80)
    print()

    uvicorn.run(
        "admin_ui.backend.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
