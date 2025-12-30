"""Main watcher service orchestrator."""

import sys
import time
import signal
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from quant_vibe.config.logging_config import setup_normalized_logging
from quant_vibe.messaging import RedisMessageBroker
from watcher_service.config import WatcherConfig, ServiceType
from watcher_service.service_monitor import ServiceMonitor, HealthStatus
from watcher_service.heartbeat_manager import HeartbeatManager
from watcher_service.alert_manager import AlertManager

# Optional: Import Pushover notifier if available
try:
    from quant_vibe.notifications import PushoverNotifier

    PUSHOVER_AVAILABLE = True
except ImportError:
    PUSHOVER_AVAILABLE = False
    PushoverNotifier = None


class WatcherService:
    """Main watcher service for monitoring system health."""

    def __init__(self, config: Optional[WatcherConfig] = None):
        """Initialize watcher service.

        Args:
            config: Watcher configuration (loads from file if not provided)
        """
        load_dotenv()

        # Load config
        self.config = config or WatcherConfig.from_yaml()

        # Setup normalized logging
        self.logger = setup_normalized_logging(
            app_name="watcher",
            log_level="INFO",
            log_dir="logs/watcher",
        )

        self.logger.info("=" * 70)
        self.logger.info("Watcher Service Initializing")
        self.logger.info("=" * 70)

        self.logger.info(f"Monitoring {len(self.config.services)} services")
        self.logger.info(
            f"Check interval: {self.config.check_interval_seconds}s"
        )
        self.logger.info(
            f"Heartbeat timeout: {self.config.heartbeat_timeout_seconds}s"
        )

        # Initialize components
        self.service_monitor = ServiceMonitor(self.logger)
        self.redis_broker = RedisMessageBroker()
        self.heartbeat_manager = HeartbeatManager(
            self.redis_broker,
            self.logger,
            self.config.heartbeat_timeout_seconds,
        )
        self.alert_manager = AlertManager(
            self.config.notifications, self.logger
        )

        # Initialize notifier if enabled
        if self.config.notifications.enabled and PUSHOVER_AVAILABLE:
            try:
                self.notifier = PushoverNotifier()
                self.alert_manager.set_notifier(self.notifier)
                self.logger.info("Pushover notifications enabled")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Pushover: {e}")
                self.logger.warning("Notifications will be disabled")
        else:
            if not PUSHOVER_AVAILABLE:
                self.logger.warning(
                    "Pushover not available - notifications disabled"
                )

        # Service health state
        self.service_health: Dict[str, Dict[str, Any]] = {}
        self.health_lock = threading.Lock()

        # Control flags
        self.running = False
        self.shutdown_event = threading.Event()

        # Subscribe to heartbeat topics
        self._subscribe_to_heartbeats()

        self.start_time = datetime.utcnow()
        self.logger.info("Watcher service initialized")

    def _subscribe_to_heartbeats(self):
        """Subscribe to heartbeat topics for services with Redis heartbeats."""
        service_topics = {}

        for service in self.config.services:
            if service.heartbeat_topic:
                service_topics[service.name] = service.heartbeat_topic

        if service_topics:
            self.logger.info(
                f"Subscribing to heartbeats for: {', '.join(service_topics.keys())}"
            )
            self.heartbeat_manager.subscribe_to_heartbeats(service_topics)
        else:
            self.logger.info("No services configured with Redis heartbeats")

    def check_all_services(self):
        """Run health checks on all configured services."""
        for service in self.config.services:
            try:
                health_data = self._check_service(service)

                with self.health_lock:
                    self.service_health[service.name] = health_data

                # Check alert rules
                if service.critical or health_data["overall_status"] != HealthStatus.HEALTHY:
                    alert = self.alert_manager.check_rules(
                        service.name, health_data
                    )
                    if alert:
                        self.alert_manager.process_alert(alert)
                    else:
                        # No alert - clear any existing ones
                        self.alert_manager.clear_alert(
                            service.name, health_data.get("alert_level")
                        )

            except Exception as e:
                self.logger.error(
                    f"Error checking service {service.name}: {e}",
                    exc_info=True,
                )

    def _check_service(self, service) -> Dict[str, Any]:
        """Check health of a single service.

        Args:
            service: ServiceConfig instance

        Returns:
            Combined health data
        """
        health_data = {
            "service": service.name,
            "timestamp": datetime.utcnow().isoformat(),
            "checks": {},
        }

        # Docker/HTTP checks via ServiceMonitor
        if service.type in [ServiceType.DOCKER, ServiceType.HTTP, ServiceType.HYBRID]:
            monitor_result = self.service_monitor.check_service(
                service_name=service.name,
                service_type=service.type.value,
                container=service.container,
                health_endpoint=service.health_endpoint,
            )
            health_data["checks"].update(monitor_result.get("checks", {}))
            health_data["overall_status"] = monitor_result.get("overall_status")

        # Redis heartbeat check
        if service.heartbeat_topic:
            heartbeat_status = self.heartbeat_manager.get_heartbeat_status(
                service.name
            )
            health_data["checks"]["heartbeat"] = heartbeat_status

            # Combine with overall status (worst case)
            if service.type == ServiceType.HYBRID:
                # Already have status from docker/http
                statuses = [
                    health_data.get("overall_status"),
                    heartbeat_status["status"],
                ]
                if HealthStatus.UNHEALTHY in statuses:
                    health_data["overall_status"] = HealthStatus.UNHEALTHY
                elif HealthStatus.DEGRADED in statuses:
                    health_data["overall_status"] = HealthStatus.DEGRADED
            else:
                # Redis-only service
                health_data["overall_status"] = heartbeat_status["status"]

            # Add heartbeat-specific fields for alert rules
            health_data["missed_heartbeats"] = heartbeat_status.get(
                "missed_heartbeats", 0
            )
            health_data["seconds_since_heartbeat"] = heartbeat_status.get(
                "seconds_since_heartbeat", 0
            )

        return health_data

    def get_service_health(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get health data for a specific service.

        Args:
            service_name: Name of service

        Returns:
            Health data dict or None if not found
        """
        with self.health_lock:
            return self.service_health.get(service_name)

    def get_all_service_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health data for all services.

        Returns:
            Dict of {service_name: health_data}
        """
        with self.health_lock:
            return dict(self.service_health)

    def get_status_summary(self) -> Dict[str, Any]:
        """Get overall watcher status summary.

        Returns:
            Status summary dict
        """
        with self.health_lock:
            services = dict(self.service_health)

        # Count by status
        healthy = sum(
            1
            for s in services.values()
            if s.get("overall_status") == HealthStatus.HEALTHY
        )
        degraded = sum(
            1
            for s in services.values()
            if s.get("overall_status") == HealthStatus.DEGRADED
        )
        unhealthy = sum(
            1
            for s in services.values()
            if s.get("overall_status") == HealthStatus.UNHEALTHY
        )
        unknown = sum(
            1
            for s in services.values()
            if s.get("overall_status") == HealthStatus.UNKNOWN
        )

        uptime_seconds = (datetime.utcnow() - self.start_time).total_seconds()

        return {
            "watcher_status": "running" if self.running else "stopped",
            "uptime_seconds": round(uptime_seconds, 1),
            "services_monitored": len(services),
            "services_healthy": healthy,
            "services_degraded": degraded,
            "services_unhealthy": unhealthy,
            "services_unknown": unknown,
            "active_alerts": len(self.alert_manager.get_active_alerts()),
        }

    def run(self):
        """Run the main watcher loop."""
        self.running = True
        self.logger.info("=" * 70)
        self.logger.info("Watcher Service Started")
        self.logger.info("=" * 70)

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start heartbeat listener in background thread
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_listener_thread, daemon=True
        )
        heartbeat_thread.start()

        try:
            while not self.shutdown_event.is_set():
                # Run health checks
                self.check_all_services()

                # Log summary
                summary = self.get_status_summary()
                self.logger.info(
                    f"Status: {summary['services_healthy']}/{summary['services_monitored']} healthy | "
                    f"{summary['services_degraded']} degraded | "
                    f"{summary['services_unhealthy']} unhealthy | "
                    f"{summary['active_alerts']} active alerts"
                )

                # Periodic cleanup
                if int(time.time()) % 3600 == 0:  # Every hour
                    self.heartbeat_manager.cleanup_stale_heartbeats()
                    self.alert_manager.cleanup_old_history()

                # Wait for next check interval
                self.shutdown_event.wait(self.config.check_interval_seconds)

        except Exception as e:
            self.logger.error(f"Error in watcher loop: {e}", exc_info=True)
        finally:
            self.stop()

    def _heartbeat_listener_thread(self):
        """Background thread for listening to heartbeat messages."""
        try:
            self.logger.info("Starting heartbeat listener thread")
            # This is a blocking call - runs until shutdown
            self.redis_broker.listen()
        except Exception as e:
            self.logger.error(f"Error in heartbeat listener: {e}", exc_info=True)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals.

        Args:
            signum: Signal number
            frame: Stack frame
        """
        self.logger.info(f"Received signal {signum} - shutting down")
        self.shutdown_event.set()

    def stop(self):
        """Stop the watcher service."""
        if not self.running:
            return

        self.logger.info("Stopping watcher service...")
        self.running = False
        self.shutdown_event.set()

        # Cleanup
        try:
            self.service_monitor.close()
            self.heartbeat_manager.stop()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}", exc_info=True)

        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        self.logger.info(f"Watcher service stopped (uptime: {uptime:.0f}s)")


def main():
    """Main entry point."""
    watcher = WatcherService()
    watcher.run()


if __name__ == "__main__":
    main()
