"""SPXW Options Streaming Service.

A production-ready service for streaming SPXW options data from Schwab API
and storing aggregated bars in TimescaleDB.

Main components:
- StreamingService: Main orchestrator
- TokenManager: OAuth token refresh management
- BarAggregator: Quote aggregation into OHLCV bars
- StreamingConfig: Configuration dataclass
"""

from .service import StreamingService
from .config import StreamingConfig
from .token_manager import TokenManager
from .aggregator import BarAggregator

__all__ = [
    "StreamingService",
    "StreamingConfig",
    "TokenManager",
    "BarAggregator",
]
