"""Unified logging configuration for all quant-vibe components.

Provides normalized logging format: [datetime][app][level][msg]
with proper stack trace handling and calendar-day (EST) rotation.
"""
import os
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
from logging.handlers import TimedRotatingFileHandler
import pytz
from dotenv import load_dotenv

load_dotenv()

# Module-level constants for performance
_EASTERN_TZ = pytz.timezone('America/New_York')
_LOG_LEVEL_CACHE = {}
_LOGGER_INSTANCES = {}

class ESTTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    TimedRotatingFileHandler that rotates at midnight EST instead of local time.

    This ensures logs rotate consistently based on US Eastern Time,
    regardless of the server's timezone.
    """

    def __init__(self, filename, when='midnight', interval=1, backupCount=0, encoding=None, delay=False, utc=False, bufsize=-1):
        """
        Initialize handler with EST timezone.

        Args:
            filename: Log file path
            when: Type of interval ('midnight' for calendar day rotation)
            interval: Interval multiplier (1 for daily)
            backupCount: Number of backup files to keep (0 = keep all)
            encoding: File encoding
            delay: Delay file opening
            utc: Ignored - always uses EST
            bufsize: Buffer size for file writes (-1 for default)
        """
        # Set EST timezone BEFORE calling parent __init__
        # (parent calls computeRollover which needs self.tz)
        self.tz = _EASTERN_TZ

        # Initialize parent with utc=True (we'll handle timezone ourselves)
        super().__init__(filename, when=when, interval=interval, backupCount=backupCount,
                         encoding=encoding, delay=delay, utc=True)

        # Override suffix to include timezone indicator
        if when.upper() == 'MIDNIGHT':
            self.suffix = "%Y-%m-%d_EST"

    def computeRollover(self, currentTime):
        """
        Compute next rollover time at midnight EST.

        Args:
            currentTime: Current time in seconds since epoch

        Returns:
            Next rollover time in seconds since epoch
        """
        from datetime import timedelta

        # Convert current time to EST
        current_est = datetime.fromtimestamp(currentTime, tz=self.tz)

        # Calculate next midnight EST
        next_midnight = current_est.replace(hour=0, minute=0, second=0, microsecond=0)
        # Add one day to get to next midnight
        next_midnight += timedelta(days=self.interval)

        # Convert back to UTC timestamp
        return next_midnight.timestamp()


class NormalizedFormatter(logging.Formatter):
    """
    Custom formatter for normalized log output.

    Format: [datetime][app][level][msg]
    Example: [2025-12-25 12:00:00][backtest][INFO] Starting backtest

    Handles multi-line messages and stack traces properly.
    """

    def __init__(self, app_name: str = "quant_vibe", include_func: bool = False):
        """
        Initialize formatter.

        Args:
            app_name: Application/component name for logs
            include_func: Whether to include function name in detailed logs
        """
        self.app_name = app_name
        self.include_func = include_func
        self.tz = _EASTERN_TZ  # Reuse cached timezone

        # Base format: [datetime][app][level][msg]
        super().__init__(
            fmt=None,  # We'll format manually in format()
            datefmt='%Y-%m-%d %H:%M:%S'
        )

    def format(self, record: logging.LogRecord) -> str:
        """
        Format log record with normalized format.

        Args:
            record: Log record to format

        Returns:
            Formatted log string
        """
        # Format timestamp in EST timezone (using cached timezone)
        timestamp = datetime.fromtimestamp(record.created, tz=self.tz).strftime(self.datefmt)

        # Format level (pad to 8 chars for alignment)
        level = f"{record.levelname:<8}"

        # Build base prefix
        if self.include_func:
            prefix = f"[{timestamp}][{self.app_name}][{level}][{record.funcName}:{record.lineno}]"
        else:
            prefix = f"[{timestamp}][{self.app_name}][{level}]"

        # Get message
        message = record.getMessage()

        # Handle multi-line messages (indent continuation lines) - only if needed
        if '\n' in message:
            lines = message.split('\n')
            formatted_lines = [f"{prefix} {lines[0]}"]
            indent = ' ' * (len(prefix) + 1)
            formatted_lines.extend(f"{indent}{line}" for line in lines[1:])
            result = '\n'.join(formatted_lines)
        else:
            result = f"{prefix} {message}"

        # Handle exceptions (stack traces)
        if record.exc_info:
            # Add stack trace with proper indentation
            exc_text = self.formatException(record.exc_info)
            indent = ' ' * (len(prefix) + 1)
            exc_lines = exc_text.split('\n')
            formatted_exc = '\n'.join(f"{indent}{line}" for line in exc_lines)
            result = f"{result}\n{formatted_exc}"

        return result

def get_log_level(app_name: str) -> str:
    """
    Get log level from environment variables with caching.

    Checks for specific app log level first, then falls back to general LOG_LEVEL.

    Args:
        app_name: Application/component name

    Returns:
        Log level string (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    if app_name not in _LOG_LEVEL_CACHE:
        specific_env_var = f"{app_name.upper()}_LOG_LEVEL"
        _LOG_LEVEL_CACHE[app_name] = os.getenv(specific_env_var, os.getenv("LOG_LEVEL", "INFO")).upper()
    return _LOG_LEVEL_CACHE[app_name]

def setup_normalized_logging(
    app_name: str = "quant_vibe",
    log_level: Optional[str] = None,
    log_dir: str = "logs",
    log_file: Optional[str] = None,
    console_output: bool = True,
    include_func: bool = False,
    capture_submodules: bool = True,
) -> logging.Logger:
    """
    Set up normalized logging for any component with singleton pattern.

    Logs are written to component-specific log file (logs/{app_name}/{app_name}_{date}.log)

    Args:
        app_name: Application/component name (backtest, live, streaming_service, etc.)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) - if None, uses env vars
        log_dir: Directory to store log files
        log_file: Specific log file name (defaults to {app_name}_{date}.log)
        console_output: Whether to output to console
        include_func: Whether to include function name/line in logs
        capture_submodules: If True, also capture logs from quant_vibe.* submodules
                           (e.g., messaging.broker, data.timescale_store) into this log file

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_normalized_logging(
        ...     app_name="backtest",
        ...     log_level="INFO",
        ...     log_dir="logs/backtests",
        ...     capture_submodules=True  # Also capture broker, timescale, etc. logs
        ... )
        >>> logger.info("Starting backtest")
        [2025-12-25 12:00:00][backtest][INFO    ] Starting backtest
    """
    # Check if logger already exists and return it (singleton pattern)
    cache_key = (app_name, log_dir, log_file, console_output, include_func, capture_submodules)
    if cache_key in _LOGGER_INSTANCES:
        return _LOGGER_INSTANCES[cache_key]

    # Create log directory
    log_dir = log_dir or f"logs/{app_name}"
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Generate log file name if not provided (use EST timezone)
    if log_file is None:
        timestamp = datetime.now(tz=_EASTERN_TZ).strftime("%Y%m%d")
        log_file = f"{app_name}_{timestamp}.log"

    full_log_path = log_path / log_file

    # Create logger
    logger = logging.getLogger(app_name)
    if log_level is None:
        log_level = get_log_level(app_name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    # Create formatters
    file_formatter = NormalizedFormatter(app_name=app_name, include_func=True)
    console_formatter = NormalizedFormatter(app_name=app_name, include_func=False)

    # Component-specific file handler with EST-based rotation and buffering
    file_handler = ESTTimedRotatingFileHandler(
        str(full_log_path),
        when='midnight',
        interval=1,
        backupCount=30,  # Keep 30 days of logs
        encoding='utf-8',
        bufsize=8192  # 8KB buffer for better I/O performance
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler - configurable level
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    # Capture logs from quant_vibe.* submodules (broker, timescale_store, etc.)
    if capture_submodules:
        quant_vibe_logger = logging.getLogger("quant_vibe")
        quant_vibe_logger.setLevel(logging.DEBUG)  # Capture all levels
        # Add the same file handler to quant_vibe parent logger (avoid duplicates)
        if file_handler not in quant_vibe_logger.handlers:
            quant_vibe_logger.addHandler(file_handler)
        # Don't add console handler to avoid duplicate console output
        # (submodules have their own console handlers)
        quant_vibe_logger.propagate = False  # Don't propagate to root

    # Prevent propagation to root logger
    logger.propagate = False

    # Cache the logger instance
    _LOGGER_INSTANCES[cache_key] = logger

    return logger


def get_logger(app_name: str = "quant_vibe") -> logging.Logger:
    """
    Get logger for utility modules (lightweight, propagates to parent).

    This function is intended for utility/library modules (e.g., messaging.broker,
    data.timescale_store) that should log through the calling service's logger.

    For service-level loggers (backtest, live_trading, etc.), use
    setup_normalized_logging() directly instead.

    Behavior:
    - Creates a logger in the Python hierarchy (e.g., "quant_vibe.messaging.broker")
    - Adds console handler for immediate feedback
    - Sets propagate=True so logs bubble up to parent loggers
    - Does NOT create file handlers (relies on parent/root logger)

    Args:
        app_name: Module name (usually __name__)

    Returns:
        Logger instance that propagates to parent

    Example:
        >>> # In utility module:
        >>> logger = get_logger(__name__)  # e.g., "quant_vibe.messaging.broker"
        >>> logger.info("Message from broker")
        >>> # Logs appear in calling service's log file
    """
    # Check if logger already exists
    logger = logging.getLogger(app_name)

    # If logger already configured (has handlers), return it
    if logger.handlers:
        return logger

    # Configure logger for utility module
    log_level = get_log_level(app_name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Add ONLY console handler (no file handler)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_formatter = NormalizedFormatter(app_name=app_name, include_func=False)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # CRITICAL: Enable propagation so logs reach parent loggers
    logger.propagate = True

    return logger
