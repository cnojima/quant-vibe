"""
Parameter grid management for optimization.

Handles generation, validation, and manipulation of parameter grids for strategy optimization.
"""

import itertools
from typing import Any, Dict, List, Optional, Set, Tuple

from quant_vibe.logging import get_logger
from quant_vibe.strategies.registry import StrategyRegistry


logger = get_logger(__name__)


class ParameterGridManager:
    """Manages parameter grids for strategy optimization."""

    def __init__(self):
        """Initialize parameter grid manager."""
        self.registry = StrategyRegistry()

    def generate_param_grid(
        self,
        strategy_name: str,
        custom_ranges: Optional[Dict[str, List[Any]]] = None,
        optimize_only: Optional[List[str]] = None,
    ) -> Dict[str, List[Any]]:
        """Generate parameter grid for optimization.

        Args:
            strategy_name: Name of strategy
            custom_ranges: Custom parameter ranges (overrides defaults)
            optimize_only: List of parameters to optimize (others excluded)

        Returns:
            Dictionary of parameter names to lists of values

        Raises:
            ValueError: If strategy not found
        """
        # Use StrategyRegistry to auto-generate grid
        optimization_ranges = self.registry.generate_optimization_grid(
            strategy_name=strategy_name,
            custom_ranges=custom_ranges,
            optimize_only=optimize_only,
        )

        logger.info(
            f"Generated param grid for {strategy_name}: "
            f"{len(optimization_ranges)} parameters, "
            f"{self.count_permutations(optimization_ranges):,} combinations"
        )

        return optimization_ranges

    def get_fixed_params(self, strategy_name: str) -> Dict[str, Any]:
        """Get fixed (non-optimizable) parameters for a strategy.

        Args:
            strategy_name: Name of strategy

        Returns:
            Dictionary of fixed parameter names to values

        Raises:
            ValueError: If strategy not found
        """
        # Get all default params
        all_params = self.registry.get_default_params(strategy_name)

        # Get optimization grid to determine which params are variable
        opt_grid = self.registry.generate_optimization_grid(strategy_name)

        # Fixed params are those not in the optimization grid
        fixed_params = {
            k: v for k, v in all_params.items()
            if k not in opt_grid
        }

        logger.info(
            f"Fixed params for {strategy_name}: {list(fixed_params.keys())}"
        )

        return fixed_params

    @staticmethod
    def count_permutations(param_grid: Dict[str, List[Any]]) -> int:
        """Count total parameter combinations.

        Args:
            param_grid: Dictionary of parameter names to lists of values

        Returns:
            Total number of combinations
        """
        if not param_grid:
            return 0

        count = 1
        for values in param_grid.values():
            if isinstance(values, list):
                count *= len(values)
            else:
                count *= 1

        return count

    def validate_param_grid(
        self,
        strategy_name: str,
        param_grid: Dict[str, List[Any]],
        max_combinations: int = 10000,
    ) -> Dict[str, Any]:
        """Validate parameter grid for a strategy.

        Args:
            strategy_name: Name of strategy
            param_grid: Parameter grid to validate
            max_combinations: Maximum allowed combinations

        Returns:
            Dictionary with validation results:
                - valid: bool
                - total_combinations: int
                - warnings: List[str]
                - errors: List[str]
        """
        warnings = []
        errors = []

        # Check strategy exists
        try:
            # Try to get default params to validate strategy exists
            all_params = self.registry.get_default_params(strategy_name)
        except (KeyError, ValueError):
            errors.append(f"Strategy '{strategy_name}' not found")
            return {
                "valid": False,
                "total_combinations": 0,
                "warnings": warnings,
                "errors": errors,
            }

        # Get optimization ranges
        optimization_ranges = self.registry.generate_optimization_grid(strategy_name)

        # Check for unknown parameters
        unknown_params = set(param_grid.keys()) - set(all_params.keys())
        if unknown_params:
            errors.append(
                f"Unknown parameters: {', '.join(sorted(unknown_params))}"
            )

        # Check for non-optimizable parameters
        fixed_params = self.get_fixed_params(strategy_name)
        non_optimizable = set(param_grid.keys()) & set(fixed_params.keys())
        if non_optimizable:
            warnings.append(
                f"Non-optimizable parameters included: {', '.join(sorted(non_optimizable))}"
            )

        # Validate parameter values
        for param_name, values in param_grid.items():
            if not isinstance(values, list):
                errors.append(f"Parameter '{param_name}' must have list of values")
                continue

            if len(values) == 0:
                errors.append(f"Parameter '{param_name}' has no values")

            # Type checking
            if param_name in all_params:
                default_value = all_params[param_name]
                expected_type = type(default_value)

                # Check type compatibility
                for value in values:
                    if not isinstance(value, expected_type):
                        # Allow int/float compatibility
                        if expected_type in (int, float) and isinstance(value, (int, float)):
                            continue
                        warnings.append(
                            f"Parameter '{param_name}' value {value} "
                            f"has type {type(value).__name__}, "
                            f"expected {expected_type.__name__}"
                        )

        # Count combinations
        total_combinations = self.count_permutations(param_grid)

        # Check combination limit
        if total_combinations > max_combinations:
            errors.append(
                f"Too many combinations: {total_combinations:,} > {max_combinations:,}"
            )

        # Performance warnings
        if total_combinations > 1000:
            estimated_time = total_combinations * 2  # ~2 seconds per combination
            warnings.append(
                f"Large optimization: {total_combinations:,} combinations "
                f"(~{estimated_time // 60} minutes)"
            )

        return {
            "valid": len(errors) == 0,
            "total_combinations": total_combinations,
            "warnings": warnings,
            "errors": errors,
        }

    @staticmethod
    def generate_combinations(param_grid: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
        """Generate all parameter combinations from grid.

        Args:
            param_grid: Dictionary of parameter names to lists of values

        Returns:
            List of parameter combination dictionaries
        """
        if not param_grid:
            return []

        # Get parameter names and value lists
        param_names = list(param_grid.keys())
        param_values = [param_grid[name] for name in param_names]

        # Generate all combinations
        combinations = []
        for values in itertools.product(*param_values):
            combination = dict(zip(param_names, values))
            combinations.append(combination)

        return combinations

    @staticmethod
    def filter_invalid_combinations(
        combinations: List[Dict[str, Any]],
        validation_fn: Optional[callable] = None,
    ) -> List[Dict[str, Any]]:
        """Filter out invalid parameter combinations.

        Args:
            combinations: List of parameter combinations
            validation_fn: Optional function to validate combinations

        Returns:
            List of valid parameter combinations
        """
        if not validation_fn:
            return combinations

        valid_combinations = []
        for combination in combinations:
            try:
                if validation_fn(combination):
                    valid_combinations.append(combination)
            except Exception as e:
                logger.warning(f"Error validating combination {combination}: {e}")

        return valid_combinations

    def merge_with_fixed_params(
        self,
        strategy_name: str,
        param_combination: Dict[str, Any],
        fixed_params_override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Merge parameter combination with fixed parameters.

        Args:
            strategy_name: Name of strategy
            param_combination: Optimizable parameter values
            fixed_params_override: Optional fixed parameter overrides

        Returns:
            Complete parameter dictionary
        """
        # Get default fixed params
        fixed_params = self.get_fixed_params(strategy_name)

        # Apply overrides
        if fixed_params_override:
            fixed_params.update(fixed_params_override)

        # Merge with combination (combination takes precedence)
        complete_params = fixed_params.copy()
        complete_params.update(param_combination)

        return complete_params

    def suggest_optimization_ranges(
        self,
        strategy_name: str,
        base_params: Dict[str, Any],
        expansion_factor: float = 0.5,
    ) -> Dict[str, List[Any]]:
        """Suggest optimization ranges based on base parameters.

        Args:
            strategy_name: Name of strategy
            base_params: Base parameter values
            expansion_factor: How much to expand around base values (0.5 = ±50%)

        Returns:
            Suggested parameter grid
        """
        try:
            # Validate strategy exists
            self.registry.get_default_params(strategy_name)
        except (KeyError, ValueError):
            raise ValueError(f"Strategy '{strategy_name}' not found")

        optimization_ranges = {}
        optimizable_params = self.registry.generate_optimization_grid(strategy_name)

        for param_name in optimizable_params:
            if param_name not in base_params:
                continue

            base_value = base_params[param_name]

            # Generate range based on type
            if isinstance(base_value, bool):
                # Boolean: both values
                optimization_ranges[param_name] = [True, False]

            elif isinstance(base_value, int):
                # Integer: expand range
                min_val = max(0, int(base_value * (1 - expansion_factor)))
                max_val = int(base_value * (1 + expansion_factor))
                step = max(1, (max_val - min_val) // 4)
                optimization_ranges[param_name] = list(range(min_val, max_val + 1, step))

            elif isinstance(base_value, float):
                # Float: expand range with steps
                min_val = base_value * (1 - expansion_factor)
                max_val = base_value * (1 + expansion_factor)
                step = (max_val - min_val) / 4
                optimization_ranges[param_name] = [
                    round(min_val + i * step, 2) for i in range(5)
                ]

            else:
                # Other types: use base value only
                optimization_ranges[param_name] = [base_value]

        return optimization_ranges