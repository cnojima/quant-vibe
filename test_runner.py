#!/usr/bin/env python
"""Simple test runner that ensures correct Python path."""

import sys
from pathlib import Path

# Add src to path BEFORE importing pytest
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Now run pytest
import pytest

if __name__ == "__main__":
    # Run pytest with the arguments passed to this script
    sys.exit(pytest.main(sys.argv[1:]))
