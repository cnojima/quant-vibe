"""
Status monitoring API endpoints.

Provides system health checks and service connectivity status.
"""

from fastapi import APIRouter, Depends

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.db.timescale import test_connection as test_db_connection
from admin_ui.backend.docker_manager.manager import get_docker_manager
from admin_ui.backend.redis_client import test_connection as test_redis_connection

router = APIRouter()


@router.get("/health")
async def get_health():
    """
    Overall system health check.

    Returns:
        System health status
    """
    # Test all connections
    db_ok = await test_db_connection()
    redis_ok = await test_redis_connection()
    docker_manager = get_docker_manager()
    docker_ok = docker_manager.test_connection()

    healthy = db_ok and redis_ok and docker_ok

    return {
        "healthy": healthy,
        "components": {
            "database": "ok" if db_ok else "error",
            "redis": "ok" if redis_ok else "error",
            "docker": "ok" if docker_ok else "error",
        },
    }


@router.get("/redis")
async def get_redis_status(current_user: User = Depends(get_current_user)):
    """
    Check Redis connectivity.

    Args:
        current_user: Authenticated user

    Returns:
        Redis connection status
    """
    is_connected = await test_redis_connection()

    return {
        "connected": is_connected,
        "status": "ok" if is_connected else "error",
    }


@router.get("/database")
async def get_database_status(current_user: User = Depends(get_current_user)):
    """
    Check TimescaleDB connectivity.

    Args:
        current_user: Authenticated user

    Returns:
        Database connection status
    """
    is_connected = await test_db_connection()

    return {
        "connected": is_connected,
        "status": "ok" if is_connected else "error",
    }


@router.get("/docker")
async def get_docker_status(current_user: User = Depends(get_current_user)):
    """
    Check Docker daemon connectivity.

    Args:
        current_user: Authenticated user

    Returns:
        Docker connection status
    """
    manager = get_docker_manager()
    is_connected = manager.test_connection()

    return {
        "connected": is_connected,
        "status": "ok" if is_connected else "error",
    }


@router.get("/heartbeats")
async def get_heartbeats(current_user: User = Depends(get_current_user)):
    """
    Get last heartbeat from each service.

    This would query system.heartbeat messages from Redis or database.

    Args:
        current_user: Authenticated user

    Returns:
        Last heartbeat timestamps for each service
    """
    # TODO: Implement actual heartbeat tracking
    # For now, return service status from Docker
    manager = get_docker_manager()
    services = manager.list_services()

    heartbeats = {}
    for service in services:
        heartbeats[service["name"]] = {
            "status": service["status"],
            "last_seen": service.get("started_at"),
        }

    return {
        "heartbeats": heartbeats,
    }
