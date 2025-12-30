"""Trading-specific notification handler.

Integrates Pushover notifications with live trading events.
Automatically sends notifications for key trading events based on configuration.
"""

import logging
from typing import Optional, Dict, Any, List
from datetime import datetime

from quant_vibe.notifications.pushover import (
    PushoverNotifier,
    NotificationPriority
)


class TradingNotifier:
    """Handle trading event notifications.

    Centralizes notification logic for trading events with configurable
    filtering and rate limiting.

    Example:
        >>> notifier = TradingNotifier()
        >>> notifier.on_position_opened("BPS", "6200/6180", 250.0)
        >>> notifier.on_order_filled("SPXW 251231P06200", 1, 2.50)
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize trading notifier.

        Args:
            config: Notification configuration dict
            logger: Logger instance
        """
        self.config = config or {}
        self.logger = logger or logging.getLogger(__name__)

        # Initialize Pushover
        pushover_config = self.config.get("pushover", {})
        self.pushover = PushoverNotifier(
            api_token=pushover_config.get("api_token"),
            user_key=pushover_config.get("user_key"),
            device=pushover_config.get("device"),
            enabled=pushover_config.get("enabled", True),
            logger=self.logger
        )

        # Notification filters
        self.notify_on_start = self.config.get("notify_on_start", True)
        self.notify_on_stop = self.config.get("notify_on_stop", True)
        self.notify_on_position_open = self.config.get("notify_on_position_open", True)
        self.notify_on_position_close = self.config.get("notify_on_position_close", True)
        self.notify_on_order_fill = self.config.get("notify_on_order_fill", True)
        self.notify_on_order_reject = self.config.get("notify_on_order_reject", True)
        self.notify_on_risk_alert = self.config.get("notify_on_risk_alert", True)
        self.notify_on_error = self.config.get("notify_on_error", True)
        self.notify_daily_summary = self.config.get("notify_daily_summary", False)

        # Minimum P&L thresholds for notifications (optional)
        self.min_pnl_notify = self.config.get("min_pnl_notify")  # e.g., 100.0

        self.logger.info("TradingNotifier initialized")

    def validate(self) -> bool:
        """Validate notification service credentials.

        Returns:
            True if configured correctly
        """
        return self.pushover.validate()

    def on_engine_start(
        self,
        mode: str,
        strategies: Optional[List[str]] = None
    ) -> bool:
        """Handle engine start event.

        Args:
            mode: Trading mode (live/paper)
            strategies: List of enabled strategies

        Returns:
            True if notification sent
        """
        if not self.notify_on_start:
            return False

        return self.pushover.send_engine_started(
            mode=mode,
            strategies=strategies
        )

    def on_engine_stop(
        self,
        reason: Optional[str] = None,
        stats: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle engine stop event.

        Args:
            reason: Reason for stopping
            stats: Session statistics

        Returns:
            True if notification sent
        """
        if not self.notify_on_stop:
            return False

        return self.pushover.send_engine_stopped(
            reason=reason,
            stats=stats
        )

    def on_position_opened(
        self,
        strategy: str,
        symbol: str,
        entry_price: float,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle position opened event.

        Args:
            strategy: Strategy name
            symbol: Position symbol/description
            entry_price: Entry price
            metadata: Additional position metadata

        Returns:
            True if notification sent
        """
        if not self.notify_on_position_open:
            return False

        return self.pushover.send_position_opened(
            strategy=strategy,
            symbol=symbol,
            entry_price=entry_price
        )

    def on_position_closed(
        self,
        strategy: str,
        symbol: str,
        pnl: float,
        pnl_pct: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle position closed event.

        Args:
            strategy: Strategy name
            symbol: Position symbol/description
            pnl: Profit/loss amount
            pnl_pct: Profit/loss percentage
            metadata: Additional position metadata

        Returns:
            True if notification sent
        """
        if not self.notify_on_position_close:
            return False

        # Check minimum P&L threshold
        if self.min_pnl_notify is not None:
            if abs(pnl) < self.min_pnl_notify:
                self.logger.debug(
                    f"Skipping notification: P&L ${pnl:.2f} below threshold "
                    f"${self.min_pnl_notify}"
                )
                return False

        return self.pushover.send_position_closed(
            strategy=strategy,
            symbol=symbol,
            pnl=pnl,
            pnl_pct=pnl_pct
        )

    def on_order_filled(
        self,
        symbol: str,
        quantity: int,
        price: float,
        order_type: str = "Market",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle order filled event.

        Args:
            symbol: Order symbol
            quantity: Quantity filled
            price: Fill price
            order_type: Order type
            metadata: Additional order metadata

        Returns:
            True if notification sent
        """
        if not self.notify_on_order_fill:
            return False

        return self.pushover.send_order_filled(
            symbol=symbol,
            quantity=quantity,
            price=price,
            order_type=order_type
        )

    def on_order_rejected(
        self,
        symbol: str,
        reason: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle order rejected event.

        Args:
            symbol: Order symbol
            reason: Rejection reason
            metadata: Additional order metadata

        Returns:
            True if notification sent
        """
        if not self.notify_on_order_reject:
            return False

        return self.pushover.send_critical_alert(
            alert_type="Order Rejected",
            message=f"{symbol}\nReason: {reason}"
        )

    def on_risk_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "warning",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle risk alert event.

        Args:
            alert_type: Type of risk alert
            message: Alert message
            severity: Alert severity (critical/warning/info)
            metadata: Additional metadata

        Returns:
            True if notification sent
        """
        if not self.notify_on_risk_alert:
            return False

        if severity == "critical":
            return self.pushover.send_critical_alert(
                alert_type=alert_type,
                message=message
            )
        elif severity == "warning":
            return self.pushover.send_warning(
                warning_type=alert_type,
                message=message
            )
        else:
            return self.pushover.send_info(
                title=alert_type,
                message=message
            )

    def on_error(
        self,
        error_type: str,
        message: str,
        critical: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Handle error event.

        Args:
            error_type: Type of error
            message: Error message
            critical: Whether error is critical
            metadata: Additional metadata

        Returns:
            True if notification sent
        """
        if not self.notify_on_error:
            return False

        if critical:
            return self.pushover.send_critical_alert(
                alert_type=error_type,
                message=message
            )
        else:
            return self.pushover.send_warning(
                warning_type=error_type,
                message=message
            )

    def send_daily_summary(
        self,
        date: datetime,
        trades: int,
        pnl: float,
        win_rate: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Send daily trading summary.

        Args:
            date: Trading date
            trades: Number of trades
            pnl: Total P&L
            win_rate: Win rate percentage
            metadata: Additional statistics

        Returns:
            True if notification sent
        """
        if not self.notify_daily_summary:
            return False

        return self.pushover.send_daily_summary(
            date=date,
            trades=trades,
            pnl=pnl,
            win_rate=win_rate
        )

    def send_custom(
        self,
        message: str,
        title: Optional[str] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        **kwargs
    ) -> bool:
        """Send custom notification.

        Args:
            message: Notification message
            title: Notification title
            priority: Priority level
            **kwargs: Additional Pushover parameters

        Returns:
            True if notification sent
        """
        return self.pushover.send(
            message=message,
            title=title,
            priority=priority,
            **kwargs
        )
