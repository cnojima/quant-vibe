"""
Pydantic models for backtest analysis results.

These models define the structure for storing and exchanging analysis data
between the analyzer engine, database, and API endpoints.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from quant_vibe.utils import ensure_utc_aware


class GreeksAnalysis(BaseModel):
    """Analysis of how option Greeks contributed to trade P&L."""

    dominant_factor: str = Field(
        ..., description="Primary Greek driving P&L (e.g., 'delta', 'theta', 'vega')"
    )
    delta_contribution: float = Field(
        ..., description="Proportion of P&L attributable to delta (0.0 to 1.0)"
    )
    theta_contribution: float = Field(
        ..., description="Proportion of P&L attributable to theta (0.0 to 1.0)"
    )
    vega_contribution: float = Field(
        ..., description="Proportion of P&L attributable to vega (0.0 to 1.0)"
    )
    gamma_contribution: float = Field(
        ..., description="Proportion of P&L attributable to gamma (0.0 to 1.0)"
    )
    entry_delta: Optional[float] = Field(
        None, description="Position delta at entry"
    )
    exit_delta: Optional[float] = Field(
        None, description="Position delta at exit"
    )
    theta_decay_total: Optional[float] = Field(
        None, description="Total theta decay over holding period ($)"
    )


class MarketConditions(BaseModel):
    """Analysis of market conditions during the trade."""

    underlying_move_pct: float = Field(
        ..., description="Percentage move in underlying during trade"
    )
    underlying_move_direction: Literal["up", "down", "flat"] = Field(
        ..., description="Direction of underlying movement"
    )
    volatility_change_pct: Optional[float] = Field(
        None, description="Change in implied volatility during trade (%)"
    )
    market_regime: Literal["trending_up", "trending_down", "choppy", "volatile_spike"] = Field(
        ..., description="Market regime classification"
    )
    intraday_range_pct: Optional[float] = Field(
        None, description="Intraday price range as % of entry price"
    )


class StrategyAdherence(BaseModel):
    """Analysis of strategy rule compliance."""

    within_all_rules: bool = Field(
        ..., description="True if trade followed all strategy rules"
    )
    rule_violations: List[str] = Field(
        default_factory=list, description="List of rules that were violated or at edge"
    )
    edge_case_flags: List[str] = Field(
        default_factory=list, description="Parameters that were at boundary conditions"
    )
    entry_quality_score: float = Field(
        ..., ge=0.0, le=1.0, description="Overall entry quality (0=poor, 1=excellent)"
    )


class ExitTiming(BaseModel):
    """Analysis of exit timing and effectiveness."""

    exit_reason: str = Field(..., description="Reason for exit (e.g., 'profit_target', 'stop_loss')")
    held_pct_of_max_duration: float = Field(
        ..., ge=0.0, le=1.0, description="Percentage of maximum holding period used"
    )
    was_optimal: bool = Field(
        ..., description="True if exit captured most of available profit"
    )
    profit_captured_pct: Optional[float] = Field(
        None, description="Percentage of peak profit that was captured at exit"
    )
    could_have_exited_better: bool = Field(
        ..., description="True if better exit point existed"
    )
    timing_notes: Optional[str] = Field(
        None, description="Additional notes on exit timing"
    )


class MacroEvent(BaseModel):
    """Major market event that may have influenced trade."""

    event_type: str = Field(..., description="Type of event (e.g., 'FOMC', 'CPI', 'earnings')")
    event_date: datetime = Field(..., description="Date/time of event")
    description: str = Field(..., description="Event description")
    proximity_to_trade: str = Field(
        ..., description="How close event was to trade (e.g., 'during', 'day_before')"
    )
    likely_impact: Literal["high", "medium", "low"] = Field(
        ..., description="Estimated impact on trade outcome"
    )

    @field_validator("event_date")
    @classmethod
    def validate_event_date(cls, v: datetime) -> datetime:
        """Ensure event_date is UTC-aware."""
        return ensure_utc_aware(v)


class TradeInsights(BaseModel):
    """Detailed insights for a single outlier trade."""

    greeks: GreeksAnalysis
    market_conditions: MarketConditions
    strategy_adherence: StrategyAdherence
    exit_timing: ExitTiming
    macro_events: List[MacroEvent] = Field(default_factory=list)


class TradeInsight(BaseModel):
    """Complete analysis of an outlier trade (big winner or loser)."""

    trade_id: str = Field(..., description="Unique trade identifier")
    pnl: float = Field(..., description="Trade profit/loss in dollars")
    pnl_pct: float = Field(..., description="Trade profit/loss as percentage")
    std_devs_from_mean: float = Field(
        ..., description="Number of standard deviations from mean P&L"
    )
    insights: TradeInsights = Field(..., description="Detailed analysis insights")
    generalization_potential: Literal["high", "medium", "low"] = Field(
        ..., description="Likelihood that pattern can be generalized to strategy rules"
    )
    key_takeaway: str = Field(
        ..., description="One-sentence summary of main insight"
    )


class EntryTimingPattern(BaseModel):
    """Pattern analysis for entry timing."""

    best_hour: int = Field(..., ge=0, le=23, description="Hour with best average P&L")
    worst_hour: int = Field(..., ge=0, le=23, description="Hour with worst average P&L")
    hourly_stats: Dict[int, Dict[str, float]] = Field(
        ..., description="Stats by hour: {hour: {avg_pnl, win_rate, count}}"
    )


class ExitReasonPattern(BaseModel):
    """Pattern analysis for exit reasons."""

    profit_target_win_rate: float = Field(..., ge=0.0, le=1.0)
    stop_loss_win_rate: float = Field(..., ge=0.0, le=1.0)
    expiration_win_rate: float = Field(..., ge=0.0, le=1.0)
    trailing_stop_win_rate: float = Field(..., ge=0.0, le=1.0)
    exit_reason_counts: Dict[str, int] = Field(
        ..., description="Count of trades by exit reason"
    )
    exit_reason_avg_pnl: Dict[str, float] = Field(
        ..., description="Average P&L by exit reason"
    )


class DTEPerformance(BaseModel):
    """Pattern analysis for days-to-expiration performance."""

    dte_buckets: Dict[str, Dict[str, float]] = Field(
        ...,
        description="Stats by DTE range: {dte_range: {avg_pnl, win_rate, count}}",
    )
    optimal_dte_range: str = Field(
        ..., description="DTE range with best risk-adjusted performance"
    )


class StrikeSelectionPattern(BaseModel):
    """Pattern analysis for strike selection."""

    otm_pct_buckets: Dict[str, Dict[str, float]] = Field(
        ...,
        description="Stats by OTM %: {otm_range: {avg_pnl, win_rate, count}}",
    )
    optimal_otm_pct: float = Field(
        ..., description="OTM % with best performance"
    )


class Patterns(BaseModel):
    """Aggregated patterns across all trades."""

    entry_timing: Optional[EntryTimingPattern] = None
    exit_reasons: Optional[ExitReasonPattern] = None
    dte_performance: Optional[DTEPerformance] = None
    strike_selection: Optional[StrikeSelectionPattern] = None
    additional_patterns: Dict[str, Any] = Field(
        default_factory=dict, description="Additional custom patterns"
    )


class AnalysisFindings(BaseModel):
    """Complete findings from backtest analysis."""

    big_winners: List[TradeInsight] = Field(
        default_factory=list, description="Outlier winning trades"
    )
    big_losers: List[TradeInsight] = Field(
        default_factory=list, description="Outlier losing trades"
    )
    patterns: Patterns = Field(
        default_factory=Patterns, description="Cross-trade patterns"
    )


class AnalysisResult(BaseModel):
    """Complete backtest analysis result."""

    analysis_id: Optional[int] = Field(None, description="Database ID (null before saving)")
    backtest_id: str = Field(..., description="Backtest identifier")
    analyzed_at: datetime = Field(
        default_factory=datetime.utcnow, description="When analysis was performed"
    )
    total_trades: int = Field(..., ge=0, description="Total number of trades analyzed")
    outlier_threshold_pct: float = Field(
        ..., gt=0.0, description="Standard deviation threshold for outlier detection"
    )
    num_big_winners: int = Field(..., ge=0, description="Number of outlier winners found")
    num_big_losers: int = Field(..., ge=0, description="Number of outlier losers found")
    findings: AnalysisFindings = Field(..., description="Structured analysis findings")
    summary_markdown: str = Field(..., description="Narrative summary in markdown")
    recommendations_markdown: str = Field(..., description="Recommendations in markdown")
    analyzer_version: str = Field(
        default="1.0.0", description="Version of analyzer that produced results"
    )

    @field_validator("analyzed_at")
    @classmethod
    def validate_analyzed_at(cls, v: datetime) -> datetime:
        """Ensure analyzed_at is UTC-aware."""
        return ensure_utc_aware(v)

    class Config:
        """Pydantic config."""

        json_schema_extra = {
            "example": {
                "backtest_id": "backtest_20260103_143022",
                "total_trades": 45,
                "outlier_threshold_pct": 2.0,
                "num_big_winners": 3,
                "num_big_losers": 4,
                "summary_markdown": "## Analysis Summary\n\nThis backtest showed...",
                "recommendations_markdown": "## Recommendations\n\n1. Consider...",
            }
        }
