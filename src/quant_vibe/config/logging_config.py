"""Logging configuration.

This module provides backward-compatible logging setup.
For new code, use unified_logging.py for normalized format.
"""

from .unified_logging import setup_logging, setup_normalized_logging, get_logger

__all__ = [
    'setup_logging',
    'setup_normalized_logging',
    'get_logger',
]
