"""Service monitoring with Docker, HTTP, and Redis health checks."""

import time
from datetime import datetime
from typing import Dict, Optional, Any
from enum import Enum

import requests
import docker
from docker.errors import DockerException, NotFound


class HealthStatus(Enum):
    """Health status of a service."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class ServiceMonitor:
    """Monitors service health using multiple check methods."""

    def __init__(self, logger):
        """Initialize service monitor.

        Args:
            logger: Logger instance
        """
        self.logger = logger
        self.docker_client: Optional[docker.DockerClient] = None

        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            self.logger.info("Docker client initialized")
        except DockerException as e:
            self.logger.warning(f"Failed to initialize Docker client: {e}")
            self.logger.warning("Docker health checks will be disabled")

    def check_docker_health(self, container_name: str) -> Dict[str, Any]:
        """Check Docker container health.

        Args:
            container_name: Name of container to check

        Returns:
            Dict with status, details, and timestamp
        """
        if not self.docker_client:
            return {
                "status": HealthStatus.UNKNOWN,
                "details": "Docker client not available",
                "timestamp": datetime.utcnow().isoformat(),
            }

        try:
            container = self.docker_client.containers.get(container_name)

            # Get container state
            container.reload()
            state = container.attrs["State"]

            # Check if running
            if not state.get("Running", False):
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "details": f"Container not running (status: {state.get('Status')})",
                    "timestamp": datetime.utcnow().isoformat(),
                    "restart_count": state.get("RestartCount", 0),
                }

            # Check Docker health status (if healthcheck defined)
            health = state.get("Health", {})
            health_status = health.get("Status", "none")

            if health_status == "healthy":
                return {
                    "status": HealthStatus.HEALTHY,
                    "details": "Container running and healthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "restart_count": state.get("RestartCount", 0),
                }
            elif health_status == "unhealthy":
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "details": f"Container health check failed: {health.get('FailingStreak', 0)} failures",
                    "timestamp": datetime.utcnow().isoformat(),
                    "restart_count": state.get("RestartCount", 0),
                }
            elif health_status == "starting":
                return {
                    "status": HealthStatus.DEGRADED,
                    "details": "Container starting (health check in progress)",
                    "timestamp": datetime.utcnow().isoformat(),
                    "restart_count": state.get("RestartCount", 0),
                }
            else:
                # No healthcheck defined, assume healthy if running
                return {
                    "status": HealthStatus.HEALTHY,
                    "details": "Container running (no healthcheck defined)",
                    "timestamp": datetime.utcnow().isoformat(),
                    "restart_count": state.get("RestartCount", 0),
                }

        except NotFound:
            return {
                "status": HealthStatus.UNHEALTHY,
                "details": f"Container '{container_name}' not found",
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNKNOWN,
                "details": f"Error checking container: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            }

    def check_http_health(
        self, endpoint: str, timeout: int = 5
    ) -> Dict[str, Any]:
        """Check HTTP health endpoint.

        Args:
            endpoint: HTTP endpoint URL (e.g., http://service:8000/health)
            timeout: Request timeout in seconds

        Returns:
            Dict with status, details, response_time, and timestamp
        """
        start_time = time.time()

        try:
            response = requests.get(endpoint, timeout=timeout)
            response_time = time.time() - start_time

            if response.status_code == 200:
                # Try to parse JSON response
                try:
                    data = response.json()
                    status_str = data.get("status", "healthy")

                    if status_str in ["healthy", "ok"]:
                        health_status = HealthStatus.HEALTHY
                    elif status_str == "degraded":
                        health_status = HealthStatus.DEGRADED
                    else:
                        health_status = HealthStatus.UNHEALTHY

                    return {
                        "status": health_status,
                        "details": data.get("message", "Service responding"),
                        "response_time_ms": round(response_time * 1000, 2),
                        "timestamp": datetime.utcnow().isoformat(),
                        "data": data,
                    }
                except ValueError:
                    # Not JSON, but 200 OK is healthy
                    return {
                        "status": HealthStatus.HEALTHY,
                        "details": "Service responding (non-JSON response)",
                        "response_time_ms": round(response_time * 1000, 2),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
            else:
                return {
                    "status": HealthStatus.UNHEALTHY,
                    "details": f"HTTP {response.status_code}: {response.text[:100]}",
                    "response_time_ms": round(response_time * 1000, 2),
                    "timestamp": datetime.utcnow().isoformat(),
                }

        except requests.exceptions.Timeout:
            return {
                "status": HealthStatus.UNHEALTHY,
                "details": f"Request timeout after {timeout}s",
                "timestamp": datetime.utcnow().isoformat(),
            }
        except requests.exceptions.ConnectionError as e:
            return {
                "status": HealthStatus.UNHEALTHY,
                "details": f"Connection error: {str(e)[:100]}",
                "timestamp": datetime.utcnow().isoformat(),
            }
        except Exception as e:
            return {
                "status": HealthStatus.UNKNOWN,
                "details": f"Error checking endpoint: {str(e)[:100]}",
                "timestamp": datetime.utcnow().isoformat(),
            }

    def check_service(
        self,
        service_name: str,
        service_type: str,
        container: Optional[str] = None,
        health_endpoint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check service health using appropriate method(s).

        Args:
            service_name: Name of service
            service_type: Type of check (docker, http, hybrid)
            container: Docker container name (if applicable)
            health_endpoint: HTTP endpoint (if applicable)

        Returns:
            Combined health check result
        """
        results = {"service": service_name, "checks": {}}

        if service_type == "docker" and container:
            results["checks"]["docker"] = self.check_docker_health(container)
            results["overall_status"] = results["checks"]["docker"]["status"]

        elif service_type == "http" and health_endpoint:
            results["checks"]["http"] = self.check_http_health(health_endpoint)
            results["overall_status"] = results["checks"]["http"]["status"]

        elif service_type == "hybrid":
            # Run all available checks
            if container:
                results["checks"]["docker"] = self.check_docker_health(container)

            if health_endpoint:
                results["checks"]["http"] = self.check_http_health(health_endpoint)

            # Determine overall status (worst case)
            statuses = [
                check["status"] for check in results["checks"].values()
            ]
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

        results["timestamp"] = datetime.utcnow().isoformat()
        return results

    def close(self):
        """Clean up resources."""
        if self.docker_client:
            try:
                self.docker_client.close()
            except Exception as e:
                self.logger.warning(f"Error closing Docker client: {e}")
