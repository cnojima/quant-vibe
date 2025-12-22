# Streaming Service Unit Tests

Comprehensive unit tests for the SPXW Options Streaming Service.

## Test Coverage

- **test_config.py** (19 tests) - StreamingConfig dataclass validation
- **test_token_manager.py** (24 tests) - OAuth token management
- **test_aggregator.py** (37 tests) - Quote-to-bar aggregation logic
- **test_service.py** (22 tests) - Main StreamingService orchestrator

**Total: 102 unit tests**

## Running the Tests

### Method 1: Using the helper script (Recommended)

```bash
# Run all streaming service tests
./run_tests.sh

# Run specific test file
./run_tests.sh tests/unit/streaming_service/test_config.py

# Run with coverage
./run_tests.sh --cov=streaming_service

# Run specific test
./run_tests.sh tests/unit/streaming_service/test_config.py::TestStreamingConfig::test_default_configuration
```

### Method 2: Direct pytest with PYTHONPATH

```bash
# Run all tests
PYTHONPATH=src pytest tests/unit/streaming_service/ -v

# Run specific test file
PYTHONPATH=src pytest tests/unit/streaming_service/test_config.py -v

# Run with coverage
PYTHONPATH=src pytest tests/unit/streaming_service/ --cov=streaming_service --cov-report=term-missing

# Run specific test
PYTHONPATH=src pytest tests/unit/streaming_service/test_config.py::TestStreamingConfig::test_default_configuration -v
```

### Method 3: Using Python directly

```bash
# Run all tests
python -m pytest tests/unit/streaming_service/ -v

# This should work if you've installed the package in editable mode:
pip install -e .
```

## Test Organization

### test_config.py
Tests for configuration validation:
- Default and custom configurations
- Parameter validation (DTE, strike range, intervals)
- Edge cases and error handling

### test_token_manager.py
Tests for OAuth token management:
- Token refresh logic (success/failure)
- Refresh timing and scheduling
- Token age tracking
- Console output format

### test_aggregator.py
Tests for bar aggregation:
- Quote buffering
- OHLCV calculation from quotes
- VWAP computation
- Contract detail parsing (expiration, strike, type)
- Flush timing and logic

### test_service.py
Tests for main service:
- Service initialization
- SPX price fetching
- Contract discovery and filtering
- Message handling (LEVELONE_OPTIONS)
- Database persistence
- Resource cleanup

## Mocked Dependencies

All external dependencies are mocked:
- ✅ Schwab API client (`schwabdev.Client`)
- ✅ TimescaleDB store (`TimescaleStore`)
- ✅ Option contract enricher (`OptionContractEnricher`)
- ✅ Streaming connection (`schwabdev.Stream`)

Tests run entirely in-memory with no external API calls or database access.

## Fixtures

Common fixtures are available in `conftest.py`:
- `sample_spxw_quote` - Sample SPXW put option quote
- `sample_call_quote` - Sample call option quote
- `mock_schwab_client` - Mock Schwab API client
- `mock_timescale_store` - Mock database store
- `mock_enricher` - Mock contract enricher
- `levelone_options_message` - Sample streaming message
- `option_chain_response` - Sample option chain API response

## Example Test Runs

### Run all tests with verbose output
```bash
PYTHONPATH=src pytest tests/unit/streaming_service/ -v
```

### Run only config tests
```bash
PYTHONPATH=src pytest tests/unit/streaming_service/test_config.py -v
```

### Run tests matching pattern
```bash
PYTHONPATH=src pytest tests/unit/streaming_service/ -k "token" -v
```

### Run with coverage report
```bash
PYTHONPATH=src pytest tests/unit/streaming_service/ \
    --cov=streaming_service \
    --cov-report=term-missing \
    --cov-report=html
```

### Run with failfast (stop on first failure)
```bash
PYTHONPATH=src pytest tests/unit/streaming_service/ -x
```

## Continuous Integration

For CI/CD pipelines, use:

```yaml
# Example GitHub Actions
- name: Run streaming service tests
  run: |
    export PYTHONPATH=$PWD/src
    pytest tests/unit/streaming_service/ -v --cov=streaming_service
```

## Troubleshooting

### Import errors

If you see `ModuleNotFoundError: No module named 'streaming_service'`:

1. Ensure you're setting PYTHONPATH:
   ```bash
   export PYTHONPATH=$PWD/src
   pytest tests/unit/streaming_service/
   ```

2. Or install in editable mode:
   ```bash
   pip install -e .
   python -m pytest tests/unit/streaming_service/
   ```

3. Or use the helper script:
   ```bash
   ./run_tests.sh
   ```

### Tests not found

Make sure you're running pytest from the project root directory:
```bash
cd /path/to/quant-vibe
PYTHONPATH=src pytest tests/unit/streaming_service/
```

## Writing New Tests

When adding new tests:

1. Place them in the appropriate test file
2. Use existing fixtures from `conftest.py`
3. Mock all external dependencies
4. Follow the naming convention: `test_<feature>_<scenario>`
5. Include docstrings describing what's being tested

Example:
```python
def test_token_refresh_success(self, token_manager, mock_client):
    """Test successful token refresh."""
    result = token_manager.refresh()
    assert result is True
    assert token_manager.last_refresh is not None
```
