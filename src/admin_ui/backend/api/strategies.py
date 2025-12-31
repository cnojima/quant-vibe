"""
Strategy management API endpoints.

Provides endpoints to list, enable, disable, and configure trading strategies.
"""

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin_ui.backend.api.config import load_yaml_config, save_yaml_config
from admin_ui.backend.auth import User, get_current_user

router = APIRouter()


class StrategyInfo(BaseModel):
    """Information about an available strategy."""

    name: str
    enabled: bool
    description: str
    params: dict[str, Any]


class StrategyToggle(BaseModel):
    """Request to enable/disable a strategy."""

    enabled: bool


class StrategyUpdate(BaseModel):
    """Request to update strategy parameters."""

    params: dict[str, Any]


# Strategy metadata (descriptions and default params)
STRATEGY_METADATA = {
    "bullish_vertical_put": {
        "description": "Credit spread strategy (sell put, buy lower put) for bullish markets",
        "default_params": {
            "max_trades_daily": 1,
            "spread_width": 10.0,
            "observation_period": 30,
            "pullback_amount": 50.0,
            "profit_target_min": 0.5,
            "profit_target_max": 1.0,
            "trailing_stop_pct": 0.05,
            "min_dte": 0,
            "max_dte": 45,
            "num_spreads": 10,
            "min_volume": 50,
            "min_bid_ask_spread_pct": 10.0,
        },
    },
    "bullish_vertical_call": {
        "description": "Debit spread strategy (buy call, sell higher call) for bullish markets",
        "default_params": {
            "max_trades_daily": 1,
            "spread_width": 20.0,
            "observation_period": 30,
            "pullback_amount": 50.0,
            "profit_target_min": 0.5,
            "profit_target_max": 1.0,
            "trailing_stop_pct": 0.05,
            "min_dte": 7,
            "max_dte": 45,
            "num_spreads": 10,
        },
    },
    "bearish_iv_scalp": {
        "description": "Credit spread strategy (sell call, buy higher call) targeting IV spikes during bearish moves (0DTE scalping)",
        "default_params": {
            "spread_width": 10.0,
            "observation_period": 15,
            "iv_threshold": 0.15,
            "iv_spike_pct": 0.10,
            "profit_target_min": 0.30,
            "profit_target_max": 0.50,
            "trailing_stop_pct": 0.03,
            "stop_loss_pct": 0.75,
            "min_dte": 0,
            "max_dte": 0,
            "num_spreads": 5,
            "min_volume": 20,
            "min_bid_ask_spread_pct": 15.0,
            "max_trades_daily": 2,
            "momentum_lookback": 5,
            "iv_lookback": 30,
        },
    },
    "coin_toss": {
        "description": "Naive strategy that randomly picks direction and buys 10 contracts near $2, sells at $2 (educational/experimental only)",
        "default_params": {
            "target_price": 2.0,
            "buy_limit": 1.0,
            "sell_target": 2.0,
            "price_tolerance": 0.50,
            "max_trades_daily": 5,
            "quantity": 10,
            "min_dte": 0,
            "max_dte": 45,
            "profit_target_pct": 1.0,
            "stop_loss_pct": None,
        },
    },
}


@router.get("/list")
async def list_strategies(current_user: User = Depends(get_current_user)):
    """
    List all available strategies and their current status.

    Args:
        current_user: Authenticated user

    Returns:
        List of strategies with their enabled status and configuration
    """
    # Load live trading config
    config = load_yaml_config("live_trading")

    # Get enabled strategies from config
    strategies_config = config.get("strategies", {})
    enabled_strategies = strategies_config.get("enabled", [])

    # Create a map of strategy name -> config
    enabled_map = {}
    for strategy_config in enabled_strategies:
        if isinstance(strategy_config, dict):
            name = strategy_config.get("name")
            if name:
                enabled_map[name] = strategy_config

    # Build list of all available strategies
    strategies = []
    for name, metadata in STRATEGY_METADATA.items():
        strategy_config = enabled_map.get(name)

        if strategy_config:
            # Strategy is enabled in config
            strategies.append(
                {
                    "name": name,
                    "enabled": strategy_config.get("enabled", True),
                    "description": metadata["description"],
                    "params": strategy_config.get("params", metadata["default_params"]),
                }
            )
        else:
            # Strategy is not in config (disabled)
            strategies.append(
                {
                    "name": name,
                    "enabled": False,
                    "description": metadata["description"],
                    "params": metadata["default_params"],
                }
            )

    return {
        "strategies": strategies,
        "count": len(strategies),
    }


