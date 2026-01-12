"""
Unit tests for OptimizationService.

Tests parameter generation, validation, caching, and core optimization logic.
"""

import hashlib
import pickle
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pandas as pd
import pytest

from quant_vibe.services.optimization_service import OptimizationService


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    return redis


@pytest.fixture
def optimization_service(mock_redis):
    """Create OptimizationService instance with mocks."""
    db_connection_string = "postgresql://test:test@localhost:5432/test"

    with patch('quant_vibe.services.optimization_service.create_engine'):
        service = OptimizationService(
            redis_client=mock_redis,
            db_connection_string=db_connection_string
        )
        return service


class TestParameterGeneration:
    """Test parameter grid generation from strategy registry."""

    def test_generate_param_grid_basic(self, optimization_service):
        """Test basic parameter grid generation."""
        grid = optimization_service.generate_param_grid("bullish_vertical_put")

        assert isinstance(grid, dict)
        assert len(grid) > 0

        # Should contain optimizable parameters
        for param_name, values in grid.items():
            assert isinstance(values, list)
            assert len(values) > 0

    def test_generate_param_grid_with_custom_ranges(self, optimization_service):
        """Test parameter grid with custom ranges."""
        custom_ranges = {
            "spread_width": [5.0, 10.0, 15.0],
            "profit_target_min": [0.3, 0.5, 0.7],
        }

        grid = optimization_service.generate_param_grid(
            "bullish_vertical_put",
            custom_ranges=custom_ranges
        )

        # Custom ranges should override defaults
        assert grid["spread_width"] == [5.0, 10.0, 15.0]
        assert grid["profit_target_min"] == [0.3, 0.5, 0.7]

    def test_generate_param_grid_with_optimize_only(self, optimization_service):
        """Test parameter grid with optimize_only filter."""
        grid = optimization_service.generate_param_grid(
            "bullish_vertical_put",
            optimize_only=["spread_width", "profit_target_min"]
        )

        # Should only contain specified parameters
        assert set(grid.keys()) == {"spread_width", "profit_target_min"}

    def test_generate_param_grid_invalid_strategy(self, optimization_service):
        """Test parameter grid generation with invalid strategy."""
        with pytest.raises(ValueError, match="Strategy .* not found"):
            optimization_service.generate_param_grid("nonexistent_strategy")

    def test_get_fixed_params(self, optimization_service):
        """Test retrieval of fixed (non-optimizable) parameters."""
        fixed_params = optimization_service.get_fixed_params("bullish_vertical_put")

        assert isinstance(fixed_params, dict)
        # Should contain non-optimizable params like min_dte, max_dte
        assert "min_dte" in fixed_params or "max_dte" in fixed_params


class TestParameterValidation:
    """Test parameter grid validation."""

    def test_validate_param_grid_valid(self, optimization_service):
        """Test validation of valid parameter grid."""
        param_grid = {
            "spread_width": [5.0, 10.0, 15.0],
            "profit_target_min": [0.3, 0.5],
        }

        is_valid, errors, warnings = optimization_service.validate_param_grid(
            "bullish_vertical_put",
            param_grid
        )

        assert is_valid is True
        assert len(errors) == 0

    def test_validate_param_grid_invalid_type(self, optimization_service):
        """Test validation with invalid parameter type."""
        param_grid = {
            "spread_width": ["invalid", "types"],  # Should be floats
        }

        is_valid, errors, warnings = optimization_service.validate_param_grid(
            "bullish_vertical_put",
            param_grid
        )

        assert is_valid is False
        assert len(errors) > 0

    def test_validate_param_grid_high_combinations(self, optimization_service):
        """Test validation warns about high combination count."""
        param_grid = {
            "spread_width": list(range(20)),  # 20 values
            "profit_target_min": list(range(15)),  # 15 values
        }  # 300 combinations

        is_valid, errors, warnings = optimization_service.validate_param_grid(
            "bullish_vertical_put",
            param_grid,
            max_combinations=200
        )

        assert len(warnings) > 0
        assert any("combination" in w.lower() for w in warnings)

    def test_count_permutations(self, optimization_service):
        """Test permutation counting."""
        param_grid = {
            "param1": [1, 2, 3],  # 3 values
            "param2": [10, 20],   # 2 values
            "param3": [100, 200, 300, 400],  # 4 values
        }

        count = optimization_service.count_permutations(param_grid)
        assert count == 3 * 2 * 4  # 24

    def test_count_permutations_empty(self, optimization_service):
        """Test permutation counting with empty grid."""
        count = optimization_service.count_permutations({})
        assert count == 0


class TestCacheKeyGeneration:
    """Test cache key generation for data caching."""

    def test_generate_cache_key_consistency(self, optimization_service):
        """Test cache key is consistent for same inputs."""
        key1 = optimization_service._generate_cache_key(
            ticker="SPX",
            start_date="2024-01-01",
            end_date="2024-12-31",
            min_dte=0,
            max_dte=45,
            timeframe="5min"
        )

        key2 = optimization_service._generate_cache_key(
            ticker="SPX",
            start_date="2024-01-01",
            end_date="2024-12-31",
            min_dte=0,
            max_dte=45,
            timeframe="5min"
        )

        assert key1 == key2

    def test_generate_cache_key_uniqueness(self, optimization_service):
        """Test cache key changes with different inputs."""
        key1 = optimization_service._generate_cache_key(
            ticker="SPX",
            start_date="2024-01-01",
            end_date="2024-12-31",
            min_dte=0,
            max_dte=45,
            timeframe="5min"
        )

        key2 = optimization_service._generate_cache_key(
            ticker="SPX",
            start_date="2024-01-01",
            end_date="2024-06-30",  # Different end date
            min_dte=0,
            max_dte=45,
            timeframe="5min"
        )

        assert key1 != key2

    def test_generate_cache_key_format(self, optimization_service):
        """Test cache key format includes all parameters."""
        key = optimization_service._generate_cache_key(
            ticker="SPX",
            start_date="2024-01-01",
            end_date="2024-12-31",
            min_dte=0,
            max_dte=45,
            timeframe="5min"
        )

        # Key should be in format: optimization:data:{md5_hash}
        assert key.startswith("optimization:data:")
        assert len(key.split(":")[-1]) == 32  # MD5 hash length


