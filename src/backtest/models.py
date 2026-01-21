"""
Pydantic models for Backtest Service API.

These models define the request/response schemas for the backtest service.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, validator
from decimal import Decimal


class BacktestRequest(BaseModel):
    """Request model for creating a new backtest."""

    strategy_name: str = Field(..., description="Name of the strategy to backtest")
    start_date: datetime = Field(..., description="Start date for the backtest")
    end_date: datetime = Field(..., description="End date for the backtest")
    initial_capital: float = Field(..., gt=0, description="Initial capital for the backtest")
    params: Dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")
    ticker: str = Field(default="$SPX", description="Ticker symbol to trade")
    timeframe: str = Field(default="5min", description="Data timeframe (1min, 5min, etc.)")
    description: Optional[str] = Field(None, description="Optional description for the backtest")

    @validator("end_date")
    def validate_date_range(cls, v, values):
        """Ensure end_date is after start_date."""
        if "start_date" in values and v <= values["start_date"]:
            raise ValueError("end_date must be after start_date")
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v),
        }
        schema_extra = {
            "example": {
                "strategy_name": "bullish_vertical_put",
                "start_date": "2024-01-01T00:00:00",
                "end_date": "2024-12-31T23:59:59",
                "initial_capital": 100000.0,
                "params": {
                    "spread_width": 10.0,
                    "profit_target_min": 0.5,
                    "profit_target_max": 0.7,
                    "stop_loss": -2.0,
                    "min_dte": 0,
                    "max_dte": 45,
                },
                "ticker": "$SPX",
                "timeframe": "5min",
                "description": "Test backtest for bullish vertical put strategy",
            }
        }


class BacktestResponse(BaseModel):
    """Response model for backtest creation."""

    id: str = Field(..., description="Unique backtest ID")
    status: str = Field(..., description="Current status of the backtest")
    message: str = Field(..., description="Status message")
    created_at: datetime = Field(..., description="Timestamp when backtest was created")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class BacktestStatus(BaseModel):
    """Model for backtest status information."""

    id: str = Field(..., description="Unique backtest ID")
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = Field(
        ..., description="Current status"
    )
    progress: float = Field(..., ge=0, le=100, description="Progress percentage (0-100)")
    strategy_name: str = Field(..., description="Strategy being backtested")
    created_at: datetime = Field(..., description="Creation timestamp")
    started_at: Optional[datetime] = Field(None, description="Start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Completion timestamp")
    error: Optional[str] = Field(None, description="Error message if failed")
    eta: Optional[datetime] = Field(None, description="Estimated time of completion")
    current_step: Optional[str] = Field(None, description="Current processing step")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat() if v else None,
        }


class BacktestProgress(BaseModel):
    """Model for real-time progress updates."""

    backtest_id: str = Field(..., description="Backtest ID")
    status: str = Field(..., description="Current status")
    progress: float = Field(..., ge=0, le=100, description="Progress percentage")
    current_step: Optional[str] = Field(None, description="Current processing step")
    message: Optional[str] = Field(None, description="Progress message")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class BacktestResult(BaseModel):
    """Model for backtest results."""

    backtest_id: str = Field(..., description="Unique backtest ID")
    strategy_name: str = Field(..., description="Strategy name")
    start_date: datetime = Field(..., description="Backtest start date")
    end_date: datetime = Field(..., description="Backtest end date")
    initial_capital: float = Field(..., description="Initial capital")
    final_capital: float = Field(..., description="Final capital")
    total_return: float = Field(..., description="Total return percentage")
    sharpe_ratio: Optional[float] = Field(None, description="Sharpe ratio")
    max_drawdown: float = Field(..., description="Maximum drawdown percentage")
    win_rate: float = Field(..., description="Win rate percentage")
    total_trades: int = Field(..., description="Total number of trades")
    winning_trades: int = Field(..., description="Number of winning trades")
    losing_trades: int = Field(..., description="Number of losing trades")
    avg_win: float = Field(..., description="Average winning trade return")
    avg_loss: float = Field(..., description="Average losing trade return")
    profit_factor: Optional[float] = Field(None, description="Profit factor")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Additional metrics")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            Decimal: lambda v: float(v),
        }


class BacktestListResponse(BaseModel):
    """Response model for listing backtests."""

    backtests: List[BacktestStatus] = Field(..., description="List of backtests")
    total: int = Field(..., description="Total number of backtests")
    offset: int = Field(..., description="Current offset")
    limit: int = Field(..., description="Current limit")


class BacktestCancelRequest(BaseModel):
    """Request model for cancelling a backtest."""

    reason: Optional[str] = Field(None, description="Reason for cancellation")


class BacktestCancelResponse(BaseModel):
    """Response model for backtest cancellation."""

    success: bool = Field(..., description="Whether cancellation was successful")
    message: str = Field(..., description="Cancellation message")


class BacktestError(BaseModel):
    """Model for backtest errors."""

    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class WebSocketMessage(BaseModel):
    """Model for WebSocket messages."""

    type: Literal["progress", "status", "result", "error"] = Field(..., description="Message type")
    backtest_id: str = Field(..., description="Backtest ID")
    data: Dict[str, Any] = Field(..., description="Message data")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }