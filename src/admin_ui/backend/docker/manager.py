"""
Docker API manager for service lifecycle control.

Provides methods to start, stop, and monitor Docker containers
for quant-vibe services.
"""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Any, Optional

import docker
from docker.errors import DockerException, NotFound
from docker.models.containers import Container

from admin_ui.backend.config import get_settings


class ServiceStatus(str, Enum):
    """Service status enum."""

    RUNNING = "running"
    STOPPED = "stopped"
    STARTING = "starting"
    STOPPING = "stopping"
    ERROR = "error"
    NOT_FOUND = "not_found"


class DockerManager:
    """Docker API manager for controlling services."""

    def __init__(self):
        """Initialize Docker client."""
        settings = get_settings()

        try:
            if settings.docker_host:
                self.client = docker.DockerClient(base_url=settings.docker_host)
            else:
                self.client = docker.from_env()
        except DockerException as e:
            raise RuntimeError(f"Failed to initialize Docker client: {e}") from e

    def _get_container(self, service_name: str) -> Optional[Container]:
        """
        Get a container by service name.

        Args:
            service_name: Name of the service/container

        Returns:
            Container object or None if not found
        """
        # Try multiple naming patterns
        # Also try replacing underscores with hyphens in service name
        service_name_hyphen = service_name.replace("_", "-")

        naming_patterns = [
            service_name,                              # exact name
            f"quant-vibe-{service_name}",             # hyphen prefix
            f"quant-vibe-{service_name_hyphen}",      # hyphen prefix + hyphenated name
            f"quant-vibe_{service_name}",             # underscore prefix
            f"quant-vibe_{service_name}_1",           # compose v1 with replica
            f"quant-vibe-{service_name}-1",           # hyphen with replica
            f"quant-vibe-{service_name_hyphen}-1",    # hyphen with replica (hyphenated)
        ]

        for container_name in naming_patterns:
            try:
                return self.client.containers.get(container_name)
            except NotFound:
                continue

        return None

    def get_service_status(self, service_name: str) -> dict[str, Any]:
        """
        Get the status of a service.

        Args:
            service_name: Name of the service

        Returns:
            Dict with service status information
        """
        container = self._get_container(service_name)

        if not container:
            return {
                "name": service_name,
                "status": ServiceStatus.NOT_FOUND.value,
                "message": "Container not found",
                "uptime_seconds": 0,
            }

        try:
            container.reload()  # Refresh container state
            status = container.status

            # Map Docker status to our enum
            if status == "running":
                service_status = ServiceStatus.RUNNING
            elif status in ("created", "restarting"):
                service_status = ServiceStatus.STARTING
            elif status in ("paused", "exited", "dead", "removing"):
                service_status = ServiceStatus.STOPPED
            else:
                service_status = ServiceStatus.ERROR

            # Calculate uptime for running containers
            uptime_seconds = 0
            started_at_str = container.attrs.get("State", {}).get("StartedAt")
            if status == "running" and started_at_str:
                try:
                    # Parse Docker timestamp (ISO 8601 format)
                    # Remove nanoseconds and parse
                    started_at_str = started_at_str.split(".")[0] + "Z"
                    started_at = datetime.fromisoformat(started_at_str.replace("Z", "+00:00"))
                    uptime_seconds = int((datetime.now(started_at.tzinfo) - started_at).total_seconds())
                except (ValueError, AttributeError):
                    uptime_seconds = 0

            return {
                "name": service_name,
                "status": service_status.value,  # Use .value to get string
                "container_status": status,
                "container_id": container.short_id,
                "image": container.image.tags[0] if container.image.tags else "unknown",
                "created": container.attrs.get("Created"),
                "started_at": started_at_str,
                "uptime_seconds": uptime_seconds,
                "ports": container.attrs.get("NetworkSettings", {}).get("Ports", {}),
            }
        except Exception as e:
            return {
                "name": service_name,
                "status": ServiceStatus.ERROR.value,
                "message": str(e),
                "uptime_seconds": 0,
            }

    def list_services(self) -> list[dict[str, Any]]:
        """
        List all quant-vibe services.

        Returns:
            List of service status dictionaries
        """
        # Known quant-vibe services
        services = [
            "streaming",
            "live_trading",
            "timescaledb",
            "redis",
            "admin_ui",
            "watcher",
            "token-service",
            "dyndns",
        ]

        return [self.get_service_status(service) for service in services]

    async def start_service(self, service_name: str) -> dict[str, Any]:
        """
        Start a service.

        Args:
            service_name: Name of the service to start

        Returns:
            Dict with operation result
        """
        container = self._get_container(service_name)

        if not container:
            return {
                "success": False,
                "message": f"Container '{service_name}' not found",
            }

        try:
            if container.status == "running":
                return {
                    "success": True,
                    "message": f"Service '{service_name}' is already running",
                }

            # Start container in a thread pool (blocking operation)
            await asyncio.to_thread(container.start)

            return {
                "success": True,
                "message": f"Service '{service_name}' started successfully",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to start service '{service_name}': {str(e)}",
            }

    async def stop_service(self, service_name: str, timeout: int = 10) -> dict[str, Any]:
        """
        Stop a service.

        Args:
            service_name: Name of the service to stop
            timeout: Timeout in seconds before forcefully killing

        Returns:
            Dict with operation result
        """
        container = self._get_container(service_name)

        if not container:
            return {
                "success": False,
                "message": f"Container '{service_name}' not found",
            }

        try:
            if container.status != "running":
                return {
                    "success": True,
                    "message": f"Service '{service_name}' is not running",
                }

            # Stop container in a thread pool (blocking operation)
            await asyncio.to_thread(container.stop, timeout=timeout)

            return {
                "success": True,
                "message": f"Service '{service_name}' stopped successfully",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to stop service '{service_name}': {str(e)}",
            }

    async def restart_service(self, service_name: str, timeout: int = 10) -> dict[str, Any]:
        """
        Restart a service.

        Args:
            service_name: Name of the service to restart
            timeout: Timeout in seconds before forcefully killing

        Returns:
            Dict with operation result
        """
        container = self._get_container(service_name)

        if not container:
            return {
                "success": False,
                "message": f"Container '{service_name}' not found",
            }

        try:
            # Restart container in a thread pool (blocking operation)
            await asyncio.to_thread(container.restart, timeout=timeout)

            return {
                "success": True,
                "message": f"Service '{service_name}' restarted successfully",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to restart service '{service_name}': {str(e)}",
            }

    def get_logs(
        self,
        service_name: str,
        tail: int = 100,
        since: Optional[datetime] = None,
    ) -> dict[str, Any]:
        """
        Get logs from a service.

        Args:
            service_name: Name of the service
            tail: Number of lines from the end of the logs
            since: Only return logs since this timestamp

        Returns:
            Dict with logs
        """
        container = self._get_container(service_name)

        if not container:
            return {
                "success": False,
                "message": f"Container '{service_name}' not found",
                "logs": "",
            }

        try:
            logs = container.logs(
                tail=tail,
                since=since,
                timestamps=True,
            ).decode("utf-8")

            return {
                "success": True,
                "logs": logs,
                "lines": len(logs.splitlines()),
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to get logs: {str(e)}",
                "logs": "",
            }

    def test_connection(self) -> bool:
        """
        Test Docker daemon connectivity.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client.ping()
            return True
        except Exception:
            return False


# Singleton instance
_manager: Optional[DockerManager] = None


def get_docker_manager() -> DockerManager:
    """Get or create Docker manager singleton."""
    global _manager
    if _manager is None:
        _manager = DockerManager()
    return _manager