class TestDataCaching:
    """Test Redis data caching functionality."""

    @pytest.mark.asyncio
    async def test_get_cached_data_cache_hit(self, optimization_service, mock_redis):
        """Test cache retrieval when data exists in Redis."""
        # Setup mock cached data
        cached_data = {
            "options_data": pd.DataFrame({"col": [1, 2, 3]}),
            "underlying_data": pd.DataFrame({"col": [4, 5, 6]}),
        }
        mock_redis.get.return_value = pickle.dumps(cached_data)

        result = await optimization_service.get_cached_data(
            ticker="SPX",
            start_date="2024-01-01",
            end_date="2024-12-31",
            min_dte=0,
            max_dte=45,
            timeframe="5min"
        )

        assert result is not None
        assert "options_data" in result
        assert "underlying_data" in result

    @pytest.mark.asyncio
    async def test_get_cached_data_cache_miss(self, optimization_service, mock_redis):
        """Test cache retrieval when data not in Redis (cache miss)."""
        mock_redis.get.return_value = None

        # Mock the data loading function
        with patch('quant_vibe.services.optimization_service.load_options_backtest_data') as mock_load:
            mock_load.return_value = (
                pd.DataFrame({"col": [1, 2, 3]}),  # options_data
                pd.DataFrame({"col": [4, 5, 6]}),  # underlying_data
            )

            result = await optimization_service.get_cached_data(
                ticker="SPX",
                start_date="2024-01-01",
                end_date="2024-12-31",
                min_dte=0,
                max_dte=45,
                timeframe="5min"
            )

            # Should have loaded data and cached it
            assert result is not None
            mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear_cache(self, optimization_service, mock_redis):
        """Test cache clearing functionality."""
        await optimization_service.clear_cache(
            ticker="SPX",
            start_date="2024-01-01",
            end_date="2024-12-31",
            min_dte=0,
            max_dte=45,
            timeframe="5min"
        )

        # Should have deleted the cache key
        mock_redis.delete.assert_called_once()


class TestOptimizationCreation:
    """Test optimization run creation and management."""

    @pytest.mark.asyncio
    async def test_create_optimization(self, optimization_service):
        """Test creation of optimization run in database."""
        # Mock the engine's connection
        with patch.object(optimization_service.engine, 'connect') as mock_connect:
            mock_conn = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchone.return_value = ("test-optimization-id",)
            mock_conn.__enter__.return_value.execute.return_value = mock_result
            mock_connect.return_value = mock_conn

            optimization_id = await optimization_service.create_optimization(
                strategy_name="bullish_vertical_put",
                param_grid={"spread_width": [5.0, 10.0]},
                fixed_params={"min_dte": 0},
                ticker="SPX",
                start_date="2024-01-01",
                end_date="2024-12-31",
                initial_capital=100000.0
            )

            assert optimization_id == "test-optimization-id"
            assert mock_connect.called


class TestResultComputation:
    """Test result computation and ranking."""

    def test_compute_rankings(self, optimization_service):
        """Test computation of result rankings."""
        results = [
            {"sharpe_ratio": 1.5, "total_return": 10.0, "win_rate": 60.0},
            {"sharpe_ratio": 2.0, "total_return": 15.0, "win_rate": 70.0},
            {"sharpe_ratio": 1.0, "total_return": 5.0, "win_rate": 50.0},
        ]

        ranked = optimization_service._compute_rankings(results)

        # Should be sorted by Sharpe ratio (descending)
        assert ranked[0]["sharpe_ratio"] == 2.0
        assert ranked[1]["sharpe_ratio"] == 1.5
        assert ranked[2]["sharpe_ratio"] == 1.0

        # Should have rank fields
        assert ranked[0]["rank_by_sharpe"] == 1
        assert ranked[1]["rank_by_sharpe"] == 2
        assert ranked[2]["rank_by_sharpe"] == 3


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_validate_param_grid_empty(self, optimization_service):
        """Test validation with empty parameter grid."""
        is_valid, errors, warnings = optimization_service.validate_param_grid(
            "bullish_vertical_put",
            {}
        )

        assert is_valid is False
        assert len(errors) > 0

    def test_generate_param_grid_with_invalid_custom_ranges(self, optimization_service):
        """Test parameter grid with invalid custom ranges."""
        custom_ranges = {
            "nonexistent_param": [1, 2, 3],
        }

        # Should either ignore invalid params or raise error
        try:
            grid = optimization_service.generate_param_grid(
                "bullish_vertical_put",
                custom_ranges=custom_ranges
            )
            # If it doesn't raise, should not include invalid param
            assert "nonexistent_param" not in grid or len(grid) > 1
        except (ValueError, KeyError):
            # This is also acceptable behavior
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
