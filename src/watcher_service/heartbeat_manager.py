"""Heartbeat tracking and management via Redis."""

import json
import threading
from datetime import timedelta
from typing import Dict, Any

from watcher_service.service_monitor import HealthStatus
from quant_vibe.utils import now_utc


class HeartbeatManager:
    """Manages heartbeat tracking for services via Redis pub/sub."""

    def __init__(self, redis_broker, logger, heartbeat_timeout_seconds: int = 90):
        """Initialize heartbeat manager.

        Args:
            redis_broker: RedisMessageBroker instance
            logger: Logger instance
            heartbeat_timeout_seconds: Time before heartbeat is considered stale
        """
        self.redis_broker = redis_broker
        self.logger = logger
        self.heartbeat_timeout = heartbeat_timeout_seconds

        # Track last heartbeat per service: {service_name: {timestamp, data}}
        self.heartbeats: Dict[str, Dict[str, Any]] = {}
        self.heartbeat_lock = threading.Lock()

        # Subscribed topics
        self.subscribed_topics = []

    def subscribe_to_heartbeats(self, service_topics: Dict[str, str]):
        """Subscribe to heartbeat topics for services.

        Args:
            service_topics: Dict of {service_name: topic_name}
        """
        topics = list(service_topics.values())

        if not topics:
            self.logger.info("No heartbeat topics to subscribe to")
            return

        self.logger.info(f"Subscribing to {len(topics)} heartbeat topics")

        # Create callback to handle heartbeat messages
        def on_heartbeat(topic: str, message: Any):
            """Handle incoming heartbeat message."""
            try:
                # Parse message if it's a string
                if isinstance(message, str):
                    data = json.loads(message)
                else:
                    data = message

                service_name = data.get("service", "unknown")

                with self.heartbeat_lock:
                    self.heartbeats[service_name] = {
                        "timestamp": now_utc(),
                        "data": data,
                        "topic": topic,
                    }

                self.logger.debug(
                    f"Heartbeat received from {service_name} "
                    f"(status: {data.get('status', 'unknown')})"
                )

            except json.JSONDecodeError as e:
                self.logger.warning(f"Failed to parse heartbeat message: {e}")
            except Exception as e:
                self.logger.error(f"Error handling heartbeat: {e}", exc_info=True)

        # Subscribe to all topics
        try:
            self.redis_broker.subscribe(topics, callback=on_heartbeat)
            self.subscribed_topics = topics
            self.logger.info(f"Subscribed to heartbeat topics: {', '.join(topics)}")
        except Exception as e:
            self.logger.error(f"Failed to subscribe to heartbeats: {e}", exc_info=True)

    def get_heartbeat_status(self, service_name: str) -> Dict[str, Any]:
        """Get heartbeat status for a service.

        Args:
            service_name: Name of service

        Returns:
            Dict with status, last_heartbeat, seconds_since_heartbeat, data
        """
        with self.heartbeat_lock:
            heartbeat = self.heartbeats.get(service_name)

        if not heartbeat:
            return {
                "status": HealthStatus.UNKNOWN,
                "details": "No heartbeat received",
                "last_heartbeat": None,
                "seconds_since_heartbeat": 0,
                "missed_heartbeats": 0,
            }

        # Calculate time since last heartbeat
        last_timestamp = heartbeat["timestamp"]
        now = now_utc()
        seconds_since = (now - last_timestamp).total_seconds()

        # Estimate missed heartbeats (assuming 30s interval)
        missed_count = max(0, int(seconds_since / 30) - 1)

        # Determine status based on timeout
        if seconds_since < self.heartbeat_timeout:
            status = HealthStatus.HEALTHY
            details = f"Last heartbeat {seconds_since:.0f}s ago"
        elif seconds_since < self.heartbeat_timeout * 2:
            status = HealthStatus.DEGRADED
            details = f"Heartbeat stale ({seconds_since:.0f}s, {missed_count} missed)"
        else:
            status = HealthStatus.UNHEALTHY
            details = f"Heartbeat timeout ({seconds_since:.0f}s, {missed_count} missed)"

        return {
            "status": status,
            "details": details,
            "last_heartbeat": last_timestamp.isoformat(),
            "seconds_since_heartbeat": round(seconds_since, 1),
            "missed_heartbeats": missed_count,
            "data": heartbeat.get("data", {}),
        }

    def get_all_heartbeat_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Get heartbeat status for all tracked services.

        Returns:
            Dict of {service_name: status_dict}
        """
        statuses = {}
        with self.heartbeat_lock:
            service_names = list(self.heartbeats.keys())

        for service_name in service_names:
            statuses[service_name] = self.get_heartbeat_status(service_name)

        return statuses

    def publish_heartbeat(self, service_name: str, status: str, metrics: Dict[str, Any]):
        """Publish a heartbeat message (for testing or local services).

        Args:
            service_name: Name of service
            status: Status string (healthy, degraded, unhealthy)
            metrics: Dict of metrics to include
        """
        message = {
            "service": service_name,
            "timestamp": now_utc().isoformat(),
            "status": status,
            "metrics": metrics,
        }

        topic = f"heartbeat.{service_name}"

        try:
            self.redis_broker.publish(topic, message)
            self.logger.debug(f"Published heartbeat for {service_name}")
        except Exception as e:
            self.logger.error(f"Failed to publish heartbeat: {e}", exc_info=True)

    def cleanup_stale_heartbeats(self, max_age_hours: int = 24):
        """Remove heartbeats older than max_age_hours.

        Args:
            max_age_hours: Maximum age in hours before cleanup
        """
        cutoff = now_utc() - timedelta(hours=max_age_hours)
        removed = []

        with self.heartbeat_lock:
            for service_name, heartbeat in list(self.heartbeats.items()):
                if heartbeat["timestamp"] < cutoff:
                    del self.heartbeats[service_name]
                    removed.append(service_name)

        if removed:
            self.logger.info(f"Cleaned up stale heartbeats: {', '.join(removed)}")

    def stop(self):
        """Stop listening to heartbeats."""
        if self.subscribed_topics:
            self.logger.info("Stopping heartbeat listener")
            # Note: RedisMessageBroker.listen() is blocking,
            # stopping is handled by the main watcher loop
