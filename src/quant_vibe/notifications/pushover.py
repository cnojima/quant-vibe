"""Pushover notification service for real-time alerts.

Provides push notifications to mobile devices and desktops via Pushover API.
Supports different priority levels, sounds, and device targeting.

Pushover API: https://pushover.net/api
"""

import os
import logging
from enum import IntEnum
from typing import Optional, List, Dict, Any
from datetime import datetime
import requests
from dotenv import load_dotenv

load_dotenv()


class NotificationPriority(IntEnum):
    """Pushover notification priority levels.

    See: https://pushover.net/api#priority
    """
    LOWEST = -2      # No notification/alert
    LOW = -1         # No sound or vibration
    NORMAL = 0       # Default priority
    HIGH = 1         # High-priority, bypasses quiet hours
    EMERGENCY = 2    # Requires acknowledgment


class PushoverSound:
    """Available Pushover notification sounds.

    See: https://pushover.net/api#sounds
    """
    PUSHOVER = "pushover"           # Default
    BIKE = "bike"
    BUGLE = "bugle"
    CASHREGISTER = "cashregister"   # Good for filled orders
    CLASSICAL = "classical"
    COSMIC = "cosmic"
    FALLING = "falling"
    GAMELAN = "gamelan"
    INCOMING = "incoming"
    INTERMISSION = "intermission"
    MAGIC = "magic"
    MECHANICAL = "mechanical"
    PIANOBAR = "pianobar"
    SIREN = "siren"                 # Good for critical alerts
    SPACEALARM = "spacealarm"       # Good for warnings
    TUGBOAT = "tugboat"
    ALIEN = "alien"
    CLIMB = "climb"
    PERSISTENT = "persistent"
    ECHO = "echo"
    UPDOWN = "updown"
    VIBRATE = "vibrate"
    NONE = "none"


