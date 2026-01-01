"""
Strategy parameter models using Pydantic.

Each strategy should define its own parameter model that inherits from BaseStrategyParams.
This provides type safety, validation, and clear documentation of parameters.
"""

from typing import Optional
from pydantic import BaseModel, Field


class BaseStrategyParams(BaseModel):
    """Base parameters common to all strategies."""

    min_dte: int = Field(
        default=0,
        ge=0,
        le=365,
        description="Minimum days to expiration"
    )
    max_dte: int = Field(
        default=45,
        ge=0,
        le=365,
        description="Maximum days to expiration"
    )
    max_trades_daily: int = Field(
        default=1,
        ge=0,
        le=999,
        description="Maximum trades per day (0=no trades, 999=unlimited)"
    )

    class Config:
        extra = "ignore"  # Ignore unknown parameters (don't pass to strategy)


class BullishVerticalPutParams(BaseStrategyParams):
    """Parameters for Bullish Vertical Put strategy."""

    spread_width: float = Field(
        default=20.0,
        ge=1.0,
        le=200.0,
        description="Width of the vertical spread in points"
    )
    observation_period: int = Field(
        default=30,
        ge=1,
        le=1440,
        description="Minutes to observe market at open"
    )
    pullback_amount: float = Field(
        default=50.0,
        ge=0.0,
        le=500.0,
        description="Dollar amount for pullback signal"
    )
    profit_target_min: float = Field(
        default=0.5,
        ge=0.0,
        le=10.0,
        description="Minimum profit target (0.5 = 50%)"
    )
    profit_target_max: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Maximum profit target (1.0 = 100%)"
    )
    trailing_stop_pct: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Trailing stop percentage (0.05 = 5%)"
    )
    num_spreads: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of spreads to open per signal"
    )
    min_volume: int = Field(
        default=50,
        ge=0,
        le=100000,
        description="Minimum volume per contract for liquidity"
    )
    min_bid_ask_spread_pct: float = Field(
        default=10.0,
        ge=0.0,
        le=100.0,
        description="Maximum bid/ask spread percentage"
    )


class BullishVerticalCallParams(BaseStrategyParams):
    """Parameters for Bullish Vertical Call strategy."""

    spread_width: float = Field(
        default=20.0,
        ge=1.0,
        le=200.0,
        description="Width of the vertical spread in points"
    )
    observation_period: int = Field(
        default=30,
        ge=1,
        le=1440,
        description="Minutes to observe market at open"
    )
    pullback_amount: float = Field(
        default=50.0,
        ge=0.0,
        le=500.0,
        description="Dollar amount for pullback signal"
    )
    profit_target_min: float = Field(
        default=0.5,
        ge=0.0,
        le=10.0,
        description="Minimum profit target (0.5 = 50%)"
    )
    profit_target_max: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Maximum profit target (1.0 = 100%)"
    )
    trailing_stop_pct: float = Field(
        default=0.05,
        ge=0.0,
        le=1.0,
        description="Trailing stop percentage (0.05 = 5%)"
    )
    num_spreads: int = Field(
        default=10,
        ge=1,
        le=100,
        description="Number of spreads to open per signal"
    )


class BearishIVScalpParams(BaseStrategyParams):
    """Parameters for Bearish IV Scalp strategy."""

    spread_width: float = Field(
        default=10.0,
        ge=1.0,
        le=200.0,
        description="Width of the vertical spread in points"
    )
    observation_period: int = Field(
        default=15,
        ge=1,
        le=1440,
        description="Minutes to observe market"
    )
    iv_threshold: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="IV threshold for entry"
    )
    iv_spike_pct: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="IV spike percentage"
    )
    profit_target_min: float = Field(
        default=0.3,
        ge=0.0,
        le=10.0,
        description="Minimum profit target"
    )
    profit_target_max: float = Field(
        default=0.5,
        ge=0.0,
        le=10.0,
        description="Maximum profit target"
    )
    trailing_stop_pct: float = Field(
        default=0.03,
        ge=0.0,
        le=1.0,
        description="Trailing stop percentage"
    )
    stop_loss_pct: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Stop loss percentage"
    )
    num_spreads: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Number of spreads to open"
    )
    min_volume: int = Field(
        default=20,
        ge=0,
        le=100000,
        description="Minimum volume per contract"
    )
    min_bid_ask_spread_pct: float = Field(
        default=15.0,
        ge=0.0,
        le=100.0,
        description="Maximum bid/ask spread percentage"
    )
    momentum_lookback: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Momentum lookback period in minutes"
    )
    iv_lookback: int = Field(
        default=30,
        ge=1,
        le=1000,
        description="IV lookback period in minutes"
    )


