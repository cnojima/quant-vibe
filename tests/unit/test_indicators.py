"""Tests for technical indicators."""

import pandas as pd

from quant_vibe.indicators import calculate_sma, calculate_ema, calculate_rsi, calculate_macd


def test_calculate_sma():
    """Test Simple Moving Average calculation."""
    data = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    sma = calculate_sma(data, period=3)

    assert len(sma) == len(data)
    assert pd.isna(sma.iloc[0])
    assert pd.isna(sma.iloc[1])
    assert sma.iloc[2] == 2.0  # (1+2+3)/3
    assert sma.iloc[3] == 3.0  # (2+3+4)/3
    assert sma.iloc[9] == 9.0  # (8+9+10)/3


def test_calculate_ema():
    """Test Exponential Moving Average calculation."""
    data = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    ema = calculate_ema(data, period=3)

    assert len(ema) == len(data)
    assert not pd.isna(ema.iloc[0])
    assert ema.iloc[0] == 1.0
    # EMA should be more responsive than SMA
    assert ema.iloc[-1] > calculate_sma(data, period=3).iloc[-1]


def test_calculate_rsi():
    """Test RSI calculation."""
    # Create data with known up/down patterns
    data = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109])
    rsi = calculate_rsi(data, period=5)

    assert len(rsi) == len(data)
    # RSI should be between 0 and 100
    assert (rsi.dropna() >= 0).all()
    assert (rsi.dropna() <= 100).all()


def test_calculate_macd():
    """Test MACD calculation."""
    data = pd.Series(range(1, 101))
    macd, signal, histogram = calculate_macd(data, fast_period=12, slow_period=26, signal_period=9)

    assert len(macd) == len(data)
    assert len(signal) == len(data)
    assert len(histogram) == len(data)

    # Histogram should equal MACD - Signal
    diff = macd - signal - histogram
    assert (diff.dropna().abs() < 1e-10).all()


def test_sma_with_invalid_period():
    """Test SMA with period larger than data."""
    data = pd.Series([1, 2, 3, 4, 5])
    sma = calculate_sma(data, period=10)

    assert len(sma) == len(data)
    assert sma.isna().all()  # All values should be NaN
