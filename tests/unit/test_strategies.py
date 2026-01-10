"""Tests for trading strategies."""

import pytest
import pandas as pd
from datetime import datetime
import pytz

from quant_vibe.strategies import SMACrossoverStrategy, HailMaryStrategy
from quant_vibe.strategies.base import Signal


def test_sma_crossover_strategy(sample_ohlcv_data):
    """Test SMA crossover strategy signal generation."""
    strategy = SMACrossoverStrategy(fast_period=10, slow_period=20)
    signals = strategy.generate_signals(sample_ohlcv_data)

    assert len(signals) == len(sample_ohlcv_data)
    # Signals should only contain valid values
    assert set(signals.unique()).issubset({Signal.BUY.value, Signal.SELL.value, Signal.HOLD.value})


def test_sma_crossover_buy_signal():
    """Test that BUY signal is generated on upward crossover."""
    # Create data with clear upward trend
    dates = pd.date_range(start="2023-01-01", periods=50, freq="D")
    prices = pd.Series(range(100, 150), index=dates)

    data = pd.DataFrame(
        {
            "Open": prices,
            "High": prices + 1,
            "Low": prices - 1,
            "Close": prices,
            "Volume": 1000000,
        }
    )

    strategy = SMACrossoverStrategy(fast_period=5, slow_period=10)
    signals = strategy.generate_signals(data)

    # Should have at least one BUY signal
    assert (signals == Signal.BUY.value).any()


def test_sma_crossover_sell_signal():
    """Test that SELL signal is generated on downward crossover."""
    # Create data that goes up then down
    dates = pd.date_range(start="2023-01-01", periods=50, freq="D")
    prices_up = list(range(100, 125))
    prices_down = list(range(124, 99, -1))
    prices = pd.Series(prices_up + prices_down, index=dates)

    data = pd.DataFrame(
        {
            "Open": prices,
            "High": prices + 1,
            "Low": prices - 1,
            "Close": prices,
            "Volume": 1000000,
        }
    )

    strategy = SMACrossoverStrategy(fast_period=5, slow_period=10)
    signals = strategy.generate_signals(data)

    # Should have at least one SELL signal
    assert (signals == Signal.SELL.value).any()


def test_strategy_validate_data():
    """Test that strategy validates required columns."""
    strategy = SMACrossoverStrategy()

    # Missing required columns
    invalid_data = pd.DataFrame({"Price": [100, 101, 102]})

    with pytest.raises(ValueError, match="Missing required columns"):
        strategy.generate_signals(invalid_data)


# Hail Mary Strategy Tests


def test_hail_mary_initialization():
    """Test Hail Mary strategy initialization."""
    strategy = HailMaryStrategy(
        otm_percent_min=0.05,
        otm_percent_max=0.10,
        entry_time_before_close=15,
        num_contracts=10,
        trailing_stop_pct=0.05,
    )

    assert strategy.name == "HailMary"
    assert strategy.otm_percent_min == 0.05
    assert strategy.otm_percent_max == 0.10
    assert strategy.entry_time_before_close == 15
    assert strategy.num_contracts == 10
    assert strategy.trailing_stop_pct == 0.05


def test_hail_mary_entry_window_detection():
    """Test that Hail Mary detects entry window correctly."""
    strategy = HailMaryStrategy(entry_time_before_close=15)

    # Create underlying data
    current_time = datetime(2025, 12, 30, 20, 45, 0, tzinfo=pytz.UTC)  # 3:45 PM ET
    underlying_data = pd.DataFrame({
        'close': [5900.0],
    }, index=[current_time])

    # Create empty options data
    options_data = pd.DataFrame()

    # Analyze market
    analysis = strategy.analyze_market(underlying_data, options_data, current_time)

    # Should be in entry window (15 min before close)
    assert analysis['in_entry_window'] == True
    assert analysis['current_price'] == 5900.0


def test_hail_mary_outside_entry_window():
    """Test that Hail Mary does not signal outside entry window."""
    strategy = HailMaryStrategy(entry_time_before_close=15)

    # Create underlying data - too early (2:00 PM ET)
    current_time = datetime(2025, 12, 30, 19, 0, 0, tzinfo=pytz.UTC)  # 2:00 PM ET
    underlying_data = pd.DataFrame({
        'close': [5900.0],
    }, index=[current_time])

    options_data = pd.DataFrame()

    # Analyze market
    analysis = strategy.analyze_market(underlying_data, options_data, current_time)

    # Should NOT be in entry window
    assert analysis['in_entry_window'] == False


def test_hail_mary_should_enter():
    """Test that Hail Mary generates entry signal in correct window."""
    strategy = HailMaryStrategy(entry_time_before_close=15)

    # Create underlying data - entry window (3:45 PM ET)
    current_time = datetime(2025, 12, 30, 20, 45, 0, tzinfo=pytz.UTC)  # 3:45 PM ET
    underlying_data = pd.DataFrame({
        'close': [5900.0],
    }, index=[current_time])

    # Create minimal options data (just to pass empty check)
    options_data = pd.DataFrame({
        'contract_symbol': ['SPXW251231C6000'],
        'strike_price': [6000.0],
        'contract_type': ['call'],
        'expiration_date': [pd.Timestamp('2025-12-31')],
        'mark': [10.0],
        'volume': [100],
    })

    # Analyze market
    analysis = strategy.analyze_market(underlying_data, options_data, current_time)

    # Should enter
    should_enter = strategy.should_enter(underlying_data, options_data, current_time, analysis)
    assert should_enter == True


def test_hail_mary_no_duplicate_entry():
    """Test that Hail Mary doesn't enter multiple times per day."""
    strategy = HailMaryStrategy(entry_time_before_close=15, max_trades_daily=1)

    # Create underlying data - entry window
    current_time = datetime(2025, 12, 30, 20, 45, 0, tzinfo=pytz.UTC)  # 3:45 PM ET
    underlying_data = pd.DataFrame({
        'close': [5900.0],
    }, index=[current_time])

    options_data = pd.DataFrame({
        'contract_symbol': ['SPXW251231C6000'],
        'strike_price': [6000.0],
        'contract_type': ['call'],
        'expiration_date': [pd.Timestamp('2025-12-31')],
        'mark': [10.0],
        'volume': [100],
    })

    # Set current_day so analyze_market doesn't reset state
    strategy.current_day = current_time.date()

    # Mark that we already entered today
    strategy.entered_today = True
    strategy.increment_daily_trade_count()

    # Analyze market
    analysis = strategy.analyze_market(underlying_data, options_data, current_time)

    # Should NOT be in entry window (because we already entered today)
    assert analysis['in_entry_window'] == False

    # Should NOT enter (already traded today)
    should_enter = strategy.should_enter(underlying_data, options_data, current_time, analysis)
    assert should_enter == False


def test_hail_mary_reset_daily_state():
    """Test that Hail Mary resets daily state."""
    strategy = HailMaryStrategy()

    # Set some state
    strategy.entered_today = True
    strategy.trades_today = 1

    # Reset
    strategy.reset_daily_state()

    # State should be cleared
    assert strategy.entered_today == False
    assert strategy.trades_today == 0
