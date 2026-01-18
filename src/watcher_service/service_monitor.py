"""Service monitoring with Docker, HTTP, and Redis health checks."""

import time
from enum import Enum
from typing import Any, Dict, Optional

import docker
import requests
from docker.errors import DockerException, NotFound
from quant_vibe.utils import now_utc


class HealthStatus(Enum):
    """Health status of a service."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ServiceMonitor:
    """Monitors service health using multiple check methods."""

    def __init__(self, logger):
        """Initialize service monitor."""
        self.logger = logger
        self.docker_client: Optional[docker.DockerClient] = None

        try:
            self.docker_client = docker.from_env()
            self.logger.info("Docker client initialized")
        except DockerException as e:
            self.logger.warning(f"Failed to initialize Docker client: {e}")
            self.logger.warning("Docker health checks will be disabled")

    def check_docker_health(self, container_name: str) -> Dict[str, Any]:
        """Check Docker container health."""
        if not self.docker_client:
            return {
                "status": HealthStatus.UNKNOWN,
                "details": "Docker client not available",
                "timestamp": now_utc().isoformat(),
            }

        try:
            container = self.docker_client.containers.get(container_name)
            container.reload()
            state = container.attrs["State"]

            if not state.get("Running", False):
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "details": f"Container not running (status: {state.get('Status')})",
                    "timestamp": now_utc().isoformat(),
                    "restart_count": state.get("RestartCount", 0),
                }

            health = state.get("Health", {})
            health_status = health.get("Status", "none")

            status_map = {
                "healthy": HealthStatus.HEALTHY,
                "unhealthy": HealthStatus.UNHEALTHY,
                "starting": HealthStatus.DEGRADED,
            }

            status = status_map.get(health_status, HealthStatus.HEALTHY)

            if health_status == "unhealthy":
                details = f"Container health check failed: {health.get('FailingStreak', 0)} failures"
            elif health_status == "starting":
                details = "Container starting (health check in progress)"
            elif health_status == "healthy":
                details = "Container running and healthy"
            else:
                details = "Container running (no healthcheck defined)"

            return {
                "status": status,
                "details": details,
                "timestamp": now_utc().isoformat(),
                "restart_count": state.get("RestartCount", 0),
            }

        except NotFound:
            return {
                "status": HealthStatus.UNHEALTHY,
                "details": f"Container '{container_name}' not found",
                "timestamp": now_utc().isoformat(),
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNKNOWN,
                "details": f"Error checking container: {str(e)}",
                "timestamp": now_utc().isoformat(),
            }

    def check_http_health(self, endpoint: str, timeout: int = 5) -> Dict[str, Any]:
        """Check HTTP health endpoint."""
        start_time = time.time()

        try:
            response = requests.get(endpoint, timeout=timeout)
            response_time = time.time() - start_time

            if response.status_code == 200:
                try:
                    data = response.json()
                    status_str = data.get("status", "healthy")

                    status_map = {
                        "healthy": HealthStatus.HEALTHY,
                        "ok": HealthStatus.HEALTHY,
                        "degraded": HealthStatus.DEGRADED,
                    }

                    health_status = status_map.get(status_str, HealthStatus.UNHEALTHY)

                    return {
                        "status": health_status,
                        "details": data.get("message", "Service responding"),
                        "response_time_ms": round(response_time * 1000, 2),
                        "timestamp": now_utc().isoformat(),
                        "data": data,
                    }
                except ValueError:
                    return {
                        "status": HealthStatus.HEALTHY,
                        "details": "Service responding (non-JSON response)",
                        "response_time_ms": round(response_time * 1000, 2),
                        "timestamp": now_utc().isoformat(),
                    }
            else:
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "details": f"HTTP {response.status_code}: {response.text[:100]}",
                    "response_time_ms": round(response_time * 1000, 2),
                    "timestamp": now_utc().isoformat(),
                }

        except requests.exceptions.Timeout:
            return {
                "status": HealthStatus.UNHEALTHY,
                "details": f"Request timeout after {timeout}s",
                "timestamp": now_utc().isoformat(),
            }
        except requests.exceptions.ConnectionError as e:
            return {
                "status": HealthStatus.UNHEALTHY,
                "details": f"Connection error: {str(e)[:100]}",
                "timestamp": now_utc().isoformat(),
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNKNOWN,
                "details": f"Error checking endpoint: {str(e)[:100]}",
                "timestamp": now_utc().isoformat(),
            }

    def check_service(
        self,
        service_name: str,
        service_type: str,
        container: Optional[str] = None,
        health_endpoint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check service health using appropriate method(s)."""
        results = {"service": service_name, "checks": {}}

        if service_type == "docker" and container:
            results["checks"]["docker"] = self.check_docker_health(container)
            results["overall_status"] = results["checks"]["docker"]["status"]

        elif service_type == "http" and health_endpoint:
            results["checks"]["http"] = self.check_http_health(health_endpoint)
            results["overall_status"] = results["checks"]["http"]["status"]

        elif service_type == "hybrid":
            if container:
                results["checks"]["docker"] = self.check_docker_health(container)

            if health_endpoint:
                results["checks"]["http"] = self.check_http_health(health_endpoint)

            statuses = [check["status"] for check in results["checks"].values()]

            if HealthStatus.UNHEALTHY in statuses:
                results["overall_status"] = HealthStatus.UNHEALTHY
            elif HealthStatus.DEGRADED in statuses:
                results["overall_status"] = HealthStatus.DEGRADED
            elif HealthStatus.HEALTHY in statuses:
                results["overall_status"] = HealthStatus.HEALTHY
            else:
                results["overall_status"] = HealthStatus.UNKNOWN

        else:
            results["overall_status"] = HealthStatus.UNKNOWN
            results["error"] = "Invalid service type or missing configuration"

        results["timestamp"] = now_utc().isoformat()
        return results

    def close(self) -> None:
        """Clean up resources."""
        if self.docker_client:
            try:
                self.docker_client.close()
            except Exception as e:
                self.logger.warning(f"Error closing Docker client: {e}")