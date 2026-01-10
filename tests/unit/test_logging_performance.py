"""Test suite for unified logging performance optimizations."""
import logging
import time
from pathlib import Path
import tempfile
import shutil
from quant_vibe.logging.unified_logging import (
    setup_normalized_logging,
    get_logger,
    _EASTERN_TZ,
    _LOG_LEVEL_CACHE,
    _LOGGER_INSTANCES,
)


def test_timezone_caching():
    """Verify timezone is cached at module level."""
    assert _EASTERN_TZ is not None
    assert str(_EASTERN_TZ) == "America/New_York"
    print("✓ Timezone caching works")


def test_log_level_caching():
    """Verify log levels are cached after first call."""
    # Clear cache for test
    _LOG_LEVEL_CACHE.clear()

    from quant_vibe.logging.unified_logging import get_log_level

    # First call should populate cache
    level1 = get_log_level("test_app")
    assert "test_app" in _LOG_LEVEL_CACHE

    # Second call should use cache
    level2 = get_log_level("test_app")
    assert level1 == level2
    print("✓ Log level caching works")


def test_logger_singleton():
    """Verify logger singleton pattern works."""
    _LOGGER_INSTANCES.clear()

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create two loggers with same config
        logger1 = setup_normalized_logging(
            app_name="test_singleton",
            log_dir=tmpdir,
            console_output=False
        )

        logger2 = setup_normalized_logging(
            app_name="test_singleton",
            log_dir=tmpdir,
            console_output=False
        )

        # Should be same instance
        assert logger1 is logger2
        print("✓ Logger singleton pattern works")


def test_logging_performance():
    """Benchmark logging performance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = setup_normalized_logging(
            app_name="perf_test",
            log_dir=tmpdir,
            console_output=False
        )

        # Warm up
        for i in range(100):
            logger.info(f"Warmup {i}")

        # Benchmark
        num_logs = 1000
        start = time.time()

        for i in range(num_logs):
            logger.info(f"Test message {i}")

        elapsed = time.time() - start
        logs_per_sec = num_logs / elapsed

        print(f"✓ Performance: {logs_per_sec:.0f} logs/sec ({elapsed*1000/num_logs:.2f}ms per log)")

        # Should be reasonably fast (>1000 logs/sec on modern hardware)
        assert logs_per_sec > 500, f"Logging too slow: {logs_per_sec} logs/sec"


def test_multi_line_formatting():
    """Verify multi-line messages are formatted correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = setup_normalized_logging(
            app_name="multiline_test",
            log_dir=tmpdir,
            console_output=False
        )

        # Test multi-line message
        logger.info("Line 1\nLine 2\nLine 3")

        # Read log file
        log_files = list(Path(tmpdir).glob("*.log"))
        assert len(log_files) == 1

        content = log_files[0].read_text()
        assert "Line 1" in content
        assert "Line 2" in content
        assert "Line 3" in content
        print("✓ Multi-line formatting works")


def test_exception_logging():
    """Verify exception stack traces are logged correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = setup_normalized_logging(
            app_name="exception_test",
            log_dir=tmpdir,
            console_output=False
        )

        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.error("An error occurred", exc_info=True)

        # Read log file
        log_files = list(Path(tmpdir).glob("*.log"))
        assert len(log_files) == 1

        content = log_files[0].read_text()
        assert "ValueError" in content
        assert "Test exception" in content
        assert "Traceback" in content
        print("✓ Exception logging works")


if __name__ == "__main__":
    print("Running unified logging performance tests...\n")

    test_timezone_caching()
    test_log_level_caching()
    test_logger_singleton()
    test_multi_line_formatting()
    test_exception_logging()
    test_logging_performance()

    print("\n✓ All tests passed!")
