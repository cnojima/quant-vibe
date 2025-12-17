"""Pytest configuration and fixtures."""

import pytest
import pandas as pd
import numpy as np


@pytest.fixture
def sample_ohlcv_data() -> pd.DataFrame:
    """Create sample OHLCV data for testing."""
    dates = pd.date_range(start="2023-01-01", end="2023-12-31", freq="D")
    n = len(dates)

    # Generate synthetic price data
    np.random.seed(42)
    close_prices = 100 + np.cumsum(np.random.randn(n) * 2)

    data = pd.DataFrame(
        {
            "Open": close_prices + np.random.randn(n) * 0.5,
            "High": close_prices + np.abs(np.random.randn(n) * 1.5),
            "Low": close_prices - np.abs(np.random.randn(n) * 1.5),
            "Close": close_prices,
            "Volume": np.random.randint(1000000, 10000000, n),
        },
        index=dates,
    )

    return data


@pytest.fixture
def temp_data_dir(tmp_path):
    """Create temporary data directory for testing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return str(data_dir)
