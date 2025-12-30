"""
Watcher service health monitoring API endpoints.

Provides endpoints to view service health status from the watcher service.
"""

from fastapi import APIRouter, Depends

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.redis_client import get_redis

router = APIRouter()


@router.get("/services")
async def get_watcher_services(current_user: User = Depends(get_current_user)):
    """
    Get service health status from watcher service.

    The watcher service publishes health status to Redis topics.
    This endpoint retrieves the latest health information.

    Args:
        current_user: Authenticated user

    Returns:
        Service health statuses
    """
    try:
        redis = await get_redis()
        if not redis:
            return {
                "success": False,
                "message": "Redis not available",
                "services": [],
            }

        # Get all heartbeat keys from Redis
        # Watcher publishes to heartbeat.{service_name}
        # We'll also check for watcher_health.{service_name} keys

        services = []

        # List of expected services
        service_names = [
            "token_service",
            "streaming",
            "live_trading",
            "admin_ui",
            "redis",
            "timescaledb",
        ]

        for service_name in service_names:
            # Try to get latest heartbeat
            heartbeat_key = f"heartbeat.{service_name}"
            heartbeat_data = await redis.get(heartbeat_key)

            if heartbeat_data:
                import json
                heartbeat = json.loads(heartbeat_data)

                services.append({
                    "name": service_name,
                    "status": heartbeat.get("status", "unknown"),
                    "last_heartbeat": heartbeat.get("timestamp"),
                    "metrics": heartbeat.get("metrics", {}),
                })
            else:
                # No heartbeat found - service might be down or not reporting
                services.append({
                    "name": service_name,
                    "status": "unknown",
                    "last_heartbeat": None,
                    "metrics": {},
                })

        return {
            "success": True,
            "services": services,
            "count": len(services),
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to get watcher status: {str(e)}",
            "services": [],
        }


@router.get("/alerts")
async def get_watcher_alerts(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """
    Get recent alerts from watcher service.

    Args:
        limit: Maximum number of alerts to return
        current_user: Authenticated user

    Returns:
        Recent alerts
    """
    try:
        redis = await get_redis()
        if not redis:
            return {
                "success": False,
                "message": "Redis not available",
                "alerts": [],
            }

        # Get alerts from Redis list
        # Watcher pushes alerts to watcher_alerts list
        alerts_data = await redis.lrange("watcher_alerts", 0, limit - 1)

        alerts = []
        for alert_data in alerts_data:
            import json
            alert = json.loads(alert_data)
            alerts.append(alert)

        return {
            "success": True,
            "alerts": alerts,
            "count": len(alerts),
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to get alerts: {str(e)}",
            "alerts": [],
        }


@router.get("/summary")
async def get_watcher_summary(current_user: User = Depends(get_current_user)):
    """
    Get overall watcher service summary.

    Args:
        current_user: Authenticated user

    Returns:
        Summary statistics
    """
    try:
        redis = await get_redis()
        if not redis:
            return {
                "success": False,
                "message": "Redis not available",
            }

        # Get summary from Redis
        summary_key = "watcher_summary"
        summary_data = await redis.get(summary_key)

        if summary_data:
            import json
            summary = json.loads(summary_data)
            return {
                "success": True,
                "summary": summary,
            }
        else:
            return {
                "success": False,
                "message": "Watcher summary not available. Watcher service may not be running.",
            }

    except Exception as e:
        return {
            "success": False,
            "message": f"Failed to get watcher summary: {str(e)}",
        }
