"""
Retry policies for handling transient failures.
"""

import asyncio
import random
from enum import Enum
from typing import Any, Callable, List, Optional, Type

from quant_vibe.logging import get_logger


logger = get_logger(__name__)


class RetryStrategy(Enum):
    """Retry strategy types."""
    FIXED = "fixed"              # Fixed delay between retries
    EXPONENTIAL = "exponential"  # Exponential backoff
    LINEAR = "linear"            # Linear increase in delay
    JITTERED = "jittered"       # Exponential with jitter


class RetryPolicy:
    """Retry policy for handling transient failures."""

    def __init__(
        self,
        max_retries: int = 3,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Optional[List[Type[Exception]]] = None,
    ):
        """Initialize retry policy.

        Args:
            max_retries: Maximum number of retry attempts
            strategy: Retry strategy to use
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            exponential_base: Base for exponential backoff
            jitter: Add randomization to delays
            retryable_exceptions: List of exceptions to retry (None = all)
        """
        self.max_retries = max_retries
        self.strategy = strategy
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions or []

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry policy.

        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Last exception if all retries failed
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                # Execute function
                result = await func(*args, **kwargs)

                if attempt > 0:
                    logger.info(
                        f"[RetryPolicy] Succeeded on attempt {attempt + 1}/{self.max_retries + 1}"
                    )

                return result

            except Exception as e:
                last_exception = e

                # Check if we should retry
                if not self._should_retry(e, attempt):
                    logger.error(
                        f"[RetryPolicy] Non-retryable exception or max retries reached: {e}"
                    )
                    raise

                # Calculate delay
                delay = self._calculate_delay(attempt)

                logger.warning(
                    f"[RetryPolicy] Attempt {attempt + 1}/{self.max_retries + 1} failed: {e}. "
                    f"Retrying in {delay:.2f} seconds..."
                )

                # Wait before retry
                await asyncio.sleep(delay)

        # All retries failed
        logger.error(
            f"[RetryPolicy] All {self.max_retries + 1} attempts failed"
        )
        raise last_exception

    def _should_retry(self, exception: Exception, attempt: int) -> bool:
        """Check if we should retry after an exception.

        Args:
            exception: The exception that occurred
            attempt: Current attempt number (0-indexed)

        Returns:
            True if we should retry
        """
        # Check if we have retries left
        if attempt >= self.max_retries:
            return False

        # If no specific exceptions specified, retry all
        if not self.retryable_exceptions:
            return True

        # Check if exception is retryable
        return any(
            isinstance(exception, exc_type)
            for exc_type in self.retryable_exceptions
        )

    def _calculate_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt.

        Args:
            attempt: Attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        if self.strategy == RetryStrategy.FIXED:
            delay = self.initial_delay

        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.initial_delay * (attempt + 1)

        elif self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.initial_delay * (self.exponential_base ** attempt)

        elif self.strategy == RetryStrategy.JITTERED:
            # Exponential with jitter
            delay = self.initial_delay * (self.exponential_base ** attempt)
            if self.jitter:
                # Add random jitter (±25%)
                jitter_range = delay * 0.25
                delay += random.uniform(-jitter_range, jitter_range)

        else:
            delay = self.initial_delay

        # Apply max delay cap
        delay = min(delay, self.max_delay)

        # Ensure positive delay
        return max(0.1, delay)


class RetryWithFallback:
    """Retry policy with fallback behavior."""

    def __init__(
        self,
        retry_policy: RetryPolicy,
        fallback_func: Optional[Callable] = None,
        fallback_value: Any = None,
    ):
        """Initialize retry with fallback.

        Args:
            retry_policy: Retry policy to use
            fallback_func: Async function to call on failure
            fallback_value: Value to return on failure
        """
        self.retry_policy = retry_policy
        self.fallback_func = fallback_func
        self.fallback_value = fallback_value

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function with retry and fallback.

        Args:
            func: Async function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result or fallback value
        """
        try:
            # Try with retry policy
            return await self.retry_policy.execute(func, *args, **kwargs)

        except Exception as e:
            logger.warning(f"[RetryWithFallback] All retries failed, using fallback: {e}")

            # Try fallback function
            if self.fallback_func:
                try:
                    return await self.fallback_func(*args, **kwargs)
                except Exception as fallback_error:
                    logger.error(f"[RetryWithFallback] Fallback also failed: {fallback_error}")

            # Return fallback value
            if self.fallback_value is not None:
                return self.fallback_value

            # No fallback available, re-raise
            raise


# Pre-configured retry policies

def get_default_retry_policy() -> RetryPolicy:
    """Get default retry policy with exponential backoff.

    Returns:
        RetryPolicy with 3 retries and exponential backoff
    """
    return RetryPolicy(
        max_retries=3,
        strategy=RetryStrategy.EXPONENTIAL,
        initial_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
    )


def get_aggressive_retry_policy() -> RetryPolicy:
    """Get aggressive retry policy for critical operations.

    Returns:
        RetryPolicy with 5 retries and jittered exponential backoff
    """
    return RetryPolicy(
        max_retries=5,
        strategy=RetryStrategy.JITTERED,
        initial_delay=0.5,
        max_delay=60.0,
        exponential_base=2.0,
        jitter=True,
    )


def get_quick_retry_policy() -> RetryPolicy:
    """Get quick retry policy for fast operations.

    Returns:
        RetryPolicy with 2 retries and fixed delay
    """
    return RetryPolicy(
        max_retries=2,
        strategy=RetryStrategy.FIXED,
        initial_delay=0.5,
        max_delay=1.0,
    )


def get_database_retry_policy() -> RetryPolicy:
    """Get retry policy optimized for database operations.

    Returns:
        RetryPolicy for database transient errors
    """
    from sqlalchemy.exc import OperationalError, TimeoutError

    return RetryPolicy(
        max_retries=3,
        strategy=RetryStrategy.EXPONENTIAL,
        initial_delay=2.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=[OperationalError, TimeoutError, ConnectionError],
    )


def get_network_retry_policy() -> RetryPolicy:
    """Get retry policy optimized for network operations.

    Returns:
        RetryPolicy for network transient errors
    """
    import httpx

    return RetryPolicy(
        max_retries=4,
        strategy=RetryStrategy.JITTERED,
        initial_delay=1.0,
        max_delay=60.0,
        exponential_base=2.0,
        jitter=True,
        retryable_exceptions=[
            httpx.TimeoutException,
            httpx.NetworkError,
            httpx.ConnectError,
            ConnectionError,
            TimeoutError,
        ],
    )