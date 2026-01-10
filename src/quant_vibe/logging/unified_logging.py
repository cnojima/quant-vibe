"""Unified logging configuration for all quant-vibe components.

Provides normalized logging format: [datetime][app][level][msg]
with proper stack trace handling and calendar-day (EST) rotation.
"""
from math import log
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

consolidated_log = 'logs/quant_vibe.log'

class ESTTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    TimedRotatingFileHandler that rotates at midnight EST instead of local time.

    This ensures logs rotate consistently based on US Eastern Time,
    regardless of the server's timezone.
    """

    def __init__(self, filename, when='midnight', interval=1, backupCount=0, encoding=None, delay=False, utc=False):
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
        """
        # Set EST timezone BEFORE calling parent __init__
        # (parent calls computeRollover which needs self.tz)
        self.tz = pytz.timezone('America/New_York')

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
        # Format timestamp in EST timezone
        eastern = pytz.timezone('America/New_York')
        timestamp = datetime.fromtimestamp(record.created, tz=eastern).strftime(self.datefmt)

        # Format level (pad to 8 chars for alignment)
        level = f"{record.levelname:<8}"

        # Build base prefix
        if self.include_func:
            prefix = f"[{timestamp}][{self.app_name}][{level}][{record.funcName}:{record.lineno}]"
        else:
            prefix = f"[{timestamp}][{self.app_name}][{level}]"

        # Get message
        message = record.getMessage()

        # Handle multi-line messages (indent continuation lines)
        if '\n' in message:
            lines = message.split('\n')
            formatted_lines = [f"{prefix} {lines[0]}"]
            indent = ' ' * (len(prefix) + 1)
            for line in lines[1:]:
                formatted_lines.append(f"{indent}{line}")
            result = '\n'.join(formatted_lines)
        else:
            result = f"{prefix} {message}"

        # Handle exceptions (stack traces)
        if record.exc_info:
            # Add stack trace with proper indentation
            exc_text = self.formatException(record.exc_info)
            indent = ' ' * (len(prefix) + 1)
            exc_lines = exc_text.split('\n')
            formatted_exc = '\n'.join([f"{indent}{line}" for line in exc_lines])
            result = f"{result}\n{formatted_exc}"

        return result

def get_log_level(app_name: str) -> str:
    """
    Get log level from environment variables.

    Checks for specific app log level first, then falls back to general LOG_LEVEL.

    Args:
        app_name: Application/component name
    """
    specific_env_var = f"{app_name.upper()}_LOG_LEVEL"
    return os.getenv(specific_env_var, os.getenv("LOG_LEVEL", "INFO")).upper()

def setup_normalized_logging(
    app_name: str = "quant_vibe",
    log_level: Optional[str] = get_log_level("quant_vibe"),
    log_dir: str = "logs",
    log_file: Optional[str] = None,
    console_output: bool = True,
    include_func: bool = False,
) -> logging.Logger:
    """
    Set up normalized logging for any component.

    Logs are written to both:
    1. A consolidated log file (logs/quant_vibe.log) containing all components
    2. A component-specific log file (logs/{app_name}/{app_name}_{date}.log)

    Args:
        app_name: Application/component name (backtest, live, streaming_service, etc.)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory to store log files
        log_file: Specific log file name (defaults to {app_name}_{date}.log)
        console_output: Whether to output to console
        include_func: Whether to include function name/line in logs

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_normalized_logging(
        ...     app_name="backtest",
        ...     log_level="INFO",
        ...     log_dir="logs/backtests"
        ... )
        >>> logger.info("Starting backtest")
        [2025-12-25 12:00:00][backtest][INFO    ] Starting backtest
    """
    # Create log directory
    log_dir = log_dir or f"logs/{app_name}"
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Generate log file name if not provided (use EST timezone)
    if log_file is None:
        eastern = pytz.timezone('America/New_York')
        timestamp = datetime.now(tz=eastern).strftime("%Y%m%d")
        log_file = f"{app_name}_{timestamp}.log"

    full_log_path = log_path / log_file

    # Create logger
    logger = logging.getLogger(app_name)
    log_level = get_log_level(app_name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    # Create formatters
    file_formatter = NormalizedFormatter(app_name=app_name, include_func=True)
    console_formatter = NormalizedFormatter(app_name=app_name, include_func=False)

    # Consolidated log handler - all components write here
    consolidated_path = Path(consolidated_log)
    consolidated_path.parent.mkdir(parents=True, exist_ok=True)
    consolidated_handler = ESTTimedRotatingFileHandler(
        str(consolidated_path),
        when='midnight',
        interval=1,
        backupCount=30,  # Keep 30 days of logs
        encoding='utf-8'
    )
    consolidated_handler.setLevel(logging.DEBUG)
    consolidated_handler.setFormatter(file_formatter)
    # logger.addHandler(consolidated_handler)

    # Component-specific file handler with EST-based rotation
    file_handler = ESTTimedRotatingFileHandler(
        str(full_log_path),
        when='midnight',
        interval=1,
        backupCount=30,  # Keep 30 days of logs
        encoding='utf-8'
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

    # Prevent propagation to root logger
    logger.propagate = False

    # Log initialization
    # logger.info(f"Logging initialized: level={log_level}, consolidated={consolidated_log}, component={full_log_path}")

    return logger


def get_logger(app_name: str = "quant_vibe") -> logging.Logger:
    """
    Get existing logger for an application.

    If logger doesn't exist, creates one with default settings.

    Args:
        app_name: Application/component name

    Returns:
        Logger instance
    """
    return setup_normalized_logging(
        app_name=app_name,
        log_dir=f"logs/{app_name}",
        console_output=True,
    )
