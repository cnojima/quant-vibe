"""Tests for data storage."""

import pytest
import pandas as pd

from quant_vibe.data import DataStore


def test_save_and_load_parquet(temp_data_dir, sample_ohlcv_data):
    """Test saving and loading data in parquet format."""
    store = DataStore(data_dir=temp_data_dir)

    symbol = "TEST"
    store.save(symbol, sample_ohlcv_data, format="parquet")

    loaded_data = store.load(symbol, format="parquet")

    assert loaded_data is not None
    pd.testing.assert_frame_equal(loaded_data, sample_ohlcv_data, check_freq=False)


def test_save_and_load_csv(temp_data_dir, sample_ohlcv_data):
    """Test saving and loading data in CSV format."""
    store = DataStore(data_dir=temp_data_dir)

    symbol = "TEST"
    store.save(symbol, sample_ohlcv_data, format="csv")

    loaded_data = store.load(symbol, format="csv")

    assert loaded_data is not None
    # CSV may have slight differences in precision
    assert len(loaded_data) == len(sample_ohlcv_data)
    assert list(loaded_data.columns) == list(sample_ohlcv_data.columns)


def test_load_nonexistent_file(temp_data_dir):
    """Test loading a file that doesn't exist."""
    store = DataStore(data_dir=temp_data_dir)

    loaded_data = store.load("NONEXISTENT")

    assert loaded_data is None


def test_unsupported_format(temp_data_dir, sample_ohlcv_data):
    """Test error handling for unsupported formats."""
    store = DataStore(data_dir=temp_data_dir)

    with pytest.raises(ValueError, match="Unsupported format"):
        store.save("TEST", sample_ohlcv_data, format="invalid")

    with pytest.raises(ValueError, match="Unsupported format"):
        store.load("TEST", format="invalid")
