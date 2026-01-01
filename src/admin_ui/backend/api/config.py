"""
Configuration management API endpoints.

Provides endpoints to read and update YAML configuration files.
"""

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError

from admin_ui.backend.auth import User, get_current_user
from admin_ui.backend.config import get_settings
from admin_ui.backend.schemas.config_schemas import (
    BacktestConfig,
    LiveTradingConfig,
    get_backtest_json_schema,
    get_live_trading_json_schema,
)

router = APIRouter()


class ConfigUpdate(BaseModel):
    """Configuration update request."""

    config: dict[str, Any]


def load_yaml_config(config_name: str) -> dict[str, Any]:
    """
    Load a YAML configuration file.

    Args:
        config_name: Name of config file (without .yaml extension)

    Returns:
        Configuration dictionary

    Raises:
        HTTPException: If file not found or invalid
    """
    settings = get_settings()
    config_path = settings.config_dir / f"{config_name}.yaml"

    if not config_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Configuration file '{config_name}.yaml' not found"
        )

    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to load configuration: {str(e)}"
        )


def save_yaml_config(config_name: str, config: dict[str, Any]) -> None:
    """
    Save a YAML configuration file.

    Args:
        config_name: Name of config file (without .yaml extension)
        config: Configuration dictionary to save

    Raises:
        HTTPException: If save fails
    """
    settings = get_settings()
    config_path = settings.config_dir / f"{config_name}.yaml"

    try:
        # Create backup first
        if config_path.exists():
            backup_path = config_path.with_suffix(f".yaml.backup")
            config_path.rename(backup_path)

        # Write new config
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save configuration: {str(e)}"
        )


@router.get("/backtest")
async def get_backtest_config(current_user: User = Depends(get_current_user)):
    """
    Get backtest configuration.

    Args:
        current_user: Authenticated user

    Returns:
        Backtest configuration
    """
    config = load_yaml_config("backtest")
    return {"config": config}


@router.put("/backtest")
async def update_backtest_config(
    update: ConfigUpdate,
    current_user: User = Depends(get_current_user),
):
    """
    Update backtest configuration.

    Args:
        update: New configuration
        current_user: Authenticated user

    Returns:
        Success message

    Raises:
        HTTPException: If validation fails
    """
    # Validate config using Pydantic schema
    try:
        BacktestConfig(**update.config)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Configuration validation failed",
                "errors": e.errors(),
            }
        )

    save_yaml_config("backtest", update.config)

    return {
        "success": True,
        "message": "Backtest configuration updated successfully",
    }


@router.get("/live")
async def get_live_config(current_user: User = Depends(get_current_user)):
    """
    Get live trading configuration.

    Args:
        current_user: Authenticated user

    Returns:
        Live trading configuration
    """
    config = load_yaml_config("live_trading")
    return {"config": config}


@router.put("/live")
async def update_live_config(
    update: ConfigUpdate,
    current_user: User = Depends(get_current_user),
):
    """
    Update live trading configuration.

    Args:
        update: New configuration
        current_user: Authenticated user

    Returns:
        Success message

    Raises:
        HTTPException: If validation fails
    """
    # Validate config using Pydantic schema
    try:
        LiveTradingConfig(**update.config)
    except ValidationError as e:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Configuration validation failed",
                "errors": e.errors(),
            }
        )

    save_yaml_config("live_trading", update.config)

    return {
        "success": True,
        "message": "Live trading configuration updated successfully",
    }


@router.get("/list")
async def list_configs(current_user: User = Depends(get_current_user)):
    """
    List all available configuration files.

    Args:
        current_user: Authenticated user

    Returns:
        List of configuration files
    """
    settings = get_settings()

    config_files = list(settings.config_dir.glob("*.yaml"))

    configs = []
    for config_file in config_files:
        configs.append({
            "name": config_file.stem,
            "filename": config_file.name,
            "size_bytes": config_file.stat().st_size,
            "modified": config_file.stat().st_mtime,
        })

    return {
        "configs": configs,
        "count": len(configs),
    }


@router.get("/schema/backtest")
async def get_backtest_schema(current_user: User = Depends(get_current_user)):
    """
    Get JSON Schema for backtest configuration.

    Args:
        current_user: Authenticated user

    Returns:
        JSON Schema definition for backtest configuration
    """
    return {"schema": get_backtest_json_schema()}


@router.get("/schema/live")
async def get_live_schema(current_user: User = Depends(get_current_user)):
    """
    Get JSON Schema for live trading configuration.

    Args:
        current_user: Authenticated user

    Returns:
        JSON Schema definition for live trading configuration
    """
    return {"schema": get_live_trading_json_schema()}
