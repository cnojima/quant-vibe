"""
Health checking for optimization service and dependencies.
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis
from sqlalchemy import create_engine, text
import psutil

from quant_vibe.logging import get_logger
from quant_vibe.utils import now_utc


logger = get_logger(__name__)


class HealthStatus(Enum):
    """Health status levels."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthCheck:
    """Base health check class."""

    def __init__(self, name: str, critical: bool = True, timeout: float = 5.0):
        """Initialize health check.

        Args:
            name: Health check name
            critical: Whether this check is critical for service health
            timeout: Timeout for health check in seconds
        """
        self.name = name
        self.critical = critical
        self.timeout = timeout

    async def check(self) -> Dict[str, Any]:
        """Perform health check.

        Returns:
            Health check result dictionary
        """
        start_time = now_utc()

        try:
            # Run check with timeout
            result = await asyncio.wait_for(
                self._perform_check(),
                timeout=self.timeout
            )

            elapsed = (now_utc() - start_time).total_seconds()

            return {
                "name": self.name,
                "status": result.get("status", HealthStatus.HEALTHY),
                "critical": self.critical,
                "elapsed_ms": round(elapsed * 1000, 2),
                **result
            }

        except asyncio.TimeoutError:
            return {
                "name": self.name,
                "status": HealthStatus.UNHEALTHY,
                "critical": self.critical,
                "error": f"Health check timed out after {self.timeout} seconds"
            }

        except Exception as e:
            logger.error(f"[HealthCheck-{self.name}] Check failed: {e}")
            return {
                "name": self.name,
                "status": HealthStatus.UNHEALTHY,
                "critical": self.critical,
                "error": str(e)
            }

    async def _perform_check(self) -> Dict[str, Any]:
        """Perform the actual health check.

        Returns:
            Health check result

        Note:
            Override in subclasses
        """
        raise NotImplementedError


class RedisHealthCheck(HealthCheck):
    """Health check for Redis connectivity."""

    def __init__(self, redis_client: aioredis.Redis):
        """Initialize Redis health check.

        Args:
            redis_client: Redis client
        """
        super().__init__("redis", critical=True)
        self.redis_client = redis_client

    async def _perform_check(self) -> Dict[str, Any]:
        """Check Redis health."""
        # Ping Redis
        await self.redis_client.ping()

        # Get Redis info
        info = await self.redis_client.info()

        # Check memory usage
        used_memory_mb = info.get("used_memory", 0) / 1024 / 1024
        max_memory_mb = info.get("maxmemory", 0) / 1024 / 1024

        memory_usage_pct = 0
        if max_memory_mb > 0:
            memory_usage_pct = (used_memory_mb / max_memory_mb) * 100

        # Determine status
        if memory_usage_pct > 90:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        return {
            "status": status,
            "redis_version": info.get("redis_version"),
            "connected_clients": info.get("connected_clients"),
            "used_memory_mb": round(used_memory_mb, 2),
            "max_memory_mb": round(max_memory_mb, 2),
            "memory_usage_pct": round(memory_usage_pct, 2),
        }


class DatabaseHealthCheck(HealthCheck):
    """Health check for database connectivity."""

    def __init__(self, db_connection_string: str):
        """Initialize database health check.

        Args:
            db_connection_string: Database connection string
        """
        super().__init__("database", critical=True)
        self.db_connection_string = db_connection_string

    async def _perform_check(self) -> Dict[str, Any]:
        """Check database health."""
        engine = create_engine(self.db_connection_string)

        # Run simple query
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.scalar()

            # Get database size
            size_result = conn.execute(
                text("SELECT pg_database_size(current_database()) as size")
            )
            db_size_bytes = size_result.scalar()
            db_size_mb = db_size_bytes / 1024 / 1024

            # Get connection count
            conn_result = conn.execute(
                text("SELECT count(*) FROM pg_stat_activity")
            )
            connection_count = conn_result.scalar()

        return {
            "status": HealthStatus.HEALTHY,
            "database_size_mb": round(db_size_mb, 2),
            "connection_count": connection_count,
        }


