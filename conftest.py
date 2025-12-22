"""Root conftest for pytest - loaded before all tests."""

import sys
from pathlib import Path


def pytest_configure(config):
    """Add src to path before pytest does anything."""
    src_path = Path(__file__).parent / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


# Also add immediately (for pytest's own import machinery)
src_path = Path(__file__).parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
