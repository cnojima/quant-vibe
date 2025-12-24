"""Strategy loading and configuration for live trading.

Provides utilities to load and configure strategies from YAML configuration.
"""

import logging
from typing import List, Dict, Any, Optional

from ..strategies.options_base import OptionsStrategy
from ..strategies.bullish_vertical_put import BullishVerticalPutStrategy
from ..strategies.bullish_vertical_call import BullishVerticalCallStrategy

logger = logging.getLogger(__name__)


class StrategyLoader:
    """Loads and configures strategies from configuration."""

    # Map of strategy names to classes
    STRATEGY_REGISTRY = {
        'bullish_vertical_put': BullishVerticalPutStrategy,
        'bullish_vertical_call': BullishVerticalCallStrategy,
    }

    @classmethod
    def load_strategies(cls, config: Dict[str, Any]) -> List[OptionsStrategy]:
        """
        Load strategies from configuration.

        Args:
            config: Configuration dictionary with 'strategies' section

        Returns:
            List of initialized strategy instances

        Example config:
            strategies:
              enabled:
                - name: bullish_vertical_put
                  enabled: true
                  params:
                    spread_width: 10
                    observation_period: 30
                    profit_target_min: 0.5
        """
        strategies = []

        # Get strategies section
        strategies_config = config.get('strategies', {})
        enabled_strategies = strategies_config.get('enabled', [])

        if not enabled_strategies:
            logger.warning("No strategies configured")
            return strategies

        # Load each strategy
        for strategy_config in enabled_strategies:
            try:
                strategy = cls._load_strategy(strategy_config)
                if strategy:
                    strategies.append(strategy)
            except Exception as e:
                strategy_name = strategy_config.get('name', 'unknown')
                logger.error(f"Failed to load strategy {strategy_name}: {e}", exc_info=True)

        logger.info(f"Loaded {len(strategies)} strategies")
        return strategies

    @classmethod
    def _load_strategy(cls, strategy_config: Dict[str, Any]) -> Optional[OptionsStrategy]:
        """
        Load a single strategy from configuration.

        Args:
            strategy_config: Strategy configuration dictionary

        Returns:
            Initialized strategy instance or None
        """
        # Get strategy name
        strategy_name = strategy_config.get('name')
        if not strategy_name:
            logger.error("Strategy configuration missing 'name' field")
            return None

        # Check if enabled
        if not strategy_config.get('enabled', True):
            logger.info(f"Strategy {strategy_name} is disabled, skipping")
            return None

        # Get strategy class
        strategy_class = cls.STRATEGY_REGISTRY.get(strategy_name)
        if not strategy_class:
            logger.error(
                f"Unknown strategy: {strategy_name}. "
                f"Available: {list(cls.STRATEGY_REGISTRY.keys())}"
            )
            return None

        # Get parameters
        params = strategy_config.get('params', {})

        # Instantiate strategy
        try:
            strategy = strategy_class(**params)
            logger.info(f"Loaded strategy: {strategy.name} with params: {params}")
            return strategy
        except Exception as e:
            logger.error(f"Failed to instantiate {strategy_name}: {e}", exc_info=True)
            return None

    @classmethod
    def register_strategy(cls, name: str, strategy_class: type):
        """
        Register a new strategy class.

        Args:
            name: Strategy name for configuration
            strategy_class: Strategy class (must inherit from OptionsStrategy)
        """
        if not issubclass(strategy_class, OptionsStrategy):
            raise ValueError(f"{strategy_class} must inherit from OptionsStrategy")

        cls.STRATEGY_REGISTRY[name] = strategy_class
        logger.info(f"Registered strategy: {name} -> {strategy_class.__name__}")

    @classmethod
    def list_available_strategies(cls) -> List[str]:
        """
        Get list of available strategy names.

        Returns:
            List of strategy names
        """
        return list(cls.STRATEGY_REGISTRY.keys())
