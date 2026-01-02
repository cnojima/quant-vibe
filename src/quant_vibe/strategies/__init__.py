"""Trading strategy implementations."""

from .base import Strategy, Signal
from .sma_crossover import SMACrossoverStrategy
from .sma_crossover_delayed import SMACrossoverDelayedStrategy
from .rsi_strategy import RSIStrategy
from .ema_crossover import EMACrossoverStrategy
from .macd_crossover import MACDCrossoverStrategy
from .macd_histogram import MACDHistogramStrategy
from .rsi_ma_filter import RSIMAFilterStrategy
from .triple_ma import TripleMAStrategy
from .multi_rsi import MultiRSIStrategy
from .rsi_macd_confirmation import RSIMACDConfirmationStrategy
from .bearish_iv_scalp import BearishIVScalpStrategy
from .coin_toss import CoinTossStrategy
from .coin_toss_limit import CoinTossLimitStrategy
from .bollinger_band import BollingerBandStrategy
from .bollinger_band_limit import BollingerBandLimitStrategy
from .naive_bullish_put import NaiveBullishPutStrategy

# Central registry for all strategies (single source of truth)
from .registry import StrategyRegistry, validate_strategy_params

__all__ = [
    "Strategy",
    "Signal",
    "SMACrossoverStrategy",
    "SMACrossoverDelayedStrategy",
    "RSIStrategy",
    "EMACrossoverStrategy",
    "MACDCrossoverStrategy",
    "MACDHistogramStrategy",
    "RSIMAFilterStrategy",
    "TripleMAStrategy",
    "MultiRSIStrategy",
    "RSIMACDConfirmationStrategy",
    "BearishIVScalpStrategy",
    "CoinTossStrategy",
    "CoinTossLimitStrategy",
    "BollingerBandStrategy",
    "BollingerBandLimitStrategy",
    "NaiveBullishPutStrategy",
    "StrategyRegistry",
    "validate_strategy_params",
]
