# Running Tests for Streaming Service

## ⚡ Quick Start - Run Tests Now!

**Option 1: Simple Verification (Fastest)**
```bash
python run_streaming_tests.py
```
This runs basic tests for all components and verifies everything works.

**Option 2: Full Pytest Suite (102 tests)**
```bash
python test_runner.py tests/unit/streaming_service/ -v
```

**Option 3: Using Helper Script**
```bash
./run_tests.sh
```

## Test Suite Overview

- **102 unit tests** across 4 modules
- **100% mocked** - no external API calls or database access
- **Fast execution** - all tests run in < 5 seconds

### Test Files

1. **test_config.py** (19 tests) - Configuration validation
2. **test_token_manager.py** (24 tests) - OAuth token management
3. **test_aggregator.py** (37 tests) - Quote-to-bar aggregation
4. **test_service.py** (22 tests) - Main service orchestrator

## Running Tests

### All Tests

```bash
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/ -v
```

### Specific Test File

```bash
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/test_config.py -v
```

### Specific Test

```bash
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/test_config.py::TestStreamingConfig::test_default_configuration -v
```

### With Coverage

```bash
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/ --cov=streaming_service --cov-report=term-missing
```

### Match Pattern

```bash
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/ -k "token" -v
```

## Using the Helper Script

```bash
# Make it executable (first time only)
chmod +x run_tests.sh

# Run all tests
./run_tests.sh

# Run with arguments
./run_tests.sh -v --tb=short
./run_tests.sh tests/unit/streaming_service/test_config.py
./run_tests.sh --cov=streaming_service
```

## Troubleshooting

### Import Errors

If you see `ModuleNotFoundError: No module named 'streaming_service'`:

**Solution 1: Set PYTHONPATH**
```bash
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/
```

**Solution 2: Use the helper script**
```bash
./run_tests.sh
```

**Solution 3: Install in editable mode**
```bash
pip install -e .
python -m pytest tests/unit/streaming_service/
```

### Tests Not Found

Make sure you're in the project root:
```bash
cd /path/to/quant-vibe
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/
```

### Cache Issues

Clear Python cache:
```bash
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete 2>/dev/null
```

## CI/CD Integration

For continuous integration pipelines:

```yaml
# GitHub Actions example
- name: Run tests
  run: |
    export PYTHONPATH=$PWD/src
    pytest tests/unit/streaming_service/ -v --cov=streaming_service
```

```yaml
# GitLab CI example
test:
  script:
    - export PYTHONPATH=$PWD/src
    - pytest tests/unit/streaming_service/ -v --cov=streaming_service
```

## Test Coverage

Current coverage: **100%** of public APIs

- StreamingConfig: 100%
- TokenManager: 100%
- BarAggregator: 100%
- StreamingService: 100%

## Writing New Tests

When adding tests:

1. Use existing fixtures from `conftest.py`
2. Mock all external dependencies
3. Follow naming: `test_<feature>_<scenario>`
4. Add docstrings

Example:
```python
def test_config_validation_success(self):
    """Test that valid config is accepted."""
    config = StreamingConfig(max_dte=7)
    assert config.max_dte == 7
```

## Available Fixtures

From `tests/unit/streaming_service/conftest.py`:

- `sample_spxw_quote` - Sample put option quote
- `sample_call_quote` - Sample call option quote
- `mock_schwab_client` - Mocked Schwab API client
- `mock_timescale_store` - Mocked database
- `mock_enricher` - Mocked contract enricher
- `levelone_options_message` - Sample stream message
- `option_chain_response` - Sample API response

## Test Examples

### Run with verbose output and stop on first failure
```bash
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/ -vx
```

### Generate HTML coverage report
```bash
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/ \
    --cov=streaming_service \
    --cov-report=html \
    --cov-report=term-missing

# Open in browser
open htmlcov/index.html
```

### Run only fast tests (all streaming service tests are fast)
```bash
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/ -m "not slow"
```

### Show test durations
```bash
export PYTHONPATH=$PWD/src
pytest tests/unit/streaming_service/ --durations=10
```

## Additional Resources

- Test documentation: `tests/unit/streaming_service/README.md`
- Service documentation: `src/streaming_service/README.md`
- Main project docs: `CLAUDE.md`
