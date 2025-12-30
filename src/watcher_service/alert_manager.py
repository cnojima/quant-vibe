"""Alert management with escalation, de-duplication, and notifications."""

import threading
from datetime import datetime, timedelta
from typing import Dict, Set, Optional, Any

from watcher_service.config import NotificationConfig, AlertLevel, NotificationRule
from watcher_service.service_monitor import HealthStatus


class Alert:
    """Represents an active alert."""

    def __init__(
        self,
        service: str,
        level: AlertLevel,
        message: str,
        details: Optional[str] = None,
    ):
        """Initialize alert.

        Args:
            service: Service name
            level: Alert level
            message: Alert message
            details: Additional details
        """
        self.service = service
        self.level = level
        self.message = message
        self.details = details
        self.first_seen = datetime.utcnow()
        self.last_seen = datetime.utcnow()
        self.count = 1
        self.notified = False
        self.notified_at: Optional[datetime] = None

    def update(self):
        """Update alert (seen again)."""
        self.last_seen = datetime.utcnow()
        self.count += 1

    def should_notify(self, min_interval_seconds: int = 300) -> bool:
        """Check if alert should trigger notification.

        Args:
            min_interval_seconds: Minimum seconds between notifications

        Returns:
            True if should notify
        """
        if not self.notified:
            return True

        # Re-notify if enough time has passed
        if self.notified_at:
            elapsed = (datetime.utcnow() - self.notified_at).total_seconds()
            return elapsed >= min_interval_seconds

        return False

    def mark_notified(self):
        """Mark alert as notified."""
        self.notified = True
        self.notified_at = datetime.utcnow()


