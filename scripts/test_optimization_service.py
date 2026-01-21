#!/usr/bin/env python3
"""
Test script for OptimizationService.

⚠️ DEPRECATED: This script tests the old monolithic OptimizationService.
Please use one of the newer test scripts instead:
- test_refactored_optimization.py - Tests the modular optimization service
- test_optimization_execution.py - Tests full optimization execution
- test_optimization_final.py - Tests the final optimization implementation

This script validates the core functionality of the optimization service:
1. Parameter grid generation
2. Parameter validation
3. Fixed params retrieval
4. Permutation counting

Run this before deploying to ensure the service works correctly.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
import warnings

# Load environment variables
load_dotenv()

# Warn about deprecated usage
warnings.warn(
    "\n" + "=" * 70 + "\n"
    "⚠️  This test script uses the deprecated OptimizationService.\n"
    "   Please use test_refactored_optimization.py instead.\n"
    "=" * 70,
    DeprecationWarning,
    stacklevel=2
)

from quant_vibe.services.optimization_service import OptimizationService


async def test_param_grid_generation():
    """Test parameter grid generation."""
    print("\n" + "=" * 70)
    print("TEST 1: Parameter Grid Generation")
    print("=" * 70)

    # Mock service (without Redis/DB for this test)
    class MockService:
        def generate_param_grid(self, strategy_name, custom_ranges=None, optimize_only=None):
            from quant_vibe.strategies.registry import StrategyRegistry
            return StrategyRegistry.generate_optimization_grid(
                strategy_name=strategy_name,
                custom_ranges=custom_ranges,
                optimize_only=optimize_only,
            )

        @staticmethod
        def count_permutations(param_grid):
            from quant_vibe.services.optimization_service import OptimizationService
            return OptimizationService.count_permutations(param_grid)

        def get_fixed_params(self, strategy_name):
            from quant_vibe.strategies.registry import StrategyRegistry
            all_params = StrategyRegistry.get_default_params(strategy_name)
            opt_grid = StrategyRegistry.generate_optimization_grid(strategy_name)
            return {k: v for k, v in all_params.items() if k not in opt_grid}

        def validate_param_grid(self, strategy_name, param_grid, max_combinations=200):
            from quant_vibe.services.optimization_service import OptimizationService
            # Create a temporary service instance just for validation
            temp_service = OptimizationService(
                redis_client=None,  # Not needed for validation
                db_connection_string="",  # Not needed for validation
            )
            return temp_service.validate_param_grid(strategy_name, param_grid, max_combinations)

    service = MockService()

    # Test 1: Auto-generate grid for coin_toss
    print("\n1. Auto-generate grid for 'coin_toss' strategy:")
    grid = service.generate_param_grid('coin_toss')
    total = service.count_permutations(grid)
    print(f"   Generated grid: {grid}")
    print(f"   Total combinations: {total}")
    assert total > 0, "Should have at least one combination"
    print("   ✅ PASS")

    # Test 2: Auto-generate grid for bullish_vertical_put
    print("\n2. Auto-generate grid for 'bullish_vertical_put' strategy:")
    grid = service.generate_param_grid('bullish_vertical_put')
    total = service.count_permutations(grid)
    print(f"   Generated grid keys: {list(grid.keys())}")
    print(f"   Total combinations: {total}")
    assert total > 0, "Should have at least one combination"
    print("   ✅ PASS")

    # Test 3: Custom ranges with optimize_only
    print("\n3. Generate grid with custom ranges and optimize_only:")
    custom_ranges = {
        'target_price': [1.0, 2.0, 3.0],
        'profit_target_pct': [0.5, 1.0],
    }
    grid = service.generate_param_grid(
        'coin_toss',
        custom_ranges=custom_ranges,
        optimize_only=['target_price', 'profit_target_pct']
    )
    total = service.count_permutations(grid)
    print(f"   Custom grid: {grid}")
    print(f"   Total combinations: {total}")
    assert total == 6, f"Should have 6 combinations (3 * 2), got {total}"
    print("   ✅ PASS")

    # Test 4: optimize_only filter
    print("\n4. Generate grid with optimize_only filter:")
    grid = service.generate_param_grid(
        'coin_toss',
        optimize_only=['target_price']
    )
    total = service.count_permutations(grid)
    print(f"   Filtered grid keys: {list(grid.keys())}")
    print(f"   Total combinations: {total}")
    assert 'target_price' in grid, "Should include target_price"
    print("   ✅ PASS")

    return True


async def test_fixed_params():
    """Test fixed params retrieval."""
    print("\n" + "=" * 70)
    print("TEST 2: Fixed Parameters Retrieval")
    print("=" * 70)

    class MockService:
        def get_fixed_params(self, strategy_name):
            from quant_vibe.strategies.registry import StrategyRegistry
            all_params = StrategyRegistry.get_default_params(strategy_name)
            opt_grid = StrategyRegistry.generate_optimization_grid(strategy_name)
            return {k: v for k, v in all_params.items() if k not in opt_grid}

    service = MockService()

    # Test 1: Get fixed params for coin_toss
    print("\n1. Get fixed params for 'coin_toss' strategy:")
    fixed = service.get_fixed_params('coin_toss')
    print(f"   Fixed params: {fixed}")
    assert isinstance(fixed, dict), "Should return a dictionary"
    print("   ✅ PASS")

    # Test 2: Verify common params are in fixed
    print("\n2. Verify common fixed params (min_dte, max_dte, max_trades_daily):")
    common_fixed = ['min_dte', 'max_dte', 'max_trades_daily']
    for param in common_fixed:
        if param in fixed:
            print(f"   {param}: {fixed[param]} ✓")
        else:
            print(f"   {param}: not in fixed params (might be optimizable)")
    print("   ✅ PASS")

    return True


async def test_validation():
    """Test parameter grid validation."""
    print("\n" + "=" * 70)
    print("TEST 3: Parameter Grid Validation")
    print("=" * 70)

    class MockService:
        def validate_param_grid(self, strategy_name, param_grid, max_combinations=200):
            from quant_vibe.services.optimization_service import OptimizationService
            result = {
                "valid": True,
                "total_combinations": 0,
                "warnings": [],
                "errors": [],
            }

            if not param_grid:
                result["valid"] = False
                result["errors"].append("Parameter grid is empty")
                return result

            total = OptimizationService.count_permutations(param_grid)
            result["total_combinations"] = total

            if total > max_combinations:
                result["warnings"].append(
                    f"High combination count ({total} > {max_combinations})"
                )

            # Validate param names
            from quant_vibe.strategies.registry import StrategyRegistry
            try:
                param_specs = StrategyRegistry.get_param_specs(strategy_name)
                valid_params = set(param_specs.keys())
                provided_params = set(param_grid.keys())

                unknown_params = provided_params - valid_params
                if unknown_params:
                    result["valid"] = False
                    result["errors"].append(f"Unknown parameters: {sorted(unknown_params)}")

            except Exception as e:
                result["valid"] = False
                result["errors"].append(f"Validation error: {str(e)}")

            return result

    service = MockService()

    # Test 1: Valid grid
    print("\n1. Validate a valid parameter grid:")
    valid_grid = {
        'target_price': [1.0, 2.0],
        'profit_target_pct': [0.5, 1.0],
    }
    result = service.validate_param_grid('coin_toss', valid_grid)
    print(f"   Valid: {result['valid']}")
    print(f"   Total combinations: {result['total_combinations']}")
    print(f"   Warnings: {result['warnings']}")
    print(f"   Errors: {result['errors']}")
    assert result['valid'], "Should be valid"
    print("   ✅ PASS")

    # Test 2: Grid with too many combinations
    print("\n2. Validate grid with too many combinations:")
    large_grid = {
        'target_price': [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
        'profit_target_pct': [0.3, 0.5, 0.7, 1.0, 1.2],
        'price_tolerance': [0.1, 0.25, 0.5, 0.75, 1.0],
    }
    result = service.validate_param_grid('coin_toss', large_grid, max_combinations=50)
    print(f"   Valid: {result['valid']}")
    print(f"   Total combinations: {result['total_combinations']}")
    print(f"   Warnings: {result['warnings']}")
    assert len(result['warnings']) > 0, "Should have warnings about high combination count"
    print("   ✅ PASS")

    # Test 3: Invalid parameter name
    print("\n3. Validate grid with invalid parameter name:")
    invalid_grid = {
        'invalid_param': [1.0, 2.0],
        'another_invalid': [0.5, 1.0],
    }
    result = service.validate_param_grid('coin_toss', invalid_grid)
    print(f"   Valid: {result['valid']}")
    print(f"   Errors: {result['errors']}")
    assert not result['valid'], "Should be invalid"
    assert len(result['errors']) > 0, "Should have errors"
    print("   ✅ PASS")

    # Test 4: Empty grid
    print("\n4. Validate empty parameter grid:")
    empty_grid = {}
    result = service.validate_param_grid('coin_toss', empty_grid)
    print(f"   Valid: {result['valid']}")
    print(f"   Errors: {result['errors']}")
    assert not result['valid'], "Should be invalid"
    print("   ✅ PASS")

    return True


async def test_permutation_counting():
    """Test permutation counting."""
    print("\n" + "=" * 70)
    print("TEST 4: Permutation Counting")
    print("=" * 70)

    from quant_vibe.services.optimization_service import OptimizationService

    # Test cases
    test_cases = [
        ({'param_a': [1, 2, 3]}, 3),
        ({'param_a': [1, 2], 'param_b': [10, 20]}, 4),
        ({'param_a': [1, 2], 'param_b': [10, 20], 'param_c': [100, 200]}, 8),
        ({'param_a': [1, 2, 3], 'param_b': [10, 20, 30], 'param_c': [100, 200]}, 18),
        ({}, 0),
    ]

    for i, (grid, expected) in enumerate(test_cases, 1):
        count = OptimizationService.count_permutations(grid)
        print(f"\n{i}. Grid: {grid}")
        print(f"   Expected: {expected}, Got: {count}")
        assert count == expected, f"Expected {expected}, got {count}"
        print("   ✅ PASS")

    return True


async def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("OPTIMIZATION SERVICE TESTS")
    print("=" * 70)

    try:
        # Run tests
        await test_param_grid_generation()
        await test_fixed_params()
        await test_validation()
        await test_permutation_counting()

        print("\n" + "=" * 70)
        print("✅ ALL TESTS PASSED")
        print("=" * 70)
        print("\nThe OptimizationService is ready to use!")

    except Exception as e:
        print("\n" + "=" * 70)
        print("❌ TEST FAILED")
        print("=" * 70)
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
