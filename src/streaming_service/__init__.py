"""SPXW Options Streaming Service.

A production-ready service for streaming SPXW options data from Schwab API
and storing aggregated bars in TimescaleDB.

Main components:
- StreamingService: Main orchestrator
- TokenManager: OAuth token refresh management
- BarAggregator: Quote aggregation into OHLCV bars (options)
- UnderlyingBarAggregator: Quote aggregation for underlying assets (SPX)
- StreamingConfig: Configuration dataclass
"""

from .service import StreamingService
from .config import StreamingConfig
from .token_manager import TokenManager
from .aggregator import BarAggregator
from .underlying_aggregator import UnderlyingBarAggregator

__all__ = [
    "StreamingService",
    "StreamingConfig",
    "TokenManager",
    "BarAggregator",
    "UnderlyingBarAggregator",
]
