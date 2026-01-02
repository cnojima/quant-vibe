"""
Central Strategy Registry - Single source of truth for all strategies.

This module provides a unified registry for all trading strategies, ensuring
consistent parameter validation across backtest, live trading, optimization,
and Admin UI components.

Design:
- Single source of truth: Pydantic models in params.py
- Automatic validation before strategy instantiation
- Auto-generation of metadata for Admin UI
- Auto-generation of optimization grids
- Fail-fast with clear error messages

Usage:
    from quant_vibe.strategies.registry import StrategyRegistry

    # Validate params
    StrategyRegistry.validate_params('coin_toss', params)

    # Instantiate strategy
    strategy = StrategyRegistry.create_strategy('coin_toss', params)

    # Get param specs for UI
    specs = StrategyRegistry.get_param_specs('coin_toss')

    # Auto-generate optimization grid
    grid = StrategyRegistry.generate_optimization_grid('coin_toss')
"""

from typing import Dict, Any, Type, List, Optional, Tuple
from pydantic import BaseModel
import inspect

from quant_vibe.strategies.options_base import OptionsStrategy
from quant_vibe.strategies.params import (
    STRATEGY_PARAMS_MAP,
    validate_and_normalize_params,
    get_strategy_params_model,
)

# Import all strategy classes
from quant_vibe.strategies.bullish_vertical_put import BullishVerticalPutStrategy
from quant_vibe.strategies.bullish_vertical_call import BullishVerticalCallStrategy
from quant_vibe.strategies.bearish_iv_scalp import BearishIVScalpStrategy
from quant_vibe.strategies.coin_toss import CoinTossStrategy
from quant_vibe.strategies.coin_toss_limit import CoinTossLimitStrategy
from quant_vibe.strategies.bollinger_band import BollingerBandStrategy
from quant_vibe.strategies.bollinger_band_limit import BollingerBandLimitStrategy
from quant_vibe.strategies.naive_bullish_put import NaiveBullishPutStrategy
from quant_vibe.strategies.hail_mary import HailMaryStrategy


