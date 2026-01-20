"""
Circuit breaker pattern for preventing cascading failures.
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional, Dict

from quant_vibe.logging import get_logger
from quant_vibe.utils import now_utc


logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"      # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: int = 60,
        half_open_requests: int = 1,
    ):
        """Initialize circuit breaker.

        Args:
            name: Circuit breaker name
            failure_threshold: Number of failures before opening
            success_threshold: Number of successes to close from half-open
            timeout: Seconds before attempting half-open from open
            half_open_requests: Number of test requests in half-open state
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.half_open_requests = half_open_requests

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_request_count = 0

        # Statistics
        self.stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "rejected_calls": 0,
            "state_transitions": []
        }

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker.

        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitOpenError: If circuit is open
            Original exception: If function fails
        """
        self.stats["total_calls"] += 1

        # Check circuit state
        if not self._can_execute():
            self.stats["rejected_calls"] += 1
            raise CircuitOpenError(
                f"Circuit '{self.name}' is {self.state.value}: "
                f"Service unavailable after {self.failure_count} failures"
            )

        try:
            # Execute function
            result = await func(*args, **kwargs)

            # Record success
            self._record_success()
            self.stats["successful_calls"] += 1

            return result

        except Exception as e:
            # Record failure
            self._record_failure()
            self.stats["failed_calls"] += 1

            logger.error(f"[CircuitBreaker-{self.name}] Call failed: {e}")
            raise

    def _can_execute(self) -> bool:
        """Check if request can be executed.

        Returns:
            True if request should be executed
        """
        if self.state == CircuitState.CLOSED:
            return True

        elif self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if self._should_attempt_reset():
                self._transition_to_half_open()
                return True
            return False

        elif self.state == CircuitState.HALF_OPEN:
            # Allow limited requests in half-open
            if self.half_open_request_count < self.half_open_requests:
                self.half_open_request_count += 1
                return True
            return False

        return False

    def _record_success(self) -> None:
        """Record successful call."""
        if self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

        elif self.state == CircuitState.HALF_OPEN:
            self.success_count += 1

            # Check if we should close circuit
            if self.success_count >= self.success_threshold:
                self._transition_to_closed()

    def _record_failure(self) -> None:
        """Record failed call."""
        self.last_failure_time = now_utc()

        if self.state == CircuitState.CLOSED:
            self.failure_count += 1

            # Check if we should open circuit
            if self.failure_count >= self.failure_threshold:
                self._transition_to_open()

        elif self.state == CircuitState.HALF_OPEN:
            # Single failure returns to open
            self._transition_to_open()

    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset from open state.

        Returns:
            True if timeout has passed
        """
        if self.last_failure_time is None:
            return True

        timeout_time = self.last_failure_time + timedelta(seconds=self.timeout)
        return now_utc() >= timeout_time

    def _transition_to_open(self) -> None:
        """Transition to open state."""
        old_state = self.state
        self.state = CircuitState.OPEN
        self.failure_count = 0
        self.success_count = 0
        self.half_open_request_count = 0

        self._log_transition(old_state, CircuitState.OPEN)

    def _transition_to_closed(self) -> None:
        """Transition to closed state."""
        old_state = self.state
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.half_open_request_count = 0

        self._log_transition(old_state, CircuitState.CLOSED)

    def _transition_to_half_open(self) -> None:
        """Transition to half-open state."""
        old_state = self.state
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        self.half_open_request_count = 0

        self._log_transition(old_state, CircuitState.HALF_OPEN)

    def _log_transition(self, old_state: CircuitState, new_state: CircuitState) -> None:
        """Log state transition.

        Args:
            old_state: Previous state
            new_state: New state
        """
        logger.info(
            f"[CircuitBreaker-{self.name}] State transition: "
            f"{old_state.value} -> {new_state.value}"
        )

        self.stats["state_transitions"].append({
            "timestamp": now_utc().isoformat(),
            "from": old_state.value,
            "to": new_state.value
        })

    def reset(self) -> None:
        """Manually reset circuit breaker to closed state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.half_open_request_count = 0

        logger.info(f"[CircuitBreaker-{self.name}] Manually reset to CLOSED")

    def get_status(self) -> Dict[str, Any]:
        """Get circuit breaker status.

        Returns:
            Status dictionary
        """
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time.isoformat()
                if self.last_failure_time else None,
            "stats": self.stats
        }


class CircuitOpenError(Exception):
    """Exception raised when circuit is open."""
    pass


class CircuitBreakerManager:
    """Manages multiple circuit breakers."""

    def __init__(self):
        """Initialize circuit breaker manager."""
        self.breakers: Dict[str, CircuitBreaker] = {}

    def get_breaker(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: int = 60,
    ) -> CircuitBreaker:
        """Get or create circuit breaker.

        Args:
            name: Circuit breaker name
            failure_threshold: Number of failures before opening
            success_threshold: Number of successes to close
            timeout: Seconds before attempting reset

        Returns:
            Circuit breaker instance
        """
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                success_threshold=success_threshold,
                timeout=timeout,
            )

        return self.breakers[name]

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self.breakers.values():
            breaker.reset()

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all circuit breakers.

        Returns:
            Dictionary of breaker statuses
        """
        return {
            name: breaker.get_status()
            for name, breaker in self.breakers.items()
        }