#!/usr/bin/env python
"""Direct test runner for streaming service tests - bypasses pytest import issues."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Now import and run tests directly
print("="*70)
print("STREAMING SERVICE TESTS")
print("="*70)
print()

# Test 1: StreamingConfig
print("Testing StreamingConfig...")
from streaming_service.config import StreamingConfig

# Test default config
config = StreamingConfig()
assert config.max_dte == 45
assert config.min_dte == 0
assert config.strike_range_pct == 0.10
print("  ✓ Default configuration works")

# Test custom config
config = StreamingConfig(max_dte=7, strike_range_pct=0.05)
assert config.max_dte == 7
assert config.strike_range_pct == 0.05
print("  ✓ Custom configuration works")

# Test validation
try:
    bad_config = StreamingConfig(max_dte=5, min_dte=10)
    assert False, "Should have raised ValueError"
except ValueError:
    print("  ✓ Validation works")

print()

# Test 2: TokenManager
print("Testing TokenManager...")
from streaming_service.token_manager import TokenManager
from unittest.mock import Mock

mock_client = Mock()
mock_client.update_tokens = Mock()
tm = TokenManager(mock_client, refresh_interval_minutes=14)
assert tm.refresh_interval_minutes == 14
assert tm.last_refresh is None
print("  ✓ TokenManager initialization works")

# Test refresh
result = tm.refresh()
assert result is True
assert tm.last_refresh is not None
print("  ✓ Token refresh works")

# Test needs_refresh
assert tm.needs_refresh() is False  # Just refreshed
print("  ✓ needs_refresh logic works")

print()

# Test 3: BarAggregator
print("Testing BarAggregator...")
from streaming_service.aggregator import BarAggregator, parse_expiration_from_ticker
from datetime import datetime

# Test expiration parsing
exp_date = parse_expiration_from_ticker("SPXW  260121P06200000")
assert exp_date is not None
assert exp_date.year == 2026
assert exp_date.month == 1
assert exp_date.day == 21
print("  ✓ Expiration parsing works")

# Test aggregator
agg = BarAggregator(aggregate_interval_seconds=60)
assert agg.aggregate_interval == 60
print("  ✓ BarAggregator initialization works")

# Add a quote
quote = {
    'symbol': 'SPXW  260121P06200000',
    'last': 100.5,
    'bid': 100.0,
    'ask': 101.0,
    'volume': 1000,
    'strike': 6200.0,
    'contract_type': 'P',
    'exp_year': 2026,
    'exp_month': 1,
    'exp_day': 21,
}
agg.add_quote(quote)
assert agg.get_buffered_symbol_count() == 1
print("  ✓ Quote buffering works")

# Flush
bars = agg.flush()
assert len(bars) == 1
assert bars[0]['option_ticker'] == 'SPXW  260121P06200000'
assert bars[0]['close'] == 100.5
print("  ✓ Bar aggregation works")

print()

# Test 4: StreamingService (basic initialization)
print("Testing StreamingService...")
from streaming_service.config import StreamingConfig
from unittest.mock import patch, MagicMock

with patch('streaming_service.service.schwabdev') as mock_schwabdev, \
     patch('streaming_service.service.TimescaleStore') as mock_ts, \
     patch('streaming_service.service.OptionContractEnricher') as mock_enricher, \
     patch.dict('os.environ', {'SCHWAB_API_KEY': 'test', 'SCHWAB_API_SECRET': 'test', 'SCHWAB_CALLBACK_URL': 'test'}):

    # Setup mocks
    mock_client = MagicMock()
    mock_schwabdev.Client.return_value = mock_client
    mock_schwabdev.Stream.return_value = MagicMock()
    mock_ts.return_value = MagicMock()
    mock_enricher.return_value = MagicMock()

    from streaming_service.service import StreamingService

    config = StreamingConfig(max_dte=7)
    service = StreamingService(config)

    assert service.config.max_dte == 7
    assert service.message_count == 0
    print("  ✓ StreamingService initialization works")

print()
print("="*70)
print(f"ALL BASIC TESTS PASSED ✓")
print("="*70)
print()
print("For full pytest test suite (102 tests), use:")
print("  python test_runner.py tests/unit/streaming_service/ -v")
print("  or: ./run_tests.sh")
