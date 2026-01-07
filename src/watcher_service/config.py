"""Configuration management for watcher service."""

from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field
from enum import Enum

import yaml


class ServiceType(Enum):
    """Type of service monitoring."""

    DOCKER = "docker"
    HTTP = "http"
    REDIS = "redis"
    HYBRID = "hybrid"  # Combines multiple check types


class AlertLevel(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class ServiceConfig:
    """Configuration for a single service to monitor."""

    name: str
    type: ServiceType
    critical: bool = True
    container: Optional[str] = None  # Docker container name
    health_endpoint: Optional[str] = None  # HTTP health endpoint
    heartbeat_topic: Optional[str] = None  # Redis topic for heartbeats
    custom_checks: List[str] = field(default_factory=list)


@dataclass
class NotificationRule:
    """Alert notification rule."""

    level: AlertLevel
    services: List[str]
    condition: str  # Python expression to evaluate
    message: str  # Template message with {{placeholders}}


@dataclass
class NotificationConfig:
    """Notification settings."""

    enabled: bool = True
    send_recovery_notifications: bool = True
    channels: List[str] = field(default_factory=lambda: ["pushover"])
    rules: List[NotificationRule] = field(default_factory=list)


@dataclass
class WatcherConfig:
    """Main watcher service configuration."""

    check_interval_seconds: int = 30
    heartbeat_timeout_seconds: int = 90  # 3 missed heartbeats
    critical_timeout_seconds: int = 150  # 5 missed heartbeats
    services: List[ServiceConfig] = field(default_factory=list)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)

    @classmethod
    def from_yaml(cls, config_path: Optional[Path] = None) -> "WatcherConfig":
        """Load configuration from YAML file.

        Args:
            config_path: Path to config file (defaults to config/watcher.yaml)

        Returns:
            WatcherConfig instance
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "watcher.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            data = yaml.safe_load(f)

        watcher_data = data.get("watcher", {})

        # Parse services
        services = []
        for svc_data in watcher_data.get("services", []):
            service = ServiceConfig(
                name=svc_data["name"],
                type=ServiceType(svc_data["type"]),
                critical=svc_data.get("critical", True),
                container=svc_data.get("container"),
                health_endpoint=svc_data.get("health_endpoint"),
                heartbeat_topic=svc_data.get("heartbeat_topic"),
                custom_checks=svc_data.get("custom_checks", []),
            )
            services.append(service)

        # Parse notification config
        notif_data = watcher_data.get("notifications", {})
        rules = []
        for rule_data in notif_data.get("rules", []):
            rule = NotificationRule(
                level=AlertLevel(rule_data["level"]),
                services=rule_data["services"],
                condition=rule_data["condition"],
                message=rule_data["message"],
            )
            rules.append(rule)

        notifications = NotificationConfig(
            enabled=notif_data.get("enabled", True),
            send_recovery_notifications=notif_data.get("send_recovery_notifications", True),
            channels=notif_data.get("channels", ["pushover"]),
            rules=rules,
        )

        return cls(
            check_interval_seconds=watcher_data.get("check_interval_seconds", 30),
            heartbeat_timeout_seconds=watcher_data.get("heartbeat_timeout_seconds", 90),
            critical_timeout_seconds=watcher_data.get("critical_timeout_seconds", 150),
            services=services,
            notifications=notifications,
        )

    def get_service(self, name: str) -> Optional[ServiceConfig]:
        """Get service config by name.

        Args:
            name: Service name

        Returns:
            ServiceConfig or None if not found
        """
        for service in self.services:
            if service.name == name:
                return service
        return None

    def get_critical_services(self) -> List[ServiceConfig]:
        """Get list of critical services.

        Returns:
            List of critical ServiceConfig objects
        """
        return [svc for svc in self.services if svc.critical]
