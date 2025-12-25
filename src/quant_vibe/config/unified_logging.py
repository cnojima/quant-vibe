"""Unified logging configuration for all quant-vibe components.

Provides normalized logging format: [datetime][app][level][msg]
with proper stack trace handling.
"""

import logging
import sys
import traceback
from pathlib import Path
from datetime import datetime
from typing import Optional


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
        # Format timestamp
        timestamp = datetime.fromtimestamp(record.created).strftime(self.datefmt)

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


def setup_normalized_logging(
    app_name: str = "quant_vibe",
    log_level: str = "INFO",
    log_dir: str = "logs",
    log_file: Optional[str] = None,
    console_output: bool = True,
    include_func: bool = False,
) -> logging.Logger:
    """
    Set up normalized logging for any component.

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
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Generate log file name if not provided
    if log_file is None:
        timestamp = datetime.now().strftime("%Y%m%d")
        log_file = f"{app_name}_{timestamp}.log"

    full_log_path = log_path / log_file

    # Create logger
    logger = logging.getLogger(app_name)
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove existing handlers to avoid duplicates
    logger.handlers = []

    # Create formatters
    file_formatter = NormalizedFormatter(app_name=app_name, include_func=True)
    console_formatter = NormalizedFormatter(app_name=app_name, include_func=False)

    # File handler - capture everything
    file_handler = logging.FileHandler(full_log_path, encoding='utf-8')
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
    logger.info(f"Logging initialized: level={log_level}, file={full_log_path}")

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
    logger = logging.getLogger(app_name)

    # If logger has no handlers, set up default logging
    if not logger.handlers:
        logger = setup_normalized_logging(app_name=app_name)

    return logger


# Convenience function for backward compatibility
def setup_logging(
    log_level: str = "INFO",
    log_file: str = "logs/quant_vibe.log",
) -> None:
    """
    Legacy setup_logging function for backward compatibility.

    Args:
        log_level: Logging level
        log_file: Path to log file
    """
    log_path = Path(log_file)
    setup_normalized_logging(
        app_name="quant_vibe",
        log_level=log_level,
        log_dir=str(log_path.parent),
        log_file=log_path.name,
    )
