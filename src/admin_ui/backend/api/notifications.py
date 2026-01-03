"""
Notification history API endpoints.

Provides endpoints to fetch and filter notification history from the database.
"""

import os
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from admin_ui.backend.auth import User, get_current_user
from quant_vibe.utils import now_utc

# Import database store
try:
    from quant_vibe.data.timescale_store import TimescaleStore
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

router = APIRouter()


class NotificationRecord(BaseModel):
    """Single notification record."""
    notification_id: int
    title: Optional[str]
    message: str
    notification_type: str
    priority: int
    sound: Optional[str]
    device: Optional[str]
    sent_successfully: bool
    error_message: Optional[str]
    metadata: Optional[dict]
    url: Optional[str]
    url_title: Optional[str]
    sent_at: datetime


class NotificationStats(BaseModel):
    """Notification statistics."""
    notification_type: str
    total_count: int
    success_count: int
    failure_count: int
    success_rate: float


class NotificationHistoryResponse(BaseModel):
    """Response for notification history."""
    notifications: List[NotificationRecord]
    total: int
    page: int
    per_page: int


class NotificationStatsResponse(BaseModel):
    """Response for notification statistics."""
    stats: List[NotificationStats]
    period_start: datetime
    period_end: datetime


@router.get("/history", response_model=NotificationHistoryResponse)
async def get_notification_history(
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=500, description="Items per page"),
    notification_type: Optional[str] = Query(None, description="Filter by notification type"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    sent_successfully: Optional[bool] = Query(None, description="Filter by success status"),
    current_user: User = Depends(get_current_user),
):
    """
    Get notification history with pagination and filters.

    Args:
        page: Page number (1-indexed)
        per_page: Number of items per page
        notification_type: Filter by notification type
        start_date: Filter notifications after this date
        end_date: Filter notifications before this date
        sent_successfully: Filter by success status
        current_user: Authenticated user

    Returns:
        NotificationHistoryResponse with notifications and pagination info
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        ts_store = TimescaleStore()

        # Build query
        query = """
            SELECT
                notification_id,
                title,
                message,
                notification_type,
                priority,
                sound,
                device,
                sent_successfully,
                error_message,
                metadata,
                url,
                url_title,
                sent_at
            FROM notifications
            WHERE 1=1
        """
        params = []

        # Apply filters
        if notification_type:
            query += " AND notification_type = %s"
            params.append(notification_type)

        if start_date:
            query += " AND sent_at >= %s"
            params.append(start_date)

        if end_date:
            query += " AND sent_at <= %s"
            params.append(end_date)

        if sent_successfully is not None:
            query += " AND sent_successfully = %s"
            params.append(sent_successfully)

        # Count total results
        count_query = f"SELECT COUNT(*) FROM ({query}) AS filtered"

        with ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(count_query, params)
                total = cur.fetchone()[0]

        # Add ordering and pagination
        query += " ORDER BY sent_at DESC"
        query += f" LIMIT {per_page} OFFSET {(page - 1) * per_page}"

        # Fetch results
        notifications = []
        with ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                columns = [desc[0] for desc in cur.description]

                for row in cur.fetchall():
                    record = dict(zip(columns, row))
                    notifications.append(NotificationRecord(**record))

        return NotificationHistoryResponse(
            notifications=notifications,
            total=total,
            page=page,
            per_page=per_page,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch notification history: {str(e)}")


@router.get("/stats", response_model=NotificationStatsResponse)
async def get_notification_stats(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
):
    """
    Get notification statistics grouped by type.

    Args:
        days: Number of days to analyze (default: 30)
        current_user: Authenticated user

    Returns:
        NotificationStatsResponse with statistics by type
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        ts_store = TimescaleStore()
        period_start = now_utc() - timedelta(days=days)
        period_end = now_utc()

        query = """
            SELECT
                notification_type,
                COUNT(*) AS total_count,
                SUM(CASE WHEN sent_successfully THEN 1 ELSE 0 END) AS success_count,
                SUM(CASE WHEN NOT sent_successfully THEN 1 ELSE 0 END) AS failure_count,
                ROUND(
                    (SUM(CASE WHEN sent_successfully THEN 1 ELSE 0 END)::NUMERIC / COUNT(*)::NUMERIC) * 100,
                    2
                ) AS success_rate
            FROM notifications
            WHERE sent_at BETWEEN %s AND %s
            GROUP BY notification_type
            ORDER BY total_count DESC
        """

        stats = []
        with ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, (period_start, period_end))
                columns = [desc[0] for desc in cur.description]

                for row in cur.fetchall():
                    record = dict(zip(columns, row))
                    stats.append(NotificationStats(**record))

        return NotificationStatsResponse(
            stats=stats,
            period_start=period_start,
            period_end=period_end,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch notification stats: {str(e)}")


@router.get("/types")
async def get_notification_types(
    current_user: User = Depends(get_current_user),
):
    """
    Get list of unique notification types.

    Args:
        current_user: Authenticated user

    Returns:
        List of unique notification types
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        ts_store = TimescaleStore()

        query = """
            SELECT DISTINCT notification_type
            FROM notifications
            ORDER BY notification_type
        """

        types = []
        with ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                types = [row[0] for row in cur.fetchall()]

        return {"types": types}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch notification types: {str(e)}")


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: User = Depends(get_current_user),
):
    """
    Delete a specific notification.

    Args:
        notification_id: ID of notification to delete
        current_user: Authenticated user

    Returns:
        Success message
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        ts_store = TimescaleStore()

        with ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM notifications WHERE notification_id = %s",
                    (notification_id,)
                )
                conn.commit()

                if cur.rowcount == 0:
                    raise HTTPException(status_code=404, detail="Notification not found")

        return {"message": "Notification deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete notification: {str(e)}")


@router.post("/cleanup")
async def cleanup_old_notifications(
    days: int = Query(90, ge=1, le=365, description="Delete notifications older than this many days"),
    current_user: User = Depends(get_current_user),
):
    """
    Clean up old notifications.

    Args:
        days: Delete notifications older than this many days
        current_user: Authenticated user

    Returns:
        Number of notifications deleted
    """
    if not DB_AVAILABLE:
        raise HTTPException(status_code=503, detail="Database not available")

    try:
        ts_store = TimescaleStore()

        with ts_store.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT cleanup_old_notifications(%s)",
                    (days,)
                )
                deleted_count = cur.fetchone()[0]
                conn.commit()

        return {"deleted": deleted_count, "message": f"Deleted {deleted_count} notifications older than {days} days"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup notifications: {str(e)}")
