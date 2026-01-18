"""Configuration for watcher service."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

import yaml


class ServiceType(Enum):
    """Type of service monitoring."""

    DOCKER = "docker"
    HTTP = "http"
    REDIS = "redis"
    HYBRID = "hybrid"


class AlertLevel(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class ServiceConfig:
    """Configuration for a single service."""

    name: str
    type: ServiceType
    critical: bool = True
    container: Optional[str] = None
    health_endpoint: Optional[str] = None
    heartbeat_topic: Optional[str] = None
    custom_checks: List[str] = field(default_factory=list)


@dataclass
class NotificationRule:
    """Alert notification rule."""

    level: AlertLevel
    services: List[str]
    condition: str
    message: str


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
    heartbeat_timeout_seconds: int = 90
    critical_timeout_seconds: int = 150
    services: List[ServiceConfig] = field(default_factory=list)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)

    @classmethod
    def from_yaml(cls, config_path: Optional[Path] = None) -> "WatcherConfig":
        """Load configuration from YAML file."""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "watcher.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path) as f:
            data = yaml.safe_load(f)

        watcher_data = data.get("watcher", {})

        services = [
            ServiceConfig(
                name=svc["name"],
                type=ServiceType(svc["type"]),
                critical=svc.get("critical", True),
                container=svc.get("container"),
                health_endpoint=svc.get("health_endpoint"),
                heartbeat_topic=svc.get("heartbeat_topic"),
                custom_checks=svc.get("custom_checks", []),
            )
            for svc in watcher_data.get("services", [])
        ]

        notif_data = watcher_data.get("notifications", {})
        rules = [
            NotificationRule(
                level=AlertLevel(rule["level"]),
                services=rule["services"],
                condition=rule["condition"],
                message=rule["message"],
            )
            for rule in notif_data.get("rules", [])
        ]

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
        """Get service config by name."""
        for service in self.services:
            if service.name == name:
                return service
        return None

    def get_critical_services(self) -> List[ServiceConfig]:
        """Get list of critical services."""
        return [svc for svc in self.services if svc.critical]