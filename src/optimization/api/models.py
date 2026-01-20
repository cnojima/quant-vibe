"""
Pydantic models for optimization API.
"""

from datetime import datetime
from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field


class OptimizationRequest(BaseModel):
    """Optimization execution request."""

    strategy_name: str = Field(..., description="Strategy name")
    train_start_date: datetime = Field(..., description="Training period start date")
    train_end_date: datetime = Field(..., description="Training period end date")
    test_start_date: Optional[datetime] = Field(None, description="Test period start date (for walk-forward)")
    test_end_date: Optional[datetime] = Field(None, description="Test period end date (for walk-forward)")
    initial_capital: float = Field(100000.0, description="Initial capital")
    optimization_type: str = Field("grid_search", description="Optimization type (grid_search or walk_forward)")
    param_grid: Optional[Dict[str, List[Any]]] = Field(None, description="Custom parameter grid")
    fixed_params: Optional[Dict[str, Any]] = Field(None, description="Fixed parameters")
    underlying_ticker: str = Field("SPX", description="Underlying ticker")
    timeframe: str = Field("5min", description="Time aggregation (1min, 5min, 15min, 1hour, daily)")


class OptimizationStatus(BaseModel):
    """Optimization execution status."""

    optimization_id: str
    status: str  # pending, running, completed, failed, cancelled
    progress_current: Optional[int] = 0
    progress_total: Optional[int] = 0
    progress_pct: Optional[float] = 0
    estimated_completion_time: Optional[datetime] = None
    current_params: Optional[Dict[str, Any]] = None
    current_metrics: Optional[Dict[str, float]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    strategy_name: Optional[str] = None
    optimization_type: Optional[str] = None
    total_combinations: Optional[int] = None
    best_params: Optional[Dict[str, Any]] = None
    best_sharpe_ratio: Optional[float] = None
    best_total_return: Optional[float] = None
    best_win_rate: Optional[float] = None


class OptimizationResult(BaseModel):
    """Optimization results."""

    optimization_id: str
    status: str
    strategy_name: str
    optimization_type: str
    total_combinations: int
    best_params: Optional[Dict[str, Any]] = None
    best_sharpe_ratio: Optional[float] = None
    best_total_return: Optional[float] = None
    best_win_rate: Optional[float] = None
    results: List[Dict[str, Any]]
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class ParamGridRequest(BaseModel):
    """Request to generate or validate parameter grid."""

    strategy_name: str
    custom_ranges: Optional[Dict[str, List[Any]]] = None
    optimize_only: Optional[List[str]] = None


class ParamGridValidationRequest(BaseModel):
    """Request to validate parameter grid."""

    strategy_name: str
    param_grid: Dict[str, List[Any]]
    max_combinations: int = 200


class ParamGridResponse(BaseModel):
    """Parameter grid response."""

    strategy_name: str
    param_grid: Dict[str, List[Any]]
    total_combinations: int


class ParamGridValidationResponse(BaseModel):
    """Parameter grid validation response."""

    valid: bool
    total_combinations: int
    warnings: List[str]
    errors: List[str]


class FixedParamsResponse(BaseModel):
    """Fixed parameters response."""

    strategy_name: str
    fixed_params: Dict[str, Any]


class CacheStatusResponse(BaseModel):
    """Cache status response."""

    cache_key: str
    underlying_ticker: str
    start_date: datetime
    end_date: datetime
    timeframe: str
    num_options_rows: int
    num_underlying_rows: int
    data_size_mb: float
    hit_count: int
    last_accessed_at: datetime


class QueueStatusResponse(BaseModel):
    """Queue status response."""

    queue_size: int
    worker_active: bool
    message: str


class CacheClearResponse(BaseModel):
    """Cache clear response."""

    message: str
    deleted_count: int