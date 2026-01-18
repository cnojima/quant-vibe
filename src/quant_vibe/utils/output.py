"""Output and logging utilities for backtest results."""

import sys
from pathlib import Path
from typing import TextIO


class TeeOutput:
    """Write output to both stdout and a file.

    This class allows you to redirect stdout so that all print statements
    are written to both the terminal and a log file simultaneously.

    Example:
        ```python
        tee = TeeOutput("backtest_log.txt")
        sys.stdout = tee
        try:
            print("This goes to both console and file")
        finally:
            tee.close()
        ```
    """

    def __init__(self, file_path: str | Path) -> None:
        """Initialize TeeOutput.

        Args:
            file_path: Path to the log file
        """
        self.terminal = sys.stdout
        self.log: TextIO = open(file_path, 'w', encoding='utf-8')

    def write(self, message: str) -> None:
        """Write message to both terminal and file.

        Args:
            message:
        """
        self.terminal.write(message)
        self.log.write(message)

    def flush(self) -> None:
        """Flush both terminal and file streams."""
        self.terminal.flush()
        self.log.flush()

    def close(self) -> None:
        """Close the log file and restore stdout."""
        self.log.close()
        sys.stdout = self.terminal