class PushoverNotifier:
    """Send push notifications via Pushover.

    Requires Pushover account and app:
    1. Sign up at https://pushover.net
    2. Create an application to get API token
    3. Note your user key from dashboard

    Environment Variables:
        PUSHOVER_API_TOKEN: Application API token
        PUSHOVER_USER_KEY: Your user key or group key
        PUSHOVER_DEVICE: (Optional) Specific device name to send to
        PUSHOVER_ENABLED: (Optional) Enable/disable notifications (default: true)

    Example:
        >>> notifier = PushoverNotifier()
        >>> notifier.send(
        ...     title="Order Filled",
        ...     message="BPS 6200/6180 filled @ $2.50",
        ...     priority=NotificationPriority.HIGH
        ... )
    """

    API_URL = "https://api.pushover.net/1/messages.json"
    VALIDATE_URL = "https://api.pushover.net/1/users/validate.json"

    def __init__(
        self,
        api_token: Optional[str] = None,
        user_key: Optional[str] = None,
        device: Optional[str] = None,
        enabled: Optional[bool] = None,
        logger: Optional[logging.Logger] = None
    ):
        """Initialize Pushover notifier.

        Args:
            api_token: Pushover API token (from app creation)
            user_key: Pushover user key or group key
            device: Specific device to send to (None = all devices)
            enabled: Enable/disable notifications
            logger: Logger instance
        """
        self.api_token = api_token or os.getenv("PUSHOVER_API_TOKEN")
        self.user_key = user_key or os.getenv("PUSHOVER_USER_KEY")
        self.device = device or os.getenv("PUSHOVER_DEVICE")

        # Parse enabled flag
        enabled_env = os.getenv("PUSHOVER_ENABLED", "true").lower()
        self.enabled = enabled if enabled is not None else (enabled_env == "true")

        self.logger = logger or logging.getLogger(__name__)

        # Validate credentials if enabled
        if self.enabled:
            if not self.api_token or not self.user_key:
                self.logger.error(
                    "Pushover credentials not configured. "
                    "Set PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY environment variables."
                )
                self.enabled = False
            else:
                self.logger.info("Pushover notifier initialized (enabled)")
                if self.device:
                    self.logger.info(f"  Target device: {self.device}")
        else:
            self.logger.info("Pushover notifier initialized (disabled)")

    def validate(self) -> bool:
        """Validate Pushover credentials.

        Returns:
            True if credentials are valid, False otherwise
        """
        if not self.enabled:
            self.logger.warning("Pushover is disabled, skipping validation")
            return False

        try:
            response = requests.post(
                self.VALIDATE_URL,
                data={
                    "token": self.api_token,
                    "user": self.user_key,
                    "device": self.device
                },
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == 1:
                    self.logger.info("✓ Pushover credentials validated successfully")
                    if "devices" in data:
                        self.logger.info(f"  Available devices: {', '.join(data['devices'])}")
                    return True
                else:
                    self.logger.error(f"Pushover validation failed: {data.get('errors')}")
                    return False
            else:
                self.logger.error(f"Pushover API error: {response.status_code}")
                return False

        except requests.RequestException as e:
            self.logger.error(f"Failed to validate Pushover credentials: {e}")
            return False

    def send(
        self,
        message: str,
        title: Optional[str] = None,
        priority: NotificationPriority = NotificationPriority.NORMAL,
        sound: Optional[str] = None,
        url: Optional[str] = None,
        url_title: Optional[str] = None,
        device: Optional[str] = None,
        timestamp: Optional[datetime] = None,
        html: bool = False,
        **kwargs
    ) -> bool:
        """Send a push notification via Pushover.

        Args:
            message: Notification message (required, max 1024 chars)
            title: Notification title (max 250 chars)
            priority: Notification priority level
            sound: Notification sound (see PushoverSound)
            url: Supplementary URL to show with notification
            url_title: Title for supplementary URL
            device: Specific device to send to (overrides default)
            timestamp: Unix timestamp for notification (defaults to now)
            html: Enable HTML formatting in message
            **kwargs: Additional Pushover API parameters

        Returns:
            True if notification sent successfully, False otherwise
        """
        if not self.enabled:
            self.logger.debug(f"Pushover disabled, skipping: {title or message[:50]}")
            return False

        # Build request payload
        payload = {
            "token": self.api_token,
            "user": self.user_key,
            "message": message[:1024],  # Max 1024 characters
        }

        # Optional fields
        if title:
            payload["title"] = title[:250]  # Max 250 characters

        if priority != NotificationPriority.NORMAL:
            payload["priority"] = int(priority)

            # Emergency priority requires retry and expire parameters
            if priority == NotificationPriority.EMERGENCY:
                payload["retry"] = kwargs.get("retry", 60)      # Retry every 60 seconds
                payload["expire"] = kwargs.get("expire", 3600)  # Give up after 1 hour

        if sound:
            payload["sound"] = sound

        if url:
            payload["url"] = url[:512]
            if url_title:
                payload["url_title"] = url_title[:100]

        if device or self.device:
            payload["device"] = device or self.device

        if timestamp:
            payload["timestamp"] = int(timestamp.timestamp())

        if html:
            payload["html"] = 1

        # Add any additional parameters
        for key, value in kwargs.items():
            if key not in payload and key not in ["retry", "expire"]:
                payload[key] = value

        # Send notification
        try:
            response = requests.post(
                self.API_URL,
                data=payload,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == 1:
                    self.logger.debug(f"✓ Pushover notification sent: {title or message[:50]}")
                    return True
                else:
                    self.logger.error(f"Pushover error: {data.get('errors')}")
                    return False
            else:
                self.logger.error(f"Pushover API error: {response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            self.logger.error(f"Failed to send Pushover notification: {e}")
            return False

    def send_order_filled(
        self,
        symbol: str,
        quantity: int,
        price: float,
        order_type: str = "Market",
        **kwargs
    ) -> bool:
        """Send notification for filled order.

        Args:
            symbol: Option symbol or ticker
            quantity: Number of contracts/shares
            price: Fill price
            order_type: Type of order (Market, Limit, etc.)
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        return self.send(
            title="🎯 Order Filled",
            message=f"{order_type}: {quantity} {symbol} @ ${price:.2f}",
            priority=NotificationPriority.HIGH,
            sound=PushoverSound.CASHREGISTER,
            **kwargs
        )

    def send_position_opened(
        self,
        strategy: str,
        symbol: str,
        entry_price: float,
        **kwargs
    ) -> bool:
        """Send notification for new position.

        Args:
            strategy: Strategy name
            symbol: Symbol or position description
            entry_price: Entry price
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        return self.send(
            title="📈 Position Opened",
            message=f"{strategy}: {symbol}\nEntry: ${entry_price:.2f}",
            priority=NotificationPriority.HIGH,
            sound=PushoverSound.INCOMING,
            **kwargs
        )

    def send_position_closed(
        self,
        strategy: str,
        symbol: str,
        pnl: float,
        pnl_pct: Optional[float] = None,
        **kwargs
    ) -> bool:
        """Send notification for closed position.

        Args:
            strategy: Strategy name
            symbol: Symbol or position description
            pnl: Profit/loss amount
            pnl_pct: Profit/loss percentage (optional)
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        pnl_emoji = "💰" if pnl >= 0 else "📉"
        pnl_str = f"${pnl:+.2f}"
        if pnl_pct is not None:
            pnl_str += f" ({pnl_pct:+.1f}%)"

        return self.send(
            title=f"{pnl_emoji} Position Closed",
            message=f"{strategy}: {symbol}\nP&L: {pnl_str}",
            priority=NotificationPriority.HIGH,
            sound=PushoverSound.CASHREGISTER if pnl >= 0 else PushoverSound.FALLING,
            **kwargs
        )

    def send_critical_alert(
        self,
        alert_type: str,
        message: str,
        **kwargs
    ) -> bool:
        """Send critical alert notification.

        Args:
            alert_type: Type of alert (e.g., "Risk Limit", "System Error")
            message: Alert message
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        return self.send(
            title=f"🚨 {alert_type}",
            message=message,
            priority=NotificationPriority.EMERGENCY,
            sound=PushoverSound.SIREN,
            **kwargs
        )

    def send_warning(
        self,
        warning_type: str,
        message: str,
        **kwargs
    ) -> bool:
        """Send warning notification.

        Args:
            warning_type: Type of warning
            message: Warning message
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        return self.send(
            title=f"⚠️ {warning_type}",
            message=message,
            priority=NotificationPriority.HIGH,
            sound=PushoverSound.SPACEALARM,
            **kwargs
        )

    def send_info(
        self,
        title: str,
        message: str,
        **kwargs
    ) -> bool:
        """Send informational notification.

        Args:
            title: Notification title
            message: Information message
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        return self.send(
            title=f"ℹ️ {title}",
            message=message,
            priority=NotificationPriority.NORMAL,
            **kwargs
        )

    def send_engine_started(
        self,
        mode: str = "live",
        strategies: Optional[List[str]] = None,
        **kwargs
    ) -> bool:
        """Send notification when trading engine starts.

        Args:
            mode: Trading mode (live, paper, backtest)
            strategies: List of enabled strategies
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        msg = f"Trading engine started in {mode.upper()} mode"
        if strategies:
            msg += f"\nStrategies: {', '.join(strategies)}"

        return self.send(
            title="🚀 Engine Started",
            message=msg,
            priority=NotificationPriority.HIGH,
            **kwargs
        )

    def send_engine_stopped(
        self,
        reason: Optional[str] = None,
        stats: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> bool:
        """Send notification when trading engine stops.

        Args:
            reason: Reason for stopping (optional)
            stats: Session statistics (optional)
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        msg = "Trading engine stopped"
        if reason:
            msg += f"\nReason: {reason}"
        if stats:
            if "trades" in stats:
                msg += f"\nTrades: {stats['trades']}"
            if "pnl" in stats:
                msg += f"\nP&L: ${stats['pnl']:+.2f}"

        return self.send(
            title="🛑 Engine Stopped",
            message=msg,
            priority=NotificationPriority.HIGH,
            **kwargs
        )

    def send_daily_summary(
        self,
        date: datetime,
        trades: int,
        pnl: float,
        win_rate: Optional[float] = None,
        **kwargs
    ) -> bool:
        """Send daily trading summary.

        Args:
            date: Trading date
            trades: Number of trades
            pnl: Total P&L
            win_rate: Win rate percentage (optional)
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        msg = f"Date: {date.strftime('%Y-%m-%d')}\n"
        msg += f"Trades: {trades}\n"
        msg += f"P&L: ${pnl:+.2f}"
        if win_rate is not None:
            msg += f"\nWin Rate: {win_rate:.1f}%"

        emoji = "📊"
        if pnl > 0:
            emoji = "💰"
        elif pnl < 0:
            emoji = "📉"

        return self.send(
            title=f"{emoji} Daily Summary",
            message=msg,
            priority=NotificationPriority.NORMAL,
            **kwargs
        )


# Convenience function for quick notifications
def send_notification(
    message: str,
    title: Optional[str] = None,
    priority: NotificationPriority = NotificationPriority.NORMAL,
    **kwargs
) -> bool:
    """Send a quick notification using default settings.

    Args:
        message: Notification message
        title: Notification title
        priority: Priority level
        **kwargs: Additional parameters

    Returns:
        True if sent successfully

    Example:
        >>> from quant_vibe.notifications import send_notification, NotificationPriority
        >>> send_notification("Test message", "Test", NotificationPriority.HIGH)
    """
    notifier = PushoverNotifier()
    return notifier.send(message, title=title, priority=priority, **kwargs)
