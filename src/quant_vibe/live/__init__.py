"""Live trading engine for options strategies.

This package provides real-time trading capabilities for executing
options strategies with streaming market data.

Components:
- engine: Main LiveTradingEngine orchestrator
- data_feed: Real-time data consumer from schwabdev stream
- strategy_executor: Strategy execution loop
- order_manager: Order submission and tracking
- position_manager: Position tracking and valuation
- risk_manager: Risk checks and limits
- state_store: State persistence and recovery
- monitor: Monitoring and alerts
"""

from .engine import LiveTradingEngine
from .data_feed import RealtimeDataFeed
from .state_store import StateStore
from .order_manager import OrderManager, Order, OrderStatus, OrderSide, OCOStatus
from .position_manager import PositionManager

__all__ = [
    'LiveTradingEngine',
    'RealtimeDataFeed',
    'StateStore',
    'OrderManager',
    'Order',
    'OrderStatus',
    'OrderSide',
    'OCOStatus',
    'PositionManager',
]
