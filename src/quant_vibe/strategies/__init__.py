"""Trading strategy implementations."""

from .base import Strategy, Signal
from .bearish_iv_scalp import BearishIVScalpStrategy
from .coin_toss import CoinTossStrategy
from .coin_toss_limit import CoinTossLimitStrategy
from .bollinger_band import BollingerBandStrategy
from .bollinger_band_limit import BollingerBandLimitStrategy
from .naive_bullish_put import NaiveBullishPutStrategy
from .hail_mary import HailMaryStrategy

# Central registry for all strategies (single source of truth)
from .registry import StrategyRegistry, validate_strategy_params

__all__ = [
    "Strategy",
    "Signal",
    "BearishIVScalpStrategy",
    "CoinTossStrategy",
    "CoinTossLimitStrategy",
    "BollingerBandStrategy",
    "BollingerBandLimitStrategy",
    "NaiveBullishPutStrategy",
    "HailMaryStrategy",
    "StrategyRegistry",
    "validate_strategy_params",
]
