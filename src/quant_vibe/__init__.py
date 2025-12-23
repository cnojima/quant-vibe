"""
Quant-Vibe: A quantitative trading platform.

This package provides tools for backtesting trading strategies,
fetching live market data, and calculating technical indicators.
"""

__version__ = "0.1.0"

# import logging
# logger = logging.getLogger(__name__)
# logging.basicConfig(filename='logs/quant-vibe.log', level=logging.DEBUG)
# logger.info("Quant-Vibe package initialized.")

from .config import __all__ as config_all
__all__ = [
    *config_all,
]