class SystemHealthCheck(HealthCheck):
    """Health check for system resources."""

    def __init__(self, memory_threshold: float = 90.0, cpu_threshold: float = 80.0):
        """Initialize system health check.

        Args:
            memory_threshold: Memory usage threshold for degraded status
            cpu_threshold: CPU usage threshold for degraded status
        """
        super().__init__("system", critical=False)
        self.memory_threshold = memory_threshold
        self.cpu_threshold = cpu_threshold

    async def _perform_check(self) -> Dict[str, Any]:
        """Check system health."""
        # Get memory usage
        memory = psutil.virtual_memory()
        memory_usage_pct = memory.percent

        # Get CPU usage
        cpu_usage_pct = psutil.cpu_percent(interval=0.1)

        # Get disk usage for current directory
        disk = psutil.disk_usage("/")
        disk_usage_pct = disk.percent

        # Determine status
        if memory_usage_pct > self.memory_threshold or cpu_usage_pct > self.cpu_threshold:
            status = HealthStatus.DEGRADED
        elif memory_usage_pct > 95 or cpu_usage_pct > 95:
            status = HealthStatus.UNHEALTHY
        else:
            status = HealthStatus.HEALTHY

        return {
            "status": status,
            "memory_usage_pct": round(memory_usage_pct, 2),
            "memory_available_mb": round(memory.available / 1024 / 1024, 2),
            "cpu_usage_pct": round(cpu_usage_pct, 2),
            "cpu_count": psutil.cpu_count(),
            "disk_usage_pct": round(disk_usage_pct, 2),
            "disk_free_gb": round(disk.free / 1024 / 1024 / 1024, 2),
        }


class OptimizationHealthCheck(HealthCheck):
    """Health check for optimization-specific metrics."""

    def __init__(self, executor, repository):
        """Initialize optimization health check.

        Args:
            executor: Optimization executor
            repository: Optimization repository
        """
        super().__init__("optimization", critical=False)
        self.executor = executor
        self.repository = repository

    async def _perform_check(self) -> Dict[str, Any]:
        """Check optimization service health."""
        # Get active optimizations
        active_optimizations = self.executor.get_active_optimizations()

        # Get recent optimizations from database
        recent_optimizations = self.repository.get_all_optimizations(
            status_filter="running",
            limit=10
        )

        # Check for stuck optimizations (running > 2 hours)
        stuck_optimizations = []
        cutoff = now_utc() - timedelta(hours=2)

        for opt in recent_optimizations:
            if opt.get("started_at"):
                started_at = datetime.fromisoformat(opt["started_at"])
                if started_at < cutoff:
                    stuck_optimizations.append(opt["optimization_id"])

        # Determine status
        if stuck_optimizations:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        return {
            "status": status,
            "active_optimizations": len(active_optimizations),
            "stuck_optimizations": len(stuck_optimizations),
            "stuck_optimization_ids": stuck_optimizations[:5],  # Limit to 5
        }


class HealthCheckManager:
    """Manages multiple health checks."""

    def __init__(self):
        """Initialize health check manager."""
        self.checks: List[HealthCheck] = []
        self.last_check_time: Optional[datetime] = None
        self.last_results: Dict[str, Any] = {}

    def add_check(self, check: HealthCheck) -> None:
        """Add a health check.

        Args:
            check: Health check to add
        """
        self.checks.append(check)

    async def check_all(self) -> Dict[str, Any]:
        """Run all health checks.

        Returns:
            Overall health status
        """
        results = await asyncio.gather(
            *[check.check() for check in self.checks],
            return_exceptions=True
        )

        # Process results
        all_results = []
        critical_healthy = True
        any_unhealthy = False

        for result in results:
            if isinstance(result, Exception):
                # Check failed
                all_results.append({
                    "name": "unknown",
                    "status": HealthStatus.UNHEALTHY,
                    "critical": True,
                    "error": str(result)
                })
                critical_healthy = False
                any_unhealthy = True
            else:
                all_results.append(result)

                # Check status
                status = result.get("status", HealthStatus.UNHEALTHY)
                if status == HealthStatus.UNHEALTHY:
                    any_unhealthy = True
                    if result.get("critical", True):
                        critical_healthy = False

        # Determine overall status
        if not critical_healthy:
            overall_status = HealthStatus.UNHEALTHY
        elif any_unhealthy:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        # Build response
        self.last_check_time = now_utc()
        self.last_results = {
            "status": overall_status.value,
            "timestamp": self.last_check_time.isoformat(),
            "checks": all_results
        }

        return self.last_results

    async def check_readiness(self) -> bool:
        """Check if service is ready to accept requests.

        Returns:
            True if ready
        """
        results = await self.check_all()
        return results["status"] != HealthStatus.UNHEALTHY.value

    async def check_liveness(self) -> bool:
        """Check if service is alive.

        Returns:
            True if alive
        """
        # For liveness, we just check if we can respond
        return True

    def get_cached_results(self) -> Dict[str, Any]:
        """Get cached health check results.

        Returns:
            Last health check results
        """
        if not self.last_results:
            return {
                "status": HealthStatus.UNHEALTHY.value,
                "message": "No health checks performed yet"
            }

        # Check if results are stale (> 60 seconds)
        if self.last_check_time:
            age = (now_utc() - self.last_check_time).total_seconds()
            if age > 60:
                return {
                    "status": HealthStatus.DEGRADED.value,
                    "message": f"Health check results are stale ({age:.0f} seconds old)",
                    **self.last_results
                }

        return self.last_results