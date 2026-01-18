"""Strategy loading and configuration for live trading."""

from typing import List, Dict, Any, Optional

from quant_vibe.logging import get_logger
from quant_vibe.strategies.options_base import OptionsStrategy
from quant_vibe.strategies.registry import StrategyRegistry

logger = get_logger('live_trading')


class StrategyLoader:
    """Loads and configures strategies from configuration."""

    @classmethod
    def load_strategies(cls, config: Dict[str, Any]) -> List[OptionsStrategy]:
        """Load strategies from configuration.

        Args:
            config: Configuration dictionary with 'strategies' section

        Returns:
            List of initialized strategy instances
        """
        strategies = []
        strategies_config = config.get('strategies', {})
        enabled_strategies = strategies_config.get('enabled', [])

        if not enabled_strategies:
            logger.warning("No strategies configured")
            return strategies

        for i, strategy_config in enumerate(enabled_strategies):
            if not cls._validate_config(strategy_config, i):
                continue

            strategy = cls._load_strategy(strategy_config)
            if strategy:
                strategies.append(strategy)

        logger.info(f"Loaded {len(strategies)} strategies")
        return strategies

    @classmethod
    def _validate_config(cls, strategy_config: Any, index: int) -> bool:
        """Validate strategy configuration format."""
        if isinstance(strategy_config, str):
            logger.error(
                f"Strategy config at index {index} is a string: '{strategy_config}'. "
                "Expected a dictionary with 'name', 'enabled', and 'params' fields."
            )
            return False

        if not isinstance(strategy_config, dict):
            logger.error(
                f"Strategy config at index {index} has invalid type: {type(strategy_config)}. "
                "Expected a dictionary."
            )
            return False

        return True

    @classmethod
    def _load_strategy(cls, strategy_config: Dict[str, Any]) -> Optional[OptionsStrategy]:
        """Load a single strategy from configuration."""
        strategy_name = strategy_config.get('name')
        if not strategy_name:
            logger.error("Strategy configuration missing 'name' field")
            return None

        if not strategy_config.get('enabled', True):
            logger.info(f"Strategy {strategy_name} is disabled, skipping")
            return None

        params = strategy_config.get('params', {})

        try:
            strategy = StrategyRegistry.create_strategy(
                strategy_name=strategy_name,
                params=params,
                validate=True
            )
            logger.info(f"Loaded strategy: {strategy.name} with params: {params}")
            return strategy
        except ValueError as e:
            logger.error(f"Parameter validation failed for {strategy_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to instantiate {strategy_name}: {e}")
            return None

    @classmethod
    def list_available_strategies(cls) -> List[str]:
        """Get list of available strategy names."""
        return StrategyRegistry.list_strategies()