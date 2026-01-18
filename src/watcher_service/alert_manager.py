"""Alert management with escalation, de-duplication, and notifications."""

import threading
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from quant_vibe.utils import now_utc
from watcher_service.config import AlertLevel, NotificationConfig
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
        """Initialize alert."""
        self.service = service
        self.level = level
        self.message = message
        self.details = details
        self.first_seen = now_utc()
        self.last_seen = now_utc()
        self.count = 1
        self.notified = False
        self.notified_at: Optional[datetime] = None

    def update(self) -> None:
        """Update alert (seen again)."""
        self.last_seen = now_utc()
        self.count += 1

    def should_notify(self, min_interval_seconds: int = 300) -> bool:
        """Check if alert should trigger notification."""
        if not self.notified:
            return True

        if self.notified_at:
            elapsed = (now_utc() - self.notified_at).total_seconds()
            return elapsed >= min_interval_seconds

        return False

    def mark_notified(self) -> None:
        """Mark alert as notified."""
        self.notified = True
        self.notified_at = now_utc()


class AlertManager:
    """Manages alerts with de-duplication and notifications."""

    def __init__(self, config: NotificationConfig, logger):
        """Initialize alert manager."""
        self.config = config
        self.logger = logger
        self.active_alerts: Dict[tuple, Alert] = {}
        self.alert_lock = threading.Lock()
        self.alert_history = []
        self.notifier = None

    def set_notifier(self, notifier) -> None:
        """Set notification client."""
        self.notifier = notifier
        self.logger.info("Alert notifier configured")

    def check_rules(
        self,
        service_name: str,
        health_data: Dict[str, Any],
    ) -> Optional[Alert]:
        """Check if any alert rules match the current health data."""
        for rule in self.config.rules:
            if service_name not in rule.services:
                continue

            try:
                context = {
                    "status": health_data.get("overall_status", HealthStatus.UNKNOWN),
                    "missed_heartbeats": health_data.get("missed_heartbeats", 0),
                    "missing": health_data.get("seconds_since_heartbeat", 0),
                    "HealthStatus": HealthStatus,
                }

                if self._evaluate_condition(rule.condition, context):
                    message = rule.message.replace("{{service}}", service_name)
                    message = message.replace(
                        "{{count}}", str(context.get("missed_heartbeats", 0))
                    )

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
        """Safely evaluate a condition string."""
        try:
            condition = condition.replace(
                "status == unhealthy", "status == HealthStatus.UNHEALTHY"
            )
            condition = condition.replace(
                "status == healthy", "status == HealthStatus.HEALTHY"
            )
            condition = condition.replace(
                "status == degraded", "status == HealthStatus.DEGRADED"
            )

            result = eval(condition, {"__builtins__": {}}, context)
            return bool(result)

        except Exception as e:
            self.logger.warning(f"Failed to evaluate condition '{condition}': {e}")
            return False

    def process_alert(self, alert: Alert) -> None:
        """Process an alert (de-duplicate, escalate, notify)."""
        alert_key = (alert.service, alert.level)

        with self.alert_lock:
            existing = self.active_alerts.get(alert_key)

            if existing:
                existing.update()
                alert = existing
            else:
                self.active_alerts[alert_key] = alert
                self.alert_history.append(
                    {
                        "service": alert.service,
                        "level": alert.level.value,
                        "message": alert.message,
                        "timestamp": alert.first_seen.isoformat(),
                    }
                )

        if self.config.enabled and alert.should_notify():
            self._send_notification(alert)
            alert.mark_notified()

    def clear_alert(self, service: str, level: AlertLevel) -> None:
        """Clear an active alert (service recovered)."""
        alert_key = (service, level)

        with self.alert_lock:
            if alert_key in self.active_alerts:
                alert = self.active_alerts[alert_key]
                del self.active_alerts[alert_key]

                self.logger.info(
                    f"Cleared {level.value} alert for {service} "
                    f"(active for {(now_utc() - alert.first_seen).total_seconds():.0f}s)"
                )

                if (
                    self.config.enabled
                    and self.config.send_recovery_notifications
                    and self.notifier
                ):
                    self._send_recovery_notification(alert)

    def clear_all_alerts_for_service(self, service: str) -> None:
        """Clear all active alerts for a service."""
        with self.alert_lock:
            alerts_to_clear = [
                (svc, level)
                for (svc, level) in self.active_alerts.keys()
                if svc == service
            ]

        for svc, level in alerts_to_clear:
            self.clear_alert(svc, level)

    def _send_notification(self, alert: Alert) -> None:
        """Send alert notification via configured channels."""
        if not self.notifier:
            self.logger.warning("No notifier configured - skipping alert notification")
            return

        try:
            priority_map = {
                AlertLevel.INFO: -1,
                AlertLevel.WARNING: 0,
                AlertLevel.CRITICAL: 1,
                AlertLevel.EMERGENCY: 2,
            }

            priority = priority_map.get(alert.level, 0)

            title = f"[{alert.level.value.upper()}] {alert.service}"
            body = alert.message
            if alert.details:
                body += f"\n\nDetails: {alert.details}"

            if hasattr(self.notifier, "send"):
                self.notifier.send(
                    message=body,
                    title=title,
                    priority=priority,
                )
            elif hasattr(self.notifier, "send_notification"):
                self.notifier.send_notification(
                    message=body,
                    title=title,
                    priority=priority,
                )
            elif hasattr(self.notifier, "send_alert"):
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

    def _send_recovery_notification(self, alert: Alert) -> None:
        """Send recovery notification."""
        if not self.notifier:
            return

        try:
            duration = (now_utc() - alert.first_seen).total_seconds()
            duration_str = f"{int(duration // 60)}m {int(duration % 60)}s"

            title = f"[RECOVERY] {alert.service}"
            body = (
                f"Service {alert.service} has recovered from {alert.level.value} alert.\n\n"
                f"Alert was active for {duration_str}.\n"
                f"Original issue: {alert.message}"
            )

            if hasattr(self.notifier, "send"):
                self.notifier.send(
                    message=body,
                    title=title,
                    priority=-1,
                )
            elif hasattr(self.notifier, "send_notification"):
                self.notifier.send_notification(
                    message=body,
                    title=title,
                    priority=-1,
                )

            self.logger.info(f"Sent recovery notification for {alert.service}")

        except Exception as e:
            self.logger.error(
                f"Failed to send recovery notification: {e}", exc_info=True
            )

    def get_active_alerts(self) -> Dict[str, Any]:
        """Get all active alerts."""
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
        """Get recent alert history."""
        return self.alert_history[-limit:]

    def cleanup_old_history(self, max_age_hours: int = 24) -> None:
        """Clean up old alert history."""
        cutoff = now_utc() - timedelta(hours=max_age_hours)

        self.alert_history = [
            alert
            for alert in self.alert_history
            if datetime.fromisoformat(alert["timestamp"]) > cutoff
        ]