@router.get("/{strategy_name}")
async def get_strategy(
    strategy_name: str, current_user: User = Depends(get_current_user)
):
    """
    Get details for a specific strategy.

    Args:
        strategy_name: Name of the strategy
        current_user: Authenticated user

    Returns:
        Strategy details
    """
    if strategy_name not in STRATEGY_METADATA:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{strategy_name}' not found. Available: {list(STRATEGY_METADATA.keys())}",
        )

    # Load config
    config = load_yaml_config("live_trading")
    strategies_config = config.get("strategies", {})
    enabled_strategies = strategies_config.get("enabled", [])

    # Find strategy in config
    strategy_config = None
    for s in enabled_strategies:
        if isinstance(s, dict) and s.get("name") == strategy_name:
            strategy_config = s
            break

    metadata = STRATEGY_METADATA[strategy_name]

    if strategy_config:
        return {
            "name": strategy_name,
            "enabled": strategy_config.get("enabled", True),
            "description": metadata["description"],
            "params": strategy_config.get("params", metadata["default_params"]),
        }
    else:
        return {
            "name": strategy_name,
            "enabled": False,
            "description": metadata["description"],
            "params": metadata["default_params"],
        }


@router.post("/{strategy_name}/toggle")
async def toggle_strategy(
    strategy_name: str,
    toggle: StrategyToggle,
    current_user: User = Depends(get_current_user),
):
    """
    Enable or disable a strategy.

    Args:
        strategy_name: Name of the strategy
        toggle: Enable/disable request
        current_user: Authenticated user

    Returns:
        Success message
    """
    if strategy_name not in STRATEGY_METADATA:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{strategy_name}' not found",
        )

    # Load config
    config = load_yaml_config("live_trading")

    # Ensure strategies section exists
    if "strategies" not in config:
        config["strategies"] = {}
    if "enabled" not in config["strategies"]:
        config["strategies"]["enabled"] = []

    enabled_strategies = config["strategies"]["enabled"]

    # Find existing strategy
    existing_index = None
    for i, s in enumerate(enabled_strategies):
        if isinstance(s, dict) and s.get("name") == strategy_name:
            existing_index = i
            break

    if toggle.enabled:
        # Enable strategy
        if existing_index is not None:
            # Already exists, just set enabled flag
            enabled_strategies[existing_index]["enabled"] = True
        else:
            # Add new strategy with default params
            metadata = STRATEGY_METADATA[strategy_name]
            enabled_strategies.append(
                {
                    "name": strategy_name,
                    "enabled": True,
                    "params": metadata["default_params"],
                }
            )
    else:
        # Disable strategy
        if existing_index is not None:
            # Set enabled flag to false (keep in config for params)
            enabled_strategies[existing_index]["enabled"] = False
        # If not in config, already disabled - no action needed

    # Save config
    save_yaml_config("live_trading", config)

    return {
        "success": True,
        "message": f"Strategy '{strategy_name}' {'enabled' if toggle.enabled else 'disabled'}",
        "requires_restart": True,
    }


@router.put("/{strategy_name}/params")
async def update_strategy_params(
    strategy_name: str,
    update: StrategyUpdate,
    current_user: User = Depends(get_current_user),
):
    """
    Update parameters for a strategy.

    Args:
        strategy_name: Name of the strategy
        update: New parameters
        current_user: Authenticated user

    Returns:
        Success message
    """
    if strategy_name not in STRATEGY_METADATA:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{strategy_name}' not found",
        )

    # Load config
    config = load_yaml_config("live_trading")

    # Ensure strategies section exists
    if "strategies" not in config:
        config["strategies"] = {}
    if "enabled" not in config["strategies"]:
        config["strategies"]["enabled"] = []

    enabled_strategies = config["strategies"]["enabled"]

    # Find existing strategy
    existing_index = None
    for i, s in enumerate(enabled_strategies):
        if isinstance(s, dict) and s.get("name") == strategy_name:
            existing_index = i
            break

    if existing_index is not None:
        # Update existing strategy params
        enabled_strategies[existing_index]["params"] = update.params
    else:
        # Create new strategy entry with params
        enabled_strategies.append(
            {
                "name": strategy_name,
                "enabled": False,  # Don't auto-enable
                "params": update.params,
            }
        )

    # Save config
    save_yaml_config("live_trading", config)

    return {
        "success": True,
        "message": f"Parameters updated for strategy '{strategy_name}'",
        "requires_restart": True,
    }
