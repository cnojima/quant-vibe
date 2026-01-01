"""
Pydantic schemas for configuration validation and UI generation.

These schemas define the structure, types, defaults, and validation rules
for both backtest.yaml and live_trading.yaml configuration files.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


# ==================== Common Strategy Schema ====================


class StrategyParams(BaseModel):
    """Base strategy parameters. Actual strategies may have different params."""

    # Common parameters across strategies
    max_trades_daily: Optional[int] = Field(
        None, ge=1, le=100, description="Maximum trades per day"
    )
    spread_width: Optional[float] = Field(
        None, ge=0, le=100, description="Spread width in points"
    )
    observation_period: Optional[int] = Field(
        None, ge=1, le=1440, description="Observation period in minutes"
    )
    pullback_amount: Optional[float] = Field(
        None, ge=0, le=500, description="Pullback amount in points"
    )
    profit_target_min: Optional[float] = Field(
        None, ge=0, le=10, description="Minimum profit target"
    )
    profit_target_max: Optional[float] = Field(
        None, ge=0, le=10, description="Maximum profit target"
    )
    trailing_stop_pct: Optional[float] = Field(
        None, ge=0, le=1, description="Trailing stop percentage"
    )
    stop_loss_pct: Optional[float] = Field(
        None, ge=0, le=1, description="Stop loss percentage"
    )
    min_dte: Optional[int] = Field(
        None, ge=0, le=365, description="Minimum days to expiration"
    )
    max_dte: Optional[int] = Field(
        None, ge=0, le=365, description="Maximum days to expiration"
    )
    num_spreads: Optional[int] = Field(
        None, ge=1, le=100, description="Number of spreads to consider"
    )
    min_volume: Optional[int] = Field(
        None, ge=0, le=10000, description="Minimum volume required"
    )
    min_bid_ask_spread_pct: Optional[float] = Field(
        None, ge=0, le=100, description="Maximum bid-ask spread percentage"
    )

    # IV Scalp specific
    iv_threshold: Optional[float] = Field(
        None, ge=0, le=1, description="IV threshold for entry"
    )
    iv_spike_pct: Optional[float] = Field(
        None, ge=0, le=1, description="IV spike percentage"
    )
    momentum_lookback: Optional[int] = Field(
        None, ge=1, le=100, description="Momentum lookback period"
    )
    iv_lookback: Optional[int] = Field(
        None, ge=1, le=1000, description="IV lookback period"
    )

    # Coin Toss specific
    target_price: Optional[float] = Field(
        None, ge=0, description="Target contract price"
    )
    buy_limit: Optional[float] = Field(None, ge=0, description="Buy limit price")
    sell_target: Optional[float] = Field(None, ge=0, description="Sell target price")
    price_tolerance: Optional[float] = Field(
        None, ge=0, description="Price tolerance"
    )
    quantity: Optional[int] = Field(None, ge=1, le=1000, description="Contract quantity")
    profit_target_pct: Optional[float] = Field(
        None, ge=0, le=10, description="Profit target percentage"
    )

    # Coin Toss Limit specific
    target_contract_price: Optional[float] = Field(
        None, ge=0, description="Target contract price"
    )
    limit_buy_price: Optional[float] = Field(None, ge=0, description="Limit buy price")
    profit_target_price: Optional[float] = Field(
        None, ge=0, description="Profit target price"
    )
    otm_percent_min: Optional[float] = Field(
        None, ge=0, le=1, description="Minimum OTM percentage"
    )
    otm_percent_max: Optional[float] = Field(
        None, ge=0, le=1, description="Maximum OTM percentage"
    )
    order_expiry_minutes: Optional[int] = Field(
        None, ge=1, le=1440, description="Order expiry in minutes"
    )

    class Config:
        extra = "allow"  # Allow additional fields not defined here


class StrategyConfig(BaseModel):
    """Configuration for a single strategy."""

    name: str = Field(..., description="Strategy name (e.g., 'bullish_vertical_put')")
    enabled: bool = Field(default=True, description="Enable/disable this strategy")
    params: StrategyParams = Field(
        default_factory=StrategyParams, description="Strategy-specific parameters"
    )


class StrategyList(BaseModel):
    """List of enabled strategies."""

    enabled: List[StrategyConfig] = Field(
        default_factory=list, description="List of enabled strategies"
    )


# ==================== Backtest Configuration Schema ====================


class BacktestEngineConfig(BaseModel):
    """Backtest engine configuration."""

    initial_capital: float = Field(
        100000, ge=1000, le=10000000, description="Initial capital for backtesting"
    )
    parallel_execution: bool = Field(
        False, description="Run strategies in parallel"
    )
    auto_save_results: bool = Field(
        True, description="Automatically save backtest results"
    )
    output_dir: str = Field(
        "reports/backtests", description="Output directory for backtest reports"
    )


class DateRangeConfig(BaseModel):
    """Date range configuration for backtesting."""

    preset: Literal[
        "today", "this_week", "this_month", "this_quarter", "this_year", "custom"
    ] = Field("this_month", description="Date range preset")

    class CustomDateRange(BaseModel):
        start_date: str = Field(
            ..., description="Start date in YYYY-MM-DD format", pattern=r"^\d{4}-\d{2}-\d{2}$"
        )
        end_date: str = Field(
            ..., description="End date in YYYY-MM-DD format", pattern=r"^\d{4}-\d{2}-\d{2}$"
        )

    custom: Optional[CustomDateRange] = Field(
        None, description="Custom date range (required if preset='custom')"
    )
    trading_days_only: bool = Field(
        True, description="Use trading days only (exclude weekends)"
    )
    market_hours_only: bool = Field(
        True, description="Use market hours only (9:30 AM - 4:00 PM EST)"
    )


class DataSourceConfig(BaseModel):
    """Data source configuration for backtesting."""

    underlying_ticker: str = Field("SPX", description="Underlying ticker symbol")
    db_profile: Literal["auto", "local", "remote"] = Field(
        "auto", description="Database profile to use"
    )
    min_dte: int = Field(0, ge=0, le=365, description="Minimum days to expiration")
    max_dte: int = Field(2, ge=0, le=365, description="Maximum days to expiration")
    verbose: bool = Field(True, description="Verbose logging for data loading")


class ReportingConfig(BaseModel):
    """Reporting configuration."""

    print_trade_details: bool = Field(True, description="Print detailed trade information")
    print_educational_metrics: bool = Field(
        True, description="Print educational analytics"
    )
    print_performance_summary: bool = Field(
        True, description="Print performance summary"
    )
    save_equity_chart: bool = Field(False, description="Save equity curve chart")
    generate_html_report: bool = Field(False, description="Generate HTML report")


class OutputConfig(BaseModel):
    """Output configuration."""

    timestamp_format: str = Field(
        "%Y%m%d_%H%M%S", description="Timestamp format for output files"
    )
    save_trades: bool = Field(True, description="Save trades to CSV")
    save_equity_curve: bool = Field(True, description="Save equity curve to CSV")
    save_summary: bool = Field(True, description="Save summary to CSV")
    save_log: bool = Field(True, description="Save execution log")


class LoggingConfig(BaseModel):
    """Logging configuration."""

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", description="Logging level"
    )
    tee_output: bool = Field(True, description="Tee output to console and file")
    log_dir: str = Field("logs/backtests", description="Log directory")


class BatchConfig(BaseModel):
    """Batch execution configuration."""

    enabled: bool = Field(False, description="Enable batch execution mode")


class BacktestConfig(BaseModel):
    """Complete backtest configuration schema."""

    engine: BacktestEngineConfig = Field(
        default_factory=BacktestEngineConfig, description="Backtest engine settings"
    )
    date_range: DateRangeConfig = Field(
        default_factory=DateRangeConfig, description="Date range for backtesting"
    )
    strategies: StrategyList = Field(
        default_factory=StrategyList, description="Strategy configurations"
    )
    data_source: DataSourceConfig = Field(
        default_factory=DataSourceConfig, description="Data source settings"
    )
    reporting: ReportingConfig = Field(
        default_factory=ReportingConfig, description="Reporting settings"
    )
    output: OutputConfig = Field(
        default_factory=OutputConfig, description="Output settings"
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig, description="Logging settings"
    )
    batch: BatchConfig = Field(
        default_factory=BatchConfig, description="Batch execution settings"
    )


# ==================== Live Trading Configuration Schema ====================


class LiveEngineConfig(BaseModel):
    """Live trading engine configuration."""

    paper_trading: bool = Field(
        True, description="Enable paper trading mode (no real orders)"
    )
    use_redis_feed: bool = Field(
        True, description="Use Redis data feed (recommended)"
    )
    max_positions: int = Field(
        5, ge=1, le=100, description="Maximum number of concurrent positions"
    )
    max_capital_per_trade: float = Field(
        10000, ge=100, le=1000000, description="Maximum capital per trade"
    )
    daily_loss_limit_pct: float = Field(
        0.05, ge=0, le=1, description="Daily loss limit as percentage of capital"
    )
    data_stale_timeout_seconds: int = Field(
        300, ge=10, le=3600, description="Data stale timeout in seconds"
    )


class DataFeedConfig(BaseModel):
    """Data feed configuration."""

    window_size: int = Field(
        100, ge=10, le=1000, description="Data window size for analysis"
    )
    aggregate_interval_seconds: int = Field(
        60, ge=1, le=300, description="Data aggregation interval in seconds"
    )
    max_dte: int = Field(45, ge=0, le=365, description="Maximum days to expiration")
    min_dte: int = Field(0, ge=0, le=365, description="Minimum days to expiration")
    strike_range_pct: float = Field(
        0.1, ge=0.01, le=1, description="Strike range percentage from ATM"
    )


class RedisConfig(BaseModel):
    """Redis connection configuration."""

    host: Optional[str] = Field(None, description="Redis host (uses REDIS_HOST env var)")
    port: Optional[int] = Field(None, ge=1, le=65535, description="Redis port (uses REDIS_PORT env var)")
    db: Optional[int] = Field(None, ge=0, le=15, description="Redis database number (uses REDIS_DB env var)")


class RiskConfig(BaseModel):
    """Risk management configuration."""

    max_total_exposure: float = Field(
        100000, ge=1000, le=10000000, description="Maximum total exposure"
    )
    max_drawdown_pct: float = Field(
        0.1, ge=0, le=1, description="Maximum drawdown percentage"
    )
    position_concentration_limit: float = Field(
        0.3, ge=0, le=1, description="Position concentration limit"
    )


class OCOConfig(BaseModel):
    """OCO (One-Cancels-Other) order configuration."""

    enabled: bool = Field(False, description="Enable OCO orders")
    profit_target_pct: float = Field(
        0.5, ge=0, le=10, description="Profit target percentage"
    )
    stop_loss_pct: float = Field(
        -0.3, ge=-1, le=0, description="Stop loss percentage (negative)"
    )
    use_market_on_stop: bool = Field(
        True, description="Use market orders for stop loss"
    )
    verify_placement: bool = Field(True, description="Verify OCO order placement")
    fallback_to_monitoring: bool = Field(
        True, description="Fallback to manual monitoring if OCO fails"
    )


class AlertsConfig(BaseModel):
    """Alert configuration."""

    on_position_open: bool = Field(False, description="Alert on position open")
    on_position_close: bool = Field(True, description="Alert on position close")
    on_daily_loss_limit: bool = Field(True, description="Alert on daily loss limit")
    on_max_drawdown: bool = Field(True, description="Alert on max drawdown")
    on_data_stale: bool = Field(True, description="Alert on stale data")
    on_order_error: bool = Field(True, description="Alert on order error")


class MonitoringConfig(BaseModel):
    """Monitoring configuration."""

    status_update_interval_seconds: int = Field(
        60, ge=1, le=3600, description="Status update interval in seconds"
    )
    health_check_interval_seconds: int = Field(
        30, ge=1, le=3600, description="Health check interval in seconds"
    )
    email_alerts_enabled: bool = Field(False, description="Enable email alerts")
    email_recipients: List[str] = Field(
        default_factory=list, description="Email recipients for alerts"
    )
    alerts: AlertsConfig = Field(
        default_factory=AlertsConfig, description="Alert settings"
    )


class LiveLoggingConfig(BaseModel):
    """Live trading logging configuration."""

    log_dir: str = Field("logs/live_trading", description="Log directory")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", description="Logging level"
    )
    rotation: Literal["daily", "hourly", "size"] = Field(
        "daily", description="Log rotation strategy"
    )
    retention_days: int = Field(
        30, ge=1, le=365, description="Log retention in days"
    )


class DatabaseConfig(BaseModel):
    """Database configuration."""

    use_timescale: bool = Field(True, description="Use TimescaleDB for data storage")


class EmergencyConfig(BaseModel):
    """Emergency controls configuration."""

    kill_switch_enabled: bool = Field(
        True, description="Enable emergency kill switch"
    )
    close_all_at_eod: bool = Field(
        True, description="Close all positions at end of day"
    )
    eod_close_time: str = Field(
        "15:55", description="End of day close time (HH:MM)", pattern=r"^\d{2}:\d{2}$"
    )


class DevelopmentConfig(BaseModel):
    """Development and debugging configuration."""

    debug_mode: bool = Field(False, description="Enable debug mode")
    instant_fills: bool = Field(
        False, description="Instant fills for testing (skip order simulation)"
    )
    save_stream_messages: bool = Field(
        False, description="Save raw stream messages for debugging"
    )


class LiveTradingConfig(BaseModel):
    """Complete live trading configuration schema."""

    engine: LiveEngineConfig = Field(
        default_factory=LiveEngineConfig, description="Live trading engine settings"
    )
    strategies: StrategyList = Field(
        default_factory=StrategyList, description="Strategy configurations"
    )
    data_feed: DataFeedConfig = Field(
        default_factory=DataFeedConfig, description="Data feed settings"
    )
    redis: RedisConfig = Field(
        default_factory=RedisConfig, description="Redis connection settings"
    )
    risk: RiskConfig = Field(
        default_factory=RiskConfig, description="Risk management settings"
    )
    oco: OCOConfig = Field(
        default_factory=OCOConfig, description="OCO order settings"
    )
    monitoring: MonitoringConfig = Field(
        default_factory=MonitoringConfig, description="Monitoring settings"
    )
    logging: LiveLoggingConfig = Field(
        default_factory=LiveLoggingConfig, description="Logging settings"
    )
    database: DatabaseConfig = Field(
        default_factory=DatabaseConfig, description="Database settings"
    )
    emergency: EmergencyConfig = Field(
        default_factory=EmergencyConfig, description="Emergency controls"
    )
    development: DevelopmentConfig = Field(
        default_factory=DevelopmentConfig, description="Development settings"
    )


# ==================== Schema Export Functions ====================


def resolve_schema_refs(schema: Dict[str, Any], defs: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """
    Recursively resolve $ref references in a JSON Schema.

    Args:
        schema: The schema to resolve
        defs: The $defs dictionary from the root schema

    Returns:
        Schema with all $ref references resolved
    """
    if defs is None:
        defs = schema.get("$defs", {})

    # Handle $ref
    if "$ref" in schema:
        ref_path = schema["$ref"]
        if ref_path.startswith("#/$defs/"):
            ref_name = ref_path.replace("#/$defs/", "")
            if ref_name in defs:
                # Get the referenced schema and resolve it recursively
                resolved = resolve_schema_refs(defs[ref_name].copy(), defs)
                # Merge description if it exists in the original schema
                if "description" in schema:
                    resolved["description"] = schema["description"]
                return resolved
        return schema

    # Recursively resolve references in properties
    if "properties" in schema:
        schema["properties"] = {
            key: resolve_schema_refs(value, defs)
            for key, value in schema["properties"].items()
        }

    # Recursively resolve references in items (for arrays)
    if "items" in schema:
        schema["items"] = resolve_schema_refs(schema["items"], defs)

    # Recursively resolve references in anyOf/oneOf/allOf
    for key in ["anyOf", "oneOf", "allOf"]:
        if key in schema:
            schema[key] = [resolve_schema_refs(item, defs) for item in schema[key]]

    return schema


def get_backtest_json_schema() -> Dict[str, Any]:
    """Get JSON Schema for backtest configuration with all $ref references resolved."""
    schema = BacktestConfig.model_json_schema()
    # Resolve all $ref references
    resolved = resolve_schema_refs(schema.copy())
    # Remove $defs since they're now resolved
    resolved.pop("$defs", None)
    return resolved


def get_live_trading_json_schema() -> Dict[str, Any]:
    """Get JSON Schema for live trading configuration with all $ref references resolved."""
    schema = LiveTradingConfig.model_json_schema()
    # Resolve all $ref references
    resolved = resolve_schema_refs(schema.copy())
    # Remove $defs since they're now resolved
    resolved.pop("$defs", None)
    return resolved
