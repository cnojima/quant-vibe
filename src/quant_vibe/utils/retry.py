"""Retry utilities with exponential backoff for API calls.

Provides decorators and context managers for retrying operations
that may fail due to transient errors (network issues, rate limits, etc.).
"""

import functools
import time
from typing import Callable, Optional, Tuple, Type, TypeVar, Union

from quant_vibe.logging import get_logger

logger = get_logger(__name__)

T = TypeVar('T')


class RetryConfig:
    """Configuration for retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (default: 5)
        backoff_base: Base for exponential backoff in seconds (default: 2.0)
        max_backoff: Maximum backoff time in seconds (default: 60.0)
        exceptions: Tuple of exception types to retry on (default: Exception)
        on_retry: Optional callback called on each retry (receives attempt number, exception)
    """

    def __init__(
        self,
        max_retries: int = 5,
        backoff_base: float = 2.0,
        max_backoff: float = 60.0,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
        on_retry: Optional[Callable[[int, Exception], None]] = None,
    ):
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.max_backoff = max_backoff
        self.exceptions = exceptions
        self.on_retry = on_retry

    def calculate_backoff(self, attempt: int) -> float:
        """Calculate backoff time for given attempt.

        Uses exponential backoff: backoff_base ^ attempt
        Capped at max_backoff.

        Args:
            attempt: Retry attempt number (0-indexed)

        Returns:
            Backoff time in seconds
        """
        backoff = self.backoff_base ** attempt
        return min(backoff, self.max_backoff)


def retry_with_backoff(
    max_retries: int = 5,
    backoff_base: float = 2.0,
    max_backoff: float = 60.0,
    exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    on_retry: Optional[Callable[[int, Exception], None]] = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator to retry a function with exponential backoff.

    Usage:
        @retry_with_backoff(max_retries=3, backoff_base=2.0)
        def fetch_data():
            response = requests.get("https://api.example.com/data")
            response.raise_for_status()
            return response.json()

    Args:
        max_retries: Maximum number of retry attempts
        backoff_base: Base for exponential backoff (seconds)
        max_backoff: Maximum backoff time (seconds)
        exceptions: Exception type(s) to retry on
        on_retry: Optional callback called on each retry

    Returns:
        Decorated function with retry logic
    """
    # Normalize exceptions to tuple
    if not isinstance(exceptions, tuple):
        exceptions = (exceptions,)

    config = RetryConfig(
        max_retries=max_retries,
        backoff_base=backoff_base,
        max_backoff=max_backoff,
        exceptions=exceptions,
        on_retry=on_retry,
    )

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(config.max_retries):
                try:
                    return func(*args, **kwargs)

                except config.exceptions as e:
                    last_exception = e

                    # Don't retry on last attempt
                    if attempt == config.max_retries - 1:
                        break

                    # Calculate backoff
                    backoff = config.calculate_backoff(attempt)

                    # Log retry
                    logger.warning(
                        f"Retry {attempt + 1}/{config.max_retries} for {func.__name__}: "
                        f"{type(e).__name__}: {e}. Retrying in {backoff:.1f}s..."
                    )

                    # Call retry callback if provided
                    if config.on_retry:
                        try:
                            config.on_retry(attempt + 1, e)
                        except Exception as callback_error:
                            logger.error(f"Error in retry callback: {callback_error}")

                    # Sleep before retry
                    time.sleep(backoff)

            # All retries exhausted
            logger.error(
                f"Failed after {config.max_retries} retries for {func.__name__}: "
                f"{type(last_exception).__name__}: {last_exception}"
            )
            raise last_exception

        return wrapper

    return decorator


class RetryContext:
    """Context manager for retry logic.

    Usage:
        with RetryContext(max_retries=3) as retry:
            for attempt in retry:
                try:
                    result = some_operation()
                    break  # Success - exit retry loop
                except SomeError as e:
                    if not retry.should_retry(e):
                        raise
                    # Continue to next retry
    """

    def __init__(
        self,
        max_retries: int = 5,
        backoff_base: float = 2.0,
        max_backoff: float = 60.0,
        exceptions: Union[Type[Exception], Tuple[Type[Exception], ...]] = Exception,
    ):
        """Initialize retry context.

        Args:
            max_retries: Maximum number of retry attempts
            backoff_base: Base for exponential backoff (seconds)
            max_backoff: Maximum backoff time (seconds)
            exceptions: Exception type(s) to retry on
        """
        if not isinstance(exceptions, tuple):
            exceptions = (exceptions,)

        self.config = RetryConfig(
            max_retries=max_retries,
            backoff_base=backoff_base,
            max_backoff=max_backoff,
            exceptions=exceptions,
        )
        self.attempt = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def __iter__(self):
        """Iterate through retry attempts."""
        for attempt in range(self.config.max_retries):
            self.attempt = attempt
            yield attempt

    def should_retry(self, exception: Exception) -> bool:
        """Check if exception should trigger a retry.

        Args:
            exception: Exception that occurred

        Returns:
            True if should retry, False otherwise
        """
        # Check if exception type matches
        if not isinstance(exception, self.config.exceptions):
            return False

        # Don't retry on last attempt
        if self.attempt >= self.config.max_retries - 1:
            return False

        # Calculate and apply backoff
        backoff = self.config.calculate_backoff(self.attempt)
        logger.warning(
            f"Retry {self.attempt + 1}/{self.config.max_retries}: "
            f"{type(exception).__name__}: {exception}. Retrying in {backoff:.1f}s..."
        )
        time.sleep(backoff)

        return True
