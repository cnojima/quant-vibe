"""
Progress tracking for optimization runs.

Handles real-time progress updates, ETA calculation, and Redis pub/sub notifications.
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import redis.asyncio as aioredis

from quant_vibe.logging import get_logger
from quant_vibe.utils import now_utc


logger = get_logger(__name__)


class OptimizationProgressTracker:
    """Tracks and reports optimization progress."""

    def __init__(self, redis_client: aioredis.Redis):
        """Initialize progress tracker.

        Args:
            redis_client: Async Redis client for pub/sub
        """
        self.redis = redis_client
        self._progress_cache = {}  # In-memory cache for progress data
        self._start_times = {}  # Track start times for ETA calculation

    async def initialize_progress(
        self,
        optimization_id: str,
        total_combinations: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize progress tracking for an optimization.

        Args:
            optimization_id: Optimization ID
            total_combinations: Total number of combinations
            metadata: Additional metadata to store
        """
        self._start_times[optimization_id] = now_utc()

        progress_data = {
            "optimization_id": optimization_id,
            "progress_current": 0,
            "progress_total": total_combinations,
            "progress_pct": 0.0,
            "started_at": self._start_times[optimization_id].isoformat(),
            "estimated_completion_time": None,
            "current_params": None,
            "current_metrics": None,
            "status": "running",
            **(metadata or {})
        }

        # Store in cache
        self._progress_cache[optimization_id] = progress_data

        # Store in Redis
        await self.redis.hset(
            f"optimization:progress:{optimization_id}",
            mapping={k: json.dumps(v) if not isinstance(v, str) else v
                    for k, v in progress_data.items()}
        )

        # Set expiration (24 hours)
        await self.redis.expire(f"optimization:progress:{optimization_id}", 86400)

        # Publish initial progress
        await self._publish_progress(optimization_id, progress_data)

        logger.info(
            f"[Progress] Initialized tracking for {optimization_id}: "
            f"{total_combinations} combinations"
        )

    async def update_progress(
        self,
        optimization_id: str,
        current: int,
        total: int,
        current_params: Optional[Dict[str, Any]] = None,
        current_metrics: Optional[Dict[str, float]] = None,
    ) -> None:
        """Update optimization progress.

        Args:
            optimization_id: Optimization ID
            current: Current combination number
            total: Total combinations
            current_params: Current parameter values
            current_metrics: Current metrics
        """
        # Calculate progress percentage
        progress_pct = (current / total * 100) if total > 0 else 0

        # Calculate ETA
        eta = self._calculate_eta(optimization_id, current, total)

        # Build progress update
        progress_data = {
            "optimization_id": optimization_id,
            "progress_current": current,
            "progress_total": total,
            "progress_pct": round(progress_pct, 2),
            "estimated_completion_time": eta.isoformat() if eta else None,
            "current_params": current_params,
            "current_metrics": current_metrics,
            "status": "running",
        }

        # Update cache
        if optimization_id in self._progress_cache:
            self._progress_cache[optimization_id].update(progress_data)
        else:
            self._progress_cache[optimization_id] = progress_data

        # Update Redis
        await self.redis.hset(
            f"optimization:progress:{optimization_id}",
            mapping={
                "progress_current": current,
                "progress_total": total,
                "progress_pct": round(progress_pct, 2),
                "estimated_completion_time": eta.isoformat() if eta else "",
                "current_params": json.dumps(current_params) if current_params else "{}",
                "current_metrics": json.dumps(current_metrics) if current_metrics else "{}",
            }
        )

        # Publish progress update (throttled)
        if current % max(1, total // 100) == 0 or current == total:  # Every 1% or last
            await self._publish_progress(optimization_id, progress_data)

        # Log significant milestones
        if current % max(1, total // 10) == 0 or current == total:  # Every 10%
            logger.info(
                f"[Progress] {optimization_id}: {current}/{total} "
                f"({progress_pct:.1f}%) - ETA: {eta.strftime('%H:%M:%S') if eta else 'N/A'}"
            )

    async def complete_progress(
        self,
        optimization_id: str,
        status: str = "completed",
        error_message: Optional[str] = None,
    ) -> None:
        """Mark optimization progress as complete.

        Args:
            optimization_id: Optimization ID
            status: Final status (completed, failed, cancelled)
            error_message: Error message if failed
        """
        completed_at = now_utc()

        # Get current progress
        progress_data = self._progress_cache.get(optimization_id, {})

        # Update with completion
        progress_data.update({
            "status": status,
            "completed_at": completed_at.isoformat(),
            "error_message": error_message,
        })

        # Update Redis
        await self.redis.hset(
            f"optimization:progress:{optimization_id}",
            mapping={
                "status": status,
                "completed_at": completed_at.isoformat(),
                "error_message": error_message or "",
            }
        )

        # Publish final update
        await self._publish_progress(optimization_id, progress_data)

        # Clean up cache
        self._progress_cache.pop(optimization_id, None)
        self._start_times.pop(optimization_id, None)

        logger.info(
            f"[Progress] Completed {optimization_id}: status={status}"
        )

    async def get_progress(self, optimization_id: str) -> Optional[Dict[str, Any]]:
        """Get current progress for an optimization.

        Args:
            optimization_id: Optimization ID

        Returns:
            Progress data or None if not found
        """
        # Check cache first
        if optimization_id in self._progress_cache:
            return self._progress_cache[optimization_id]

        # Check Redis
        progress_data = await self.redis.hgetall(
            f"optimization:progress:{optimization_id}"
        )

        if not progress_data:
            return None

        # Parse JSON fields
        result = {}
        for key, value in progress_data.items():
            if key in ["current_params", "current_metrics"] and value and value != "{}":
                try:
                    result[key] = json.loads(value)
                except json.JSONDecodeError:
                    result[key] = {}
            elif key in ["progress_current", "progress_total"]:
                result[key] = int(value) if value else 0
            elif key == "progress_pct":
                result[key] = float(value) if value else 0.0
            else:
                result[key] = value

        return result

    async def cancel_progress(self, optimization_id: str) -> bool:
        """Cancel progress tracking for an optimization.

        Args:
            optimization_id: Optimization ID

        Returns:
            True if cancelled, False if not found
        """
        # Check if exists
        if optimization_id not in self._progress_cache:
            progress = await self.get_progress(optimization_id)
            if not progress:
                return False

        # Mark as cancelled
        await self.complete_progress(optimization_id, status="cancelled")

        # Publish cancellation
        await self.redis.publish(
            f"optimization:cancel:{optimization_id}",
            json.dumps({"optimization_id": optimization_id})
        )

        return True

    def _calculate_eta(
        self,
        optimization_id: str,
        current: int,
        total: int,
    ) -> Optional[datetime]:
        """Calculate estimated time of completion.

        Args:
            optimization_id: Optimization ID
            current: Current combination number
            total: Total combinations

        Returns:
            Estimated completion time or None
        """
        if current == 0 or optimization_id not in self._start_times:
            return None

        start_time = self._start_times[optimization_id]
        elapsed = now_utc() - start_time

        # Calculate average time per combination
        avg_time_per_combo = elapsed / current

        # Calculate remaining time
        remaining_combos = total - current
        remaining_time = avg_time_per_combo * remaining_combos

        # Calculate ETA
        eta = now_utc() + remaining_time

        return eta

    async def _publish_progress(
        self,
        optimization_id: str,
        progress_data: Dict[str, Any],
    ) -> None:
        """Publish progress update via Redis pub/sub.

        Args:
            optimization_id: Optimization ID
            progress_data: Progress data to publish
        """
        try:
            # Publish to optimization-specific channel
            channel = f"optimization:progress:{optimization_id}"
            message = json.dumps(progress_data, default=str)
            await self.redis.publish(channel, message)

            # Also publish to general progress channel
            await self.redis.publish("optimization:progress", message)

        except Exception as e:
            logger.error(f"[Progress] Error publishing update: {e}")

    async def get_active_optimizations(self) -> List[str]:
        """Get list of currently active optimization IDs.

        Returns:
            List of optimization IDs
        """
        active_ids = []

        # Scan for progress keys
        pattern = "optimization:progress:*"
        async for key in self.redis.scan_iter(match=pattern):
            # Extract optimization ID from key
            optimization_id = key.split(":")[-1]

            # Check if still running
            progress = await self.get_progress(optimization_id)
            if progress and progress.get("status") == "running":
                active_ids.append(optimization_id)

        return active_ids

    async def cleanup_stale_progress(self, hours: int = 24) -> int:
        """Clean up stale progress records.

        Args:
            hours: Hours after which to consider progress stale

        Returns:
            Number of records cleaned
        """
        cleaned = 0
        cutoff = now_utc() - timedelta(hours=hours)

        # Scan for progress keys
        pattern = "optimization:progress:*"
        async for key in self.redis.scan_iter(match=pattern):
            progress = await self.redis.hgetall(key)

            # Check if stale
            if progress.get("completed_at"):
                completed_at = datetime.fromisoformat(progress["completed_at"])
                if completed_at < cutoff:
                    await self.redis.delete(key)
                    cleaned += 1

        logger.info(f"[Progress] Cleaned {cleaned} stale progress records")
        return cleaned