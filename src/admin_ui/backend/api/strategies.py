"""
Strategy management API endpoints.

Provides endpoints to list, enable, disable, and configure trading strategies.

Now auto-generates metadata from central StrategyRegistry - no more manual duplication!
"""

from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from admin_ui.backend.api.config import load_yaml_config, save_yaml_config
from admin_ui.backend.auth import User, get_current_user

# Import central registry
from quant_vibe.strategies.registry import StrategyRegistry
from quant_vibe.utils import now_utc

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


# AUTO-GENERATED from StrategyRegistry (single source of truth)
# This replaces the manual STRATEGY_METADATA dictionary
def get_strategy_metadata() -> dict[str, dict[str, Any]]:
    """
    Get strategy metadata from central registry.

    Returns:
        Dictionary mapping strategy names to metadata

    Note: This auto-generates from Pydantic models, so no manual updates needed!
    """
    return StrategyRegistry.get_all_metadata()


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
    strategy_metadata = get_strategy_metadata()
    for name, metadata in strategy_metadata.items():
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
    strategy_metadata = get_strategy_metadata()
    if strategy_name not in strategy_metadata:
        raise HTTPException(
            status_code=404,
            detail=f"Strategy '{strategy_name}' not found. Available: {list(strategy_metadata.keys())}",
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

    metadata = strategy_metadata[strategy_name]

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
    strategy_metadata = get_strategy_metadata()
    if strategy_name not in strategy_metadata:
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
            metadata = strategy_metadata[strategy_name]
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

    # Trigger hot-reload
    try:
        from quant_vibe.messaging import RedisMessageBroker
        from datetime import datetime

        broker = RedisMessageBroker()
        broker.publish(
            topic="control.live_trading",
            data={
                "command": "reload_strategies",
                "timestamp": now_utc().isoformat(),
                "trigger": "strategy_toggle",
                "strategy": strategy_name,
            }
        )
        broker.close()

        return {
            "success": True,
            "message": f"Strategy '{strategy_name}' {'enabled' if toggle.enabled else 'disabled'}. Live engine will reload automatically.",
            "requires_restart": False,
            "auto_reload": True,
        }
    except Exception as e:
        # If hot-reload fails, still return success but indicate restart needed
        return {
            "success": True,
            "message": f"Strategy '{strategy_name}' {'enabled' if toggle.enabled else 'disabled'}",
            "requires_restart": True,
            "auto_reload": False,
            "reload_error": str(e),
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
    strategy_metadata = get_strategy_metadata()
    if strategy_name not in strategy_metadata:
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

    # Trigger hot-reload
    try:
        from quant_vibe.messaging import RedisMessageBroker
        from datetime import datetime

        broker = RedisMessageBroker()
        broker.publish(
            topic="control.live_trading",
            data={
                "command": "reload_strategies",
                "timestamp": now_utc().isoformat(),
                "trigger": "params_update",
                "strategy": strategy_name,
            }
        )
        broker.close()

        return {
            "success": True,
            "message": f"Parameters updated for strategy '{strategy_name}'. Live engine will reload automatically.",
            "requires_restart": False,
            "auto_reload": True,
        }
    except Exception as e:
        # If hot-reload fails, still return success but indicate restart needed
        return {
            "success": True,
            "message": f"Parameters updated for strategy '{strategy_name}'",
            "requires_restart": True,
            "auto_reload": False,
            "reload_error": str(e),
        }
