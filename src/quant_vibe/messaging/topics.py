"""Topic definitions for message broker.

Topics are used to organize messages by type and destination.
"""

from enum import Enum


class Topic(str, Enum):
    """Message topics for pub/sub communication.

    Topics follow the pattern: {service}.{data_type}
    """

    # Options market data (streaming_service -> live_trading)
    OPTIONS_QUOTES = "streaming.options_quotes"
    OPTIONS_BARS = "streaming.options_bars"

    # Underlying asset data (streaming_service -> live_trading)
    UNDERLYING_QUOTES = "streaming.underlying_quotes"
    UNDERLYING_BARS = "streaming.underlying_bars"

    # Replay market data (replay_service -> live_trading for testing)
    REPLAY_OPTIONS_BARS = "replay.options_bars"
    REPLAY_UNDERLYING_BARS = "replay.underlying_bars"

    # System status and health
    SYSTEM_HEARTBEAT = "system.heartbeat"
    SYSTEM_ERROR = "system.error"

    # Trading signals (live_trading -> monitoring)
    TRADING_SIGNAL = "trading.signal"
    TRADING_ORDER = "trading.order"
    TRADING_FILL = "trading.fill"

    # Account activity (streaming_service -> live_trading)
    ACCOUNT_ACTIVITY = "streaming.account_activity"

    # Control messages (admin_ui -> live_trading)
    CONTROL_LIVE_TRADING = "control.live_trading"

    def __str__(self) -> str:
        """Return topic value as string."""
        return self.value