class StrategyRegistry:
    """
    Central registry for all trading strategies.

    Provides:
    - Strategy class lookup
    - Parameter validation (via Pydantic)
    - Metadata generation for Admin UI
    - Optimization grid generation
    - Safe strategy instantiation
    """

    # Map strategy names to strategy classes
    _STRATEGY_CLASSES: Dict[str, Type[OptionsStrategy]] = {
        'bullish_vertical_put': BullishVerticalPutStrategy,
        'bullish_vertical_call': BullishVerticalCallStrategy,
        'bearish_iv_scalp': BearishIVScalpStrategy,
        'coin_toss': CoinTossStrategy,
        'coin_toss_limit': CoinTossLimitStrategy,
        'bollinger_band': BollingerBandStrategy,
        'bollinger_band_limit': BollingerBandLimitStrategy,
        'naive_bullish_put': NaiveBullishPutStrategy,
        'hail_mary': HailMaryStrategy,
    }

    # Map strategy names to module paths (for dynamic import)
    _MODULE_PATHS: Dict[str, str] = {
        'bullish_vertical_put': 'quant_vibe.strategies.bullish_vertical_put.BullishVerticalPutStrategy',
        'bullish_vertical_call': 'quant_vibe.strategies.bullish_vertical_call.BullishVerticalCallStrategy',
        'bearish_iv_scalp': 'quant_vibe.strategies.bearish_iv_scalp.BearishIVScalpStrategy',
        'coin_toss': 'quant_vibe.strategies.coin_toss.CoinTossStrategy',
        'coin_toss_limit': 'quant_vibe.strategies.coin_toss_limit.CoinTossLimitStrategy',
        'bollinger_band': 'quant_vibe.strategies.bollinger_band.BollingerBandStrategy',
        'bollinger_band_limit': 'quant_vibe.strategies.bollinger_band_limit.BollingerBandLimitStrategy',
        'naive_bullish_put': 'quant_vibe.strategies.naive_bullish_put.NaiveBullishPutStrategy',
        'hail_mary': 'quant_vibe.strategies.hail_mary.HailMaryStrategy',
    }

    # Strategy descriptions for UI
    _DESCRIPTIONS: Dict[str, str] = {
        'bullish_vertical_put': 'Credit spread strategy (sell put, buy lower put) for bullish markets',
        'bullish_vertical_call': 'Debit spread strategy (buy call, sell higher call) for bullish markets',
        'bearish_iv_scalp': 'Credit spread strategy (sell call, buy higher call) targeting IV spikes during bearish moves (0DTE scalping)',
        'coin_toss': 'Naive strategy that randomly picks direction and buys 10 contracts near $2, sells at $2 (educational/experimental only)',
        'coin_toss_limit': 'Refined coin toss with limit orders: buy at $1, sell at $2 for 100% profit (educational/experimental only)',
        'bollinger_band': 'Uses Bollinger Bands for direction (calls at lower band, puts at upper band) with market orders (educational/experimental)',
        'bollinger_band_limit': 'Uses Bollinger Bands for direction (calls at lower band, puts at upper band) with limit orders: buy at $1, sell at $2 (educational/experimental)',
        'naive_bullish_put': 'Simple vertical put spread - opens at market open for UI testing (educational/experimental)',
        'hail_mary': 'Speculative overnight call buying: buys 10 far OTM (5-10%) calls 15min before close, holds overnight with 5% trailing stop',
    }

    @classmethod
    def register(cls, name: str, strategy_class: Type[OptionsStrategy], description: str = ""):
        """
        Register a new strategy.

        Args:
            name: Strategy identifier (e.g., 'coin_toss')
            strategy_class: Strategy class
            description: Human-readable description for UI
        """
        if not issubclass(strategy_class, OptionsStrategy):
            raise ValueError(f"{strategy_class} must inherit from OptionsStrategy")

        cls._STRATEGY_CLASSES[name] = strategy_class
        if description:
            cls._DESCRIPTIONS[name] = description

    @classmethod
    def get_strategy_class(cls, name: str) -> Type[OptionsStrategy]:
        """
        Get strategy class by name.

        Args:
            name: Strategy name

        Returns:
            Strategy class

        Raises:
            ValueError: If strategy not found
        """
        if name not in cls._STRATEGY_CLASSES:
            available = ', '.join(sorted(cls._STRATEGY_CLASSES.keys()))
            raise ValueError(
                f"Unknown strategy: '{name}'\n"
                f"Available strategies: {available}"
            )
        return cls._STRATEGY_CLASSES[name]

    @classmethod
    def get_module_path(cls, name: str) -> str:
        """
        Get module path for dynamic import.

        Args:
            name: Strategy name

        Returns:
            Module path string (e.g., 'quant_vibe.strategies.coin_toss.CoinTossStrategy')
        """
        if name not in cls._MODULE_PATHS:
            available = ', '.join(sorted(cls._MODULE_PATHS.keys()))
            raise ValueError(
                f"Unknown strategy: '{name}'\n"
                f"Available strategies: {available}"
            )
        return cls._MODULE_PATHS[name]

    @classmethod
    def validate_params(cls, strategy_name: str, params: Dict[str, Any], strict: bool = False) -> Dict[str, Any]:
        """
        Validate parameters using Pydantic model.

        Args:
            strategy_name: Name of strategy
            params: Parameter dictionary to validate
            strict: If True, raise error on unknown parameters (default: False, warn only)

        Returns:
            Validated and normalized parameters

        Raises:
            ValueError: If strategy unknown or params invalid (or unknown params in strict mode)
        """
        # Verify strategy exists
        cls.get_strategy_class(strategy_name)

        # Get valid parameter names
        try:
            param_model = get_strategy_params_model(strategy_name)
            valid_params = set(param_model.model_fields.keys())
        except:
            valid_params = set()

        # Check for unknown parameters
        unknown_params = set(params.keys()) - valid_params
        if unknown_params:
            warning_msg = (
                f"Warning: Unknown parameters for strategy '{strategy_name}': {sorted(unknown_params)}\n"
                f"Valid parameters: {sorted(valid_params)}"
            )
            if strict:
                raise ValueError(warning_msg)
            else:
                # Import logger for warning
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(warning_msg)

        # Validate using Pydantic model
        try:
            validated = validate_and_normalize_params(strategy_name, params)
            return validated
        except Exception as e:
            valid_params_str = ', '.join(sorted(valid_params))
            raise ValueError(
                f"Invalid parameters for strategy '{strategy_name}': {e}\n"
                f"Valid parameters: {valid_params_str}"
            ) from e

    @classmethod
    def create_strategy(
        cls,
        strategy_name: str,
        params: Dict[str, Any],
        validate: bool = True
    ) -> OptionsStrategy:
        """
        Create and instantiate a strategy with validated parameters.

        Args:
            strategy_name: Name of strategy
            params: Strategy parameters
            validate: Whether to validate params (default: True)

        Returns:
            Instantiated strategy instance

        Raises:
            ValueError: If strategy unknown or params invalid
        """
        # Get strategy class
        strategy_class = cls.get_strategy_class(strategy_name)

        # Validate params if requested
        if validate:
            validated_params = cls.validate_params(strategy_name, params)
        else:
            # Fallback: filter by constructor signature
            sig = inspect.signature(strategy_class.__init__)
            validated_params = {
                k: v for k, v in params.items()
                if k in sig.parameters
            }

        # Instantiate strategy
        try:
            strategy = strategy_class(**validated_params)
            return strategy
        except Exception as e:
            raise ValueError(
                f"Failed to instantiate strategy '{strategy_name}': {e}"
            ) from e

    @classmethod
    def get_param_specs(cls, strategy_name: str) -> Dict[str, Any]:
        """
        Get parameter specifications from Pydantic model.

        Args:
            strategy_name: Name of strategy

        Returns:
            Dictionary with parameter specs (name, type, default, description, constraints)

        Example:
            {
                'target_price': {
                    'type': 'float',
                    'default': 2.0,
                    'description': 'Target contract price',
                    'ge': 0.0,  # Greater than or equal
                },
                ...
            }
        """
        # Verify strategy exists
        cls.get_strategy_class(strategy_name)

        # Get Pydantic model
        param_model = get_strategy_params_model(strategy_name)

        # Extract field specifications
        specs = {}
        for field_name, field_info in param_model.model_fields.items():
            spec = {
                'type': field_info.annotation.__name__ if hasattr(field_info.annotation, '__name__') else str(field_info.annotation),
                'default': field_info.default if field_info.default is not None else None,
                'description': field_info.description or f"Parameter {field_name}",
            }

            # Add constraints from Field()
            if hasattr(field_info, 'metadata'):
                for constraint in field_info.metadata:
                    if hasattr(constraint, 'ge'):
                        spec['ge'] = constraint.ge
                    if hasattr(constraint, 'le'):
                        spec['le'] = constraint.le
                    if hasattr(constraint, 'gt'):
                        spec['gt'] = constraint.gt
                    if hasattr(constraint, 'lt'):
                        spec['lt'] = constraint.lt

            specs[field_name] = spec

        return specs

    @classmethod
    def get_default_params(cls, strategy_name: str) -> Dict[str, Any]:
        """
        Get default parameters for a strategy.

        Args:
            strategy_name: Name of strategy

        Returns:
            Dictionary of default parameters
        """
        specs = cls.get_param_specs(strategy_name)
        return {k: v['default'] for k, v in specs.items() if v['default'] is not None}

    @classmethod
    def generate_optimization_grid(
        cls,
        strategy_name: str,
        custom_ranges: Optional[Dict[str, List[Any]]] = None,
        optimize_only: Optional[List[str]] = None,
        num_values: int = 3,
    ) -> Dict[str, List[Any]]:
        """
        Auto-generate optimization grid from parameter specs.

        IMPORTANT: This method now generates FEWER values by default (3 instead of 5)
        to prevent combinatorial explosion. Use custom_ranges or optimize_only to
        control which parameters are optimized.

        Args:
            strategy_name: Name of strategy
            custom_ranges: Optional custom ranges to override defaults
            optimize_only: Optional list of parameter names to optimize (ignores others)
            num_values: Number of values to generate per parameter (default: 3)

        Returns:
            Parameter grid for optimization

        Example:
            # Auto-generate grid (only 3 values per parameter)
            grid = generate_optimization_grid('coin_toss')

            # Optimize only specific parameters
            grid = generate_optimization_grid('coin_toss', optimize_only=['target_price', 'profit_target_pct'])

            # Custom ranges for specific parameters
            grid = generate_optimization_grid('coin_toss', custom_ranges={'target_price': [1.0, 1.5, 2.0, 2.5]})

        Note:
            - Parameters commonly excluded from optimization:
              - min_dte, max_dte (usually fixed based on strategy concept)
              - observation_period (usually fixed based on strategy concept)
              - num_spreads (position sizing, not strategy logic)
              - max_trades_daily (risk management, not strategy logic)
              - min_volume, min_bid_ask_spread_pct (data quality filters)
            - Parameters good for optimization:
              - Entry thresholds (pullback_amount, bb_threshold, etc.)
              - Exit targets (profit_target_*, stop_loss_*)
              - Strategy-specific parameters (spread_width, target_price, etc.)
        """
        specs = cls.get_param_specs(strategy_name)
        grid = {}

        # Common parameters to EXCLUDE from auto-generation (usually fixed)
        # These are typically risk management, position sizing, or data quality filters
        EXCLUDE_FROM_AUTO_OPTIMIZATION = {
            'min_dte', 'max_dte',  # Strategy concept parameters
            'observation_period',  # Strategy concept parameter
            'num_spreads',  # Position sizing
            'max_trades_daily',  # Risk management
            'min_volume',  # Data quality filter
            'min_bid_ask_spread_pct',  # Data quality filter
            'profit_target_max',  # Usually fixed at 1.0 (100%)
        }

        for param_name, spec in specs.items():
            # Skip if optimize_only is specified and this param is not in it
            if optimize_only is not None and param_name not in optimize_only:
                continue

            # Skip if custom range provided
            if custom_ranges and param_name in custom_ranges:
                grid[param_name] = custom_ranges[param_name]
                continue

            # Skip common parameters that shouldn't be auto-optimized
            if optimize_only is None and param_name in EXCLUDE_FROM_AUTO_OPTIMIZATION:
                continue

            # Auto-generate range based on type and constraints
            param_type = spec['type']
            default = spec.get('default')

            if default is None:
                continue  # Skip required params with no default

            # Generate range based on type
            if param_type in ('float', 'int'):
                ge = spec.get('ge', 0)
                le = spec.get('le')

                # Generate num_values values around default
                if le is not None:
                    # Use range from ge to le
                    step = (le - ge) / (num_values - 1) if num_values > 1 else 0
                    values = [ge + i * step for i in range(num_values)]
                else:
                    # Use values around default (e.g., 0.8x, 1.0x, 1.2x for num_values=3)
                    if num_values == 3:
                        values = [default * 0.8, default, default * 1.2]
                    elif num_values == 5:
                        values = [default * 0.6, default * 0.8, default, default * 1.2, default * 1.4]
                    else:
                        # General case: spread values around default
                        spread = 0.4  # ±40% range
                        step = (2 * spread * default) / (num_values - 1) if num_values > 1 else 0
                        values = [default * (1 - spread) + i * step for i in range(num_values)]

                    # Apply ge constraint
                    values = [max(v, ge) for v in values]

                # Convert to int if needed
                if param_type == 'int':
                    values = sorted(set(int(v) for v in values))
                else:
                    values = sorted(set(round(v, 2) for v in values))

                # Only add to grid if we have multiple unique values
                if len(values) > 1:
                    grid[param_name] = values

        return grid

    @classmethod
    def get_metadata_for_admin_ui(cls, strategy_name: str) -> Dict[str, Any]:
        """
        Generate metadata for Admin UI (auto-generated from Pydantic).

        Args:
            strategy_name: Name of strategy

        Returns:
            Metadata dictionary with description and default_params
        """
        return {
            'description': cls._DESCRIPTIONS.get(strategy_name, f"Strategy: {strategy_name}"),
            'default_params': cls.get_default_params(strategy_name),
        }

    @classmethod
    def list_strategies(cls) -> List[str]:
        """
        Get list of all registered strategy names.

        Returns:
            List of strategy names (sorted)
        """
        return sorted(cls._STRATEGY_CLASSES.keys())

    @classmethod
    def get_all_metadata(cls) -> Dict[str, Dict[str, Any]]:
        """
        Get metadata for all strategies (for Admin UI).

        Returns:
            Dictionary mapping strategy names to metadata
        """
        return {
            name: cls.get_metadata_for_admin_ui(name)
            for name in cls.list_strategies()
        }


# Convenience function for backward compatibility
def validate_strategy_params(strategy_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate strategy parameters (convenience wrapper).

    Args:
        strategy_name: Name of strategy
        params: Parameters to validate

    Returns:
        Validated parameters
    """
    return StrategyRegistry.validate_params(strategy_name, params)
