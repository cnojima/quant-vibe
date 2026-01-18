"""Pushover notification service for real-time alerts.

Provides push notifications to mobile devices and desktops via Pushover API.
Supports different priority levels, sounds, and device targeting.

Pushover API: https://pushover.net/api
"""

import os

import json
from enum import IntEnum
from typing import Optional, List, Dict, Any
from datetime import datetime
import requests
from dotenv import load_dotenv

from quant_vibe.logging import get_logger
load_dotenv()

# Import database store for logging notifications
try:
    from quant_vibe.data.timescale_store import TimescaleStore
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


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
        db_logging: bool = True,
    ):
        """Initialize Pushover notifier.

        Args:
            api_token: Pushover API token (from app creation)
            user_key: Pushover user key or group key
            device: Specific device to send to (None = all devices)
            enabled: Enable/disable notifications
            db_logging: Enable database logging of notifications (default: True)
        """
        self.api_token = api_token or os.getenv("PUSHOVER_API_TOKEN")
        self.user_key = user_key or os.getenv("PUSHOVER_USER_KEY")
        self.device = device or os.getenv("PUSHOVER_DEVICE")

        # Parse enabled flag
        enabled_env = os.getenv("PUSHOVER_ENABLED", "true").lower()
        self.enabled = enabled if enabled is not None else (enabled_env == "true")

        self.logger = get_logger(__name__)

        # Database logging configuration
        self.db_logging = db_logging and DB_AVAILABLE
        self._db_store = None
        if self.db_logging:
            try:
                self._db_store = TimescaleStore()
                self.logger.debug("Database logging enabled for notifications")
            except Exception as e:
                self.logger.warning(f"Failed to initialize database logging: {e}")
                self.db_logging = False

        # Validate credentials if enabled
        if self.enabled:
            if not self.api_token or not self.user_key:
                self.logger.warning(
                    "Pushover credentials not configured. Notifications will be disabled. "
                    "Set PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY environment variables to enable."
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

    def _log_to_database(
        self,
        title: Optional[str],
        message: str,
        notification_type: str,
        priority: NotificationPriority,
        sound: Optional[str],
        device: Optional[str],
        url: Optional[str],
        url_title: Optional[str],
        sent_successfully: bool,
        error_message: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log notification to database for audit trail.

        Args:
            title: Notification title
            message: Notification message
            notification_type: Type of notification
            priority: Priority level
            sound: Sound used
            device: Target device
            url: Supplementary URL
            url_title: URL title
            sent_successfully: Whether notification was sent successfully
            error_message: Error message if failed
            metadata: Additional metadata (JSON)
        """
        if not self.db_logging or self._db_store is None:
            return

        try:
            with self._db_store.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO notifications (
                            title, message, notification_type, priority, sound, device,
                            sent_successfully, error_message, metadata, url, url_title
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            title,
                            message,
                            notification_type,
                            int(priority),
                            sound,
                            device,
                            sent_successfully,
                            error_message,
                            json.dumps(metadata) if metadata else None,
                            url,
                            url_title,
                        ),
                    )
                    conn.commit()
                    self.logger.debug(f"Logged notification to database: {notification_type}")
        except Exception as e:
            self.logger.warning(f"Failed to log notification to database: {e}")

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
        notification_type: str = "custom",
        metadata: Optional[Dict[str, Any]] = None,
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
            notification_type: Type of notification for database logging
            metadata: Additional metadata for database logging (JSON)
            **kwargs: Additional Pushover API parameters

        Returns:
            True if notification sent successfully, False otherwise
        """
        if not self.enabled:
            self.logger.debug(f"Pushover disabled, skipping: {title or message[:50]}")
            # Still log to database even if disabled
            if self.db_logging:
                self._log_to_database(
                    title=title,
                    message=message,
                    notification_type=notification_type,
                    priority=priority,
                    sound=sound,
                    device=device or self.device,
                    url=url,
                    url_title=url_title,
                    sent_successfully=False,
                    error_message="Pushover disabled",
                    metadata=metadata,
                )
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
        sent_successfully = False
        error_msg = None
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
                    sent_successfully = True
                else:
                    error_msg = f"Pushover error: {data.get('errors')}"
                    self.logger.error(error_msg)
            else:
                error_msg = f"Pushover API error: {response.status_code} - {response.text}"
                self.logger.error(error_msg)

        except requests.RequestException as e:
            error_msg = f"Failed to send Pushover notification: {e}"
            self.logger.error(error_msg)

        # Log to database
        if self.db_logging:
            self._log_to_database(
                title=title,
                message=message,
                notification_type=notification_type,
                priority=priority,
                sound=sound,
                device=device or self.device,
                url=url,
                url_title=url_title,
                sent_successfully=sent_successfully,
                error_message=error_msg,
                metadata=metadata,
            )

        return sent_successfully

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
            notification_type="order_filled",
            metadata={"symbol": symbol, "quantity": quantity, "price": price, "order_type": order_type},
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
            notification_type="position_opened",
            metadata={"strategy": strategy, "symbol": symbol, "entry_price": entry_price},
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
            notification_type="position_closed",
            metadata={"strategy": strategy, "symbol": symbol, "pnl": pnl, "pnl_pct": pnl_pct},
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
            notification_type="critical_alert",
            metadata={"alert_type": alert_type},
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
            notification_type="warning",
            metadata={"warning_type": warning_type},
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
            notification_type="info",
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
            notification_type="engine_started",
            metadata={"mode": mode, "strategies": strategies},
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
            notification_type="engine_stopped",
            metadata={"reason": reason, "stats": stats},
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
            notification_type="daily_summary",
            metadata={"date": date.isoformat(), "trades": trades, "pnl": pnl, "win_rate": win_rate},
            **kwargs
        )

    def send_optimization_complete(
        self,
        strategy_name: str,
        optimization_id: str,
        best_sharpe: Optional[float] = None,
        best_return: Optional[float] = None,
        runtime_minutes: Optional[float] = None,
        **kwargs
    ) -> bool:
        """Send notification for completed optimization.

        Args:
            strategy_name: Name of optimized strategy
            optimization_id: Unique optimization ID
            best_sharpe: Best Sharpe ratio found
            best_return: Best return percentage
            runtime_minutes: Optimization runtime in minutes
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        msg = f"Optimization {optimization_id} finished successfully."
        if best_sharpe is not None:
            msg += f"\nBest Sharpe: {best_sharpe:.2f}"
        if best_return is not None:
            msg += f"\nBest Return: {best_return:+.2f}%"
        if runtime_minutes is not None:
            msg += f"\nRuntime: {runtime_minutes:.1f} min"

        return self.send(
            title=f"✅ Optimization Complete: {strategy_name}",
            message=msg,
            priority=NotificationPriority.NORMAL,
            sound=PushoverSound.CASHREGISTER,
            notification_type="optimization_complete",
            metadata={
                "strategy_name": strategy_name,
                "optimization_id": optimization_id,
                "best_sharpe": best_sharpe,
                "best_return": best_return,
                "runtime_minutes": runtime_minutes,
            },
            **kwargs
        )

    def send_optimization_failed(
        self,
        strategy_name: str,
        optimization_id: str,
        error_message: str,
        runtime_minutes: Optional[float] = None,
        **kwargs
    ) -> bool:
        """Send notification for failed optimization.

        Args:
            strategy_name: Name of optimized strategy
            optimization_id: Unique optimization ID
            error_message: Error description
            runtime_minutes: Optimization runtime in minutes
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        msg = f"Optimization {optimization_id} failed."
        msg += f"\nError: {error_message[:200]}"  # Truncate long errors
        if runtime_minutes is not None:
            msg += f"\nRuntime: {runtime_minutes:.1f} min"

        return self.send(
            title=f"❌ Optimization Failed: {strategy_name}",
            message=msg,
            priority=NotificationPriority.HIGH,
            sound=PushoverSound.SIREN,
            notification_type="optimization_failed",
            metadata={
                "strategy_name": strategy_name,
                "optimization_id": optimization_id,
                "error_message": error_message[:200],
                "runtime_minutes": runtime_minutes,
            },
            **kwargs
        )

    def send_backtest_complete(
        self,
        strategy_name: str,
        backtest_id: str,
        total_return: Optional[float] = None,
        sharpe_ratio: Optional[float] = None,
        num_trades: Optional[int] = None,
        **kwargs
    ) -> bool:
        """Send notification for completed backtest.

        Args:
            strategy_name: Name of strategy
            backtest_id: Unique backtest ID
            total_return: Total return percentage
            sharpe_ratio: Sharpe ratio
            num_trades: Number of trades
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        msg = f"Backtest {backtest_id} finished."
        if total_return is not None:
            msg += f"\nReturn: {total_return:+.2f}%"
        if sharpe_ratio is not None:
            msg += f"\nSharpe: {sharpe_ratio:.2f}"
        if num_trades is not None:
            msg += f"\nTrades: {num_trades}"

        return self.send(
            title=f"✅ Backtest Complete: {strategy_name}",
            message=msg,
            priority=NotificationPriority.NORMAL,
            sound=PushoverSound.MAGIC,
            notification_type="backtest_complete",
            metadata={
                "strategy_name": strategy_name,
                "backtest_id": backtest_id,
                "total_return": total_return,
                "sharpe_ratio": sharpe_ratio,
                "num_trades": num_trades,
            },
            **kwargs
        )

    def send_backtest_failed(
        self,
        strategy_name: str,
        backtest_id: str,
        error_message: str,
        **kwargs
    ) -> bool:
        """Send notification for failed backtest.

        Args:
            strategy_name: Name of strategy
            backtest_id: Unique backtest ID
            error_message: Error description
            **kwargs: Additional parameters for send()

        Returns:
            True if sent successfully
        """
        msg = f"Backtest {backtest_id} failed.\nError: {error_message[:200]}"

        return self.send(
            title=f"❌ Backtest Failed: {strategy_name}",
            message=msg,
            priority=NotificationPriority.HIGH,
            sound=PushoverSound.SIREN,
            notification_type="backtest_failed",
            metadata={
                "strategy_name": strategy_name,
                "backtest_id": backtest_id,
                "error_message": error_message[:200],
            },
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

        """
    notifier = PushoverNotifier()
    return notifier.send(message, title=title, priority=priority, **kwargs)