class CoinTossParams(BaseStrategyParams):
    """Parameters for Coin Toss strategy."""

    target_price: float = Field(
        default=2.0,
        ge=0.0,
        description="Target contract price"
    )
    buy_limit: float = Field(
        default=1.0,
        ge=0.0,
        description="Buy limit price"
    )
    sell_target: float = Field(
        default=2.0,
        ge=0.0,
        description="Sell target price"
    )
    price_tolerance: float = Field(
        default=0.5,
        ge=0.0,
        description="Price tolerance"
    )
    quantity: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Contract quantity"
    )
    profit_target_pct: float = Field(
        default=1.0,
        ge=0.0,
        le=10.0,
        description="Profit target percentage"
    )
    stop_loss_pct: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Stop loss percentage (optional)"
    )


class CoinTossLimitParams(BaseStrategyParams):
    """Parameters for Coin Toss Limit strategy."""

    target_contract_price: float = Field(
        default=2.0,
        ge=0.0,
        description="Target contract price"
    )
    limit_buy_price: float = Field(
        default=1.0,
        ge=0.0,
        description="Limit buy price"
    )
    profit_target_price: float = Field(
        default=2.0,
        ge=0.0,
        description="Profit target price"
    )
    otm_percent_min: float = Field(
        default=0.1,
        ge=0.0,
        le=1.0,
        description="Minimum OTM percentage"
    )
    otm_percent_max: float = Field(
        default=0.15,
        ge=0.0,
        le=1.0,
        description="Maximum OTM percentage"
    )
    price_tolerance: float = Field(
        default=1.0,
        ge=0.0,
        description="Price tolerance"
    )
    quantity: int = Field(
        default=10,
        ge=1,
        le=1000,
        description="Contract quantity"
    )
    stop_loss_pct: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Stop loss percentage"
    )
    order_expiry_minutes: int = Field(
        default=60,
        ge=1,
        le=1440,
        description="Order expiry in minutes"
    )


# Registry mapping strategy names to their parameter models
STRATEGY_PARAMS_MAP = {
    'bullish_vertical_put': BullishVerticalPutParams,
    'bullish_vertical_call': BullishVerticalCallParams,
    'bearish_iv_scalp': BearishIVScalpParams,
    'coin_toss': CoinTossParams,
    'coin_toss_limit': CoinTossLimitParams,
}


def get_strategy_params_model(strategy_name: str):
    """
    Get the parameter model class for a strategy.

    Args:
        strategy_name: Name of the strategy

    Returns:
        Pydantic model class for the strategy's parameters

    Raises:
        ValueError: If strategy name is unknown
    """
    if strategy_name not in STRATEGY_PARAMS_MAP:
        raise ValueError(
            f"Unknown strategy: {strategy_name}\n"
            f"Available strategies: {list(STRATEGY_PARAMS_MAP.keys())}"
        )
    return STRATEGY_PARAMS_MAP[strategy_name]


def validate_and_normalize_params(strategy_name: str, params: dict) -> dict:
    """
    Validate and normalize strategy parameters using Pydantic.

    Args:
        strategy_name: Name of the strategy
        params: Raw parameter dictionary

    Returns:
        Validated and normalized parameter dictionary

    Raises:
        ValueError: If parameters are invalid
    """
    params_model = get_strategy_params_model(strategy_name)
    validated = params_model(**params)
    return validated.model_dump()