class AlertManager:
    """Manages alerts with de-duplication and notifications."""

    def __init__(self, config: NotificationConfig, logger):
        """Initialize alert manager.

        Args:
            config: Notification configuration
            logger: Logger instance
        """
        self.config = config
        self.logger = logger

        # Active alerts: {(service, level): Alert}
        self.active_alerts: Dict[tuple, Alert] = {}
        self.alert_lock = threading.Lock()

        # Alert history for tracking
        self.alert_history = []

        # Notification client (will be set later)
        self.notifier = None

    def set_notifier(self, notifier):
        """Set notification client.

        Args:
            notifier: PushoverNotifier or TradingNotifier instance
        """
        self.notifier = notifier
        self.logger.info("Alert notifier configured")

    def check_rules(
        self,
        service_name: str,
        health_data: Dict[str, Any],
    ) -> Optional[Alert]:
        """Check if any alert rules match the current health data.

        Args:
            service_name: Name of service
            health_data: Health check data including status, metrics, etc.

        Returns:
            Alert instance if rule matched, None otherwise
        """
        for rule in self.config.rules:
            # Check if rule applies to this service
            if service_name not in rule.services:
                continue

            # Evaluate condition
            try:
                # Create context for condition evaluation
                context = {
                    "status": health_data.get("overall_status", HealthStatus.UNKNOWN),
                    "missed_heartbeats": health_data.get("missed_heartbeats", 0),
                    "missing": health_data.get("seconds_since_heartbeat", 0),
                    "HealthStatus": HealthStatus,  # For comparisons
                }

                # Parse and evaluate condition
                # Simple condition format: "missed_heartbeats >= 3"
                if self._evaluate_condition(rule.condition, context):
                    # Format message with placeholders
                    message = rule.message.replace("{{service}}", service_name)
                    message = message.replace(
                        "{{count}}", str(context.get("missed_heartbeats", 0))
                    )

                    # Create alert
                    return Alert(
                        service=service_name,
                        level=rule.level,
                        message=message,
                        details=health_data.get("details"),
                    )

            except Exception as e:
                self.logger.error(
                    f"Error evaluating rule condition '{rule.condition}': {e}"
                )

        return None

    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Safely evaluate a condition string.

        Args:
            condition: Condition string (e.g., "missed_heartbeats >= 3")
            context: Variables available for evaluation

        Returns:
            True if condition is met
        """
        try:
            # Simple condition parsing
            # Support: missed_heartbeats >= 3, status == unhealthy, missing >= 300

            # Replace status comparisons
            condition = condition.replace(
                "status == unhealthy", "status == HealthStatus.UNHEALTHY"
            )
            condition = condition.replace(
                "status == healthy", "status == HealthStatus.HEALTHY"
            )
            condition = condition.replace(
                "status == degraded", "status == HealthStatus.DEGRADED"
            )

            # Evaluate using eval (safe because we control the condition strings)
            result = eval(condition, {"__builtins__": {}}, context)
            return bool(result)

        except Exception as e:
            self.logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return False

    def process_alert(self, alert: Alert):
        """Process an alert (de-duplicate, escalate, notify).

        Args:
            alert: Alert instance
        """
        alert_key = (alert.service, alert.level)

        with self.alert_lock:
            existing = self.active_alerts.get(alert_key)

            if existing:
                # Alert already active - update it
                existing.update()
                alert = existing
            else:
                # New alert
                self.active_alerts[alert_key] = alert
                self.alert_history.append(
                    {
                        "service": alert.service,
                        "level": alert.level.value,
                        "message": alert.message,
                        "timestamp": alert.first_seen.isoformat(),
                    }
                )

        # Check if should notify
        if self.config.enabled and alert.should_notify():
            self._send_notification(alert)
            alert.mark_notified()

    def clear_alert(self, service: str, level: AlertLevel):
        """Clear an active alert (service recovered).

        Args:
            service: Service name
            level: Alert level to clear
        """
        alert_key = (service, level)

        with self.alert_lock:
            if alert_key in self.active_alerts:
                alert = self.active_alerts[alert_key]
                del self.active_alerts[alert_key]

                self.logger.info(
                    f"Cleared {level.value} alert for {service} "
                    f"(active for {(datetime.utcnow() - alert.first_seen).total_seconds():.0f}s)"
                )

                # Send recovery notification
                if self.config.enabled and self.notifier:
                    self._send_recovery_notification(alert)

    def _send_notification(self, alert: Alert):
        """Send alert notification via configured channels.

        Args:
            alert: Alert instance
        """
        if not self.notifier:
            self.logger.warning("No notifier configured - skipping alert notification")
            return

        try:
            # Map alert level to Pushover priority
            priority_map = {
                AlertLevel.INFO: -1,  # Lowest
                AlertLevel.WARNING: 0,  # Normal
                AlertLevel.CRITICAL: 1,  # High
                AlertLevel.EMERGENCY: 2,  # Emergency (requires acknowledgment)
            }

            priority = priority_map.get(alert.level, 0)

            # Format message
            title = f"[{alert.level.value.upper()}] {alert.service}"
            body = alert.message
            if alert.details:
                body += f"\n\nDetails: {alert.details}"

            # Send via notifier
            if hasattr(self.notifier, "send_notification"):
                # PushoverNotifier
                self.notifier.send_notification(
                    message=body,
                    title=title,
                    priority=priority,
                )
            elif hasattr(self.notifier, "send_alert"):
                # TradingNotifier or custom
                self.notifier.send_alert(
                    level=alert.level.value,
                    service=alert.service,
                    message=alert.message,
                    details=alert.details,
                )

            self.logger.info(
                f"Sent {alert.level.value} notification for {alert.service}"
            )

        except Exception as e:
            self.logger.error(
                f"Failed to send notification for {alert.service}: {e}",
                exc_info=True,
            )

    def _send_recovery_notification(self, alert: Alert):
        """Send recovery notification.

        Args:
            alert: Recovered alert
        """
        if not self.notifier:
            return

        try:
            title = f"[RECOVERY] {alert.service}"
            body = f"Service {alert.service} has recovered from {alert.level.value} alert"

            if hasattr(self.notifier, "send_notification"):
                self.notifier.send_notification(
                    message=body,
                    title=title,
                    priority=-1,  # Low priority for recovery
                )

            self.logger.info(f"Sent recovery notification for {alert.service}")

        except Exception as e:
            self.logger.error(
                f"Failed to send recovery notification: {e}", exc_info=True
            )

    def get_active_alerts(self) -> Dict[str, Any]:
        """Get all active alerts.

        Returns:
            Dict of active alerts by service
        """
        with self.alert_lock:
            return {
                service: {
                    "level": alert.level.value,
                    "message": alert.message,
                    "details": alert.details,
                    "first_seen": alert.first_seen.isoformat(),
                    "last_seen": alert.last_seen.isoformat(),
                    "count": alert.count,
                }
                for (service, level), alert in self.active_alerts.items()
            }

    def get_alert_history(self, limit: int = 100) -> list:
        """Get recent alert history.

        Args:
            limit: Maximum number of alerts to return

        Returns:
            List of recent alerts
        """
        return self.alert_history[-limit:]

    def cleanup_old_history(self, max_age_hours: int = 24):
        """Clean up old alert history.

        Args:
            max_age_hours: Maximum age in hours
        """
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)

        # Keep only recent alerts
        self.alert_history = [
            alert
            for alert in self.alert_history
            if datetime.fromisoformat(alert["timestamp"]) > cutoff
        ]
