"""Main watcher service orchestrator."""

import os
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from quant_vibe.logging import setup_normalized_logging
from quant_vibe.messaging import RedisMessageBroker
from quant_vibe.utils import now_utc
from watcher_service.alert_manager import AlertManager
from watcher_service.config import ServiceType, WatcherConfig
from watcher_service.heartbeat_manager import HeartbeatManager
from watcher_service.service_monitor import HealthStatus, ServiceMonitor

try:
    from quant_vibe.notifications import PushoverNotifier

    PUSHOVER_AVAILABLE = True
except ImportError:
    PUSHOVER_AVAILABLE = False
    PushoverNotifier = None


class WatcherService:
    """Main watcher service for monitoring system health."""

    def __init__(self, config: Optional[WatcherConfig] = None):
        """Initialize watcher service."""
        load_dotenv()

        self.config = config or WatcherConfig.from_yaml()

        log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.logger = setup_normalized_logging(
            app_name="watcher",
            log_dir="logs/watcher",
        )

        self.logger.info("=" * 70)
        self.logger.info("Watcher Service Initializing")
        self.logger.info("=" * 70)

        self.logger.info(f"Monitoring {len(self.config.services)} services")
        self.logger.info(f"Check interval: {self.config.check_interval_seconds}s")
        self.logger.info(f"Heartbeat timeout: {self.config.heartbeat_timeout_seconds}s")

        self.service_monitor = ServiceMonitor(self.logger)
        self.redis_broker = RedisMessageBroker()
        self.heartbeat_manager = HeartbeatManager(
            self.redis_broker,
            self.logger,
            self.config.heartbeat_timeout_seconds,
        )
        self.alert_manager = AlertManager(self.config.notifications, self.logger)

        if self.config.notifications.enabled and PUSHOVER_AVAILABLE:
            try:
                self.notifier = PushoverNotifier()
                self.alert_manager.set_notifier(self.notifier)
                self.logger.info("Pushover notifications enabled")
            except Exception as e:
                self.logger.warning(f"Failed to initialize Pushover: {e}")
                self.logger.warning("Notifications will be disabled")
        elif not PUSHOVER_AVAILABLE:
            self.logger.warning("Pushover not available - notifications disabled")

        self.service_health: Dict[str, Dict[str, Any]] = {}
        self.health_lock = threading.Lock()
        self.running = False
        self.shutdown_event = threading.Event()
        self._subscribe_to_heartbeats()
        self.start_time = now_utc()
        self.logger.info("Watcher service initialized")

    def _subscribe_to_heartbeats(self) -> None:
        """Subscribe to heartbeat topics for services with Redis heartbeats."""
        service_topics = {
            service.name: service.heartbeat_topic
            for service in self.config.services
            if service.heartbeat_topic
        }

        if service_topics:
            self.logger.info(
                f"Subscribing to heartbeats for: {', '.join(service_topics.keys())}"
            )
            self.heartbeat_manager.subscribe_to_heartbeats(service_topics)
        else:
            self.logger.info("No services configured with Redis heartbeats")

    def check_all_services(self) -> None:
        """Run health checks on all configured services."""
        for service in self.config.services:
            try:
                health_data = self._check_service(service)

                with self.health_lock:
                    self.service_health[service.name] = health_data

                if service.critical or health_data["overall_status"] != HealthStatus.HEALTHY:
                    alert = self.alert_manager.check_rules(service.name, health_data)
                    if alert:
                        self.alert_manager.process_alert(alert)
                    else:
                        self.alert_manager.clear_all_alerts_for_service(service.name)
                elif health_data["overall_status"] == HealthStatus.HEALTHY:
                    self.alert_manager.clear_all_alerts_for_service(service.name)

            except Exception as e:
                self.logger.error(
                    f"Error checking service {service.name}: {e}",
                    exc_info=True,
                )

    def _check_service(self, service) -> Dict[str, Any]:
        """Check health of a single service."""
        health_data = {
            "service": service.name,
            "timestamp": now_utc().isoformat(),
            "checks": {},
        }

        if service.type in [ServiceType.DOCKER, ServiceType.HTTP, ServiceType.HYBRID]:
            monitor_result = self.service_monitor.check_service(
                service_name=service.name,
                service_type=service.type.value,
                container=service.container,
                health_endpoint=service.health_endpoint,
            )
            health_data["checks"].update(monitor_result.get("checks", {}))
            health_data["overall_status"] = monitor_result.get("overall_status")

        if service.heartbeat_topic:
            heartbeat_status = self.heartbeat_manager.get_heartbeat_status(
                service.name
            )
            health_data["checks"]["heartbeat"] = heartbeat_status

            if service.type == ServiceType.HYBRID:
                statuses = [
                    health_data.get("overall_status"),
                    heartbeat_status["status"],
                ]
                if HealthStatus.UNHEALTHY in statuses:
                    health_data["overall_status"] = HealthStatus.UNHEALTHY
                elif HealthStatus.DEGRADED in statuses:
                    health_data["overall_status"] = HealthStatus.DEGRADED
            else:
                health_data["overall_status"] = heartbeat_status["status"]

            health_data["missed_heartbeats"] = heartbeat_status.get(
                "missed_heartbeats", 0
            )
            health_data["seconds_since_heartbeat"] = heartbeat_status.get(
                "seconds_since_heartbeat", 0
            )

        return health_data

    def get_service_health(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Get health data for a specific service."""
        with self.health_lock:
            return self.service_health.get(service_name)

    def get_all_service_health(self) -> Dict[str, Dict[str, Any]]:
        """Get health data for all services."""
        with self.health_lock:
            return dict(self.service_health)

    def get_status_summary(self) -> Dict[str, Any]:
        """Get overall watcher status summary."""
        with self.health_lock:
            services = dict(self.service_health)

        status_counts = {
            HealthStatus.HEALTHY: 0,
            HealthStatus.DEGRADED: 0,
            HealthStatus.UNHEALTHY: 0,
            HealthStatus.UNKNOWN: 0,
        }

        for service in services.values():
            status = service.get("overall_status", HealthStatus.UNKNOWN)
            status_counts[status] = status_counts.get(status, 0) + 1

        uptime_seconds = (now_utc() - self.start_time).total_seconds()

        return {
            "watcher_status": "running" if self.running else "stopped",
            "uptime_seconds": round(uptime_seconds, 1),
            "services_monitored": len(services),
            "services_healthy": status_counts[HealthStatus.HEALTHY],
            "services_degraded": status_counts[HealthStatus.DEGRADED],
            "services_unhealthy": status_counts[HealthStatus.UNHEALTHY],
            "services_unknown": status_counts[HealthStatus.UNKNOWN],
            "active_alerts": len(self.alert_manager.get_active_alerts()),
        }

    def run(self) -> None:
        """Run the main watcher loop."""
        self.running = True
        self.logger.info("=" * 70)
        self.logger.info("Watcher Service Started")
        self.logger.info("=" * 70)

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        heartbeat_thread = threading.Thread(
            target=self._heartbeat_listener_thread, daemon=True
        )
        heartbeat_thread.start()

        try:
            while not self.shutdown_event.is_set():
                self.check_all_services()

                summary = self.get_status_summary()
                self.logger.info(
                    f"Status: {summary['services_healthy']}/{summary['services_monitored']} healthy | "
                    f"{summary['services_degraded']} degraded | "
                    f"{summary['services_unhealthy']} unhealthy | "
                    f"{summary['active_alerts']} active alerts"
                )

                if int(time.time()) % 3600 == 0:
                    self.heartbeat_manager.cleanup_stale_heartbeats()
                    self.alert_manager.cleanup_old_history()

                self.shutdown_event.wait(self.config.check_interval_seconds)

        except Exception as e:
            self.logger.error(f"Error in watcher loop: {e}", exc_info=True)
        finally:
            self.stop()

    def _heartbeat_listener_thread(self) -> None:
        """Background thread for listening to heartbeat messages."""
        try:
            self.logger.info("Starting heartbeat listener thread")

            while not self.shutdown_event.is_set():
                self.redis_broker.get_message(timeout=0.1)
                time.sleep(0.01)

            self.logger.info("Heartbeat listener thread shutting down")

        except Exception as e:
            self.logger.error(f"Error in heartbeat listener: {e}", exc_info=True)

    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum} - shutting down")
        self.shutdown_event.set()

    def stop(self) -> None:
        """Stop the watcher service."""
        if not self.running:
            return

        self.logger.info("Stopping watcher service...")
        self.running = False
        self.shutdown_event.set()

        try:
            self.service_monitor.close()
            self.heartbeat_manager.stop()
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}", exc_info=True)

        uptime = (now_utc() - self.start_time).total_seconds()
        self.logger.info(f"Watcher service stopped (uptime: {uptime:.0f}s)")


def main():
    """Main entry point."""
    watcher = WatcherService()
    watcher.run()


if __name__ == "__main__":
    main()