# BACKTEST Design Document

## Goal
Leverage OCHLV bar aggregate data in TimescaleDB to test investment strategies against historical data with high fidelity, performance optimization, and comprehensive risk management.

## Core Functionality

### 1. Data Pipeline

#### Data Sources
- **Primary Source**: TimescaleDB for OHLCV bars, Greeks, and quote data
- **Underlying Data**: Synchronized SPX/SPXW underlying price data
- **Contract Data**: Options chains with complete Greeks and pricing

#### Timeframe Support
- **1-minute**: Default for high-precision backtesting
- **5-minute**: Recommended for training (95% memory reduction)
- **15-minute, 1-hour, Daily**: Available for longer-term strategies

#### Data Loading
1. Load options OCHLV bar data from defined date/time window
   - Filter by DTE range (e.g., 0-45 days)
   - Filter by contract type (calls, puts)
   - Apply liquidity filters (minimum volume, bid-ask spread)
   - Validate Greeks availability
2. Load underlying OCHLV bar data from same window
   - Synchronize timestamps with options data
   - Handle missing data with interpolation
3. Cache frequently accessed patterns in Redis (1-hour TTL)

#### Data Quality
- **Completeness Threshold**: 95% minimum data availability
- **Suspicious Price Detection**: Cap unrealistic mark prices
- **Fallback Pricing**: Use intrinsic value for expired/missing data
- **Timestamp Tolerance**: 60-second window for underlying matching

### 2. Strategy Lifecycle

#### Core Lifecycle Methods
```python
class OptionsStrategy:
    def initialize(self, params: Dict) -> None:
        """Setup strategy state and parameters"""

    def analyze_market(self, bar_data: BarData) -> MarketAnalysis:
        """Process current market snapshot"""

    def should_enter(self, analysis: MarketAnalysis) -> bool:
        """Generate entry signals based on strategy rules"""

    def construct_spread(self, contracts: List[Contract]) -> OptionsSpread:
        """Build options position (vertical, calendar, etc.)"""

    def should_exit(self, position: Position, bar_data: BarData) -> bool:
        """Evaluate exit conditions (stop loss, profit target, etc.)"""

    def cleanup(self) -> None:
        """End of day/backtest cleanup"""
```

#### Strategy States
- **OBSERVING**: Analyzing market, waiting for entry signal
- **ENTERING**: Constructing position, validating liquidity
- **HOLDING**: Managing open position, monitoring exits
- **EXITING**: Closing position, calculating P&L
- **COOLDOWN**: Post-trade waiting period

### 3. Position Management

#### Entry Execution
- Market analysis with configurable observation periods
- Signal generation based on strategy-specific rules
- Spread construction with contract selection logic
- Liquidity validation before entry
- Capital sufficiency checks

#### Exit Management
Exit conditions are evaluated in strict priority order:
1. **Stop Loss** (mandatory, typically 25%)
2. **Profit Target** (configurable, 30-100%)
3. **Trailing Stop** (optional, 3-5% typical)
4. **Time-Based** (end of day, expiration approach)
5. **Strategy-Specific** (technical indicators, volatility)

#### Position Tracking
- Real-time mark-to-market valuation
- Unrealized P&L calculation per bar
- Realized P&L on position close
- Greeks aggregation for spread positions
- Equity curve generation

## Design Considerations

### Architecture Patterns

#### Strategy Registry Pattern
- Centralized strategy management
- Parameter validation via Pydantic models
- Dynamic strategy instantiation
- Optimization grid generation
- Single source of truth for all strategies

#### Orchestrator Pattern
- Configuration-driven execution
- YAML-based parameter management
- Multi-strategy coordination
- Batch processing support
- Result aggregation

#### Calculator Pattern
- Separated P&L calculation logic
- Standardized metrics computation
- Testable business logic
- Reusable across strategies

### Performance Optimization

#### Memory Management
- Use 5-minute bars for training (95% memory reduction)
- Lazy loading of Greeks and quotes
- Data batching for large date ranges
- Garbage collection between strategies
- DataFrame memory optimization

#### Caching Strategy
- Redis caching with 1-hour TTL
- Cache key: ticker + dates + DTE + timeframe
- 95% faster subsequent runs
- Automatic cache invalidation
- Memory-based cache for hot data

#### Parallel Processing (Future)
- Strategy-level parallelization
- Parameter grid parallelization
- Multi-core utilization
- Async data loading
- Result aggregation

### Risk Management Design

#### Mandatory Controls
- **25% Stop Loss**: Enforced at base class level
- **Capital Preservation**: Never risk more than allocated
- **Data Validation**: Reject trades with insufficient data
- **Liquidity Checks**: Minimum volume requirements

#### Configurable Limits
- Daily trade limits (1-5 per strategy)
- Maximum concurrent positions
- Capital allocation per position
- Maximum drawdown thresholds
- Time-based restrictions

## Limits and Constraints

### Technical Constraints

```yaml
performance_limits:
  max_backtest_days: 365          # Memory constraint
  max_concurrent_positions: 10    # Tracking complexity
  min_data_completeness: 0.95     # Data quality threshold
  max_parameter_combinations: 200 # Optimization runtime
  max_memory_usage_gb: 16         # System limitation

data_constraints:
  min_bar_volume: 1               # Liquidity filter
  max_bid_ask_spread: 5.0         # Slippage control
  min_option_volume: 10           # Options liquidity
  timestamp_tolerance_ms: 60000   # Underlying match window
  max_missing_bars_percent: 5     # Data quality

processing_constraints:
  max_bars_per_batch: 100000      # Memory management
  cache_ttl_seconds: 3600          # Redis cache duration
  max_parallel_workers: 4         # CPU utilization
  query_timeout_seconds: 300      # Database timeout
```

### Business Logic Constraints

```yaml
trading_rules:
  max_daily_trades: 5             # Per strategy limit
  min_dte: 0                      # Days to expiration
  max_dte: 45                     # Risk management
  max_loss_percent: 25            # Mandatory stop loss
  min_profit_target: 30           # Minimum profit %
  max_profit_target: 100          # Realistic limit

position_limits:
  max_positions_per_strategy: 1   # Concurrent positions
  max_capital_per_position: 0.1   # 10% of portfolio
  min_capital_per_position: 1000  # Minimum viable
  max_spread_width: 50            # Risk control

timing_constraints:
  market_open_buffer_minutes: 30  # Avoid opening volatility
  market_close_buffer_minutes: 15 # Avoid closing auctions
  min_holding_period_minutes: 15  # Avoid overtrading
  max_holding_period_days: 45     # DTE management
```

## Data Schema

### Options Bar Data
```python
@dataclass
class OptionsBar:
    timestamp: datetime  # UTC-aware
    contract_symbol: str

    # OHLCV data
    open: float
    high: float
    low: float
    close: float
    volume: int

    # Quote data
    bid: float
    ask: float
    mark: float  # Mid of bid-ask

    # Greeks
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float

    # Additional metrics
    implied_volatility: float
    open_interest: int
    underlying_price: float
```

### Position Data
```python
@dataclass
class OptionsPosition:
    entry_timestamp: datetime
    strategy_name: str
    legs: List[OptionLeg]

    # Entry metrics
    entry_capital: float
    entry_credit: float  # For credit spreads
    entry_debit: float   # For debit spreads

    # Current state
    current_value: float
    unrealized_pnl: float
    days_held: int

    # Risk metrics
    max_loss: float
    max_profit: float
    current_delta: float
    current_theta: float
```

## Error Handling

### Data Quality Issues
- **Missing Bars**: Interpolation or forward-fill strategies
- **Stale Quotes**: Use last known good values with staleness flag
- **Wide Spreads**: Skip entry if spread exceeds threshold
- **Zero Volume**: Reject trades on illiquid contracts

### Execution Failures
- **Insufficient Capital**: Skip trade and log warning
- **Contract Not Found**: Fallback to next available strike
- **Spread Construction Failed**: Abort entry attempt
- **Position Limit Reached**: Queue for next opportunity

### System Errors
- **Database Connection Lost**: Retry with exponential backoff
- **Cache Unavailable**: Fallback to direct database queries
- **Memory Exhaustion**: Batch processing with cleanup
- **Calculation Errors**: Fail gracefully with error logging

## Configuration Examples

### Basic Backtest Configuration
```yaml
backtest:
  engine:
    initial_capital: 100000
    commission_per_contract: 0.65
    slippage_ticks: 1
    allow_partial_fills: false

  data:
    ticker: SPXW
    timeframe: 5min  # Recommended for training
    start_date: 2024-01-01
    end_date: 2024-12-31
    dte_range: [0, 45]
    min_volume: 10
    max_spread: 5.0

  strategy:
    name: bullish_vertical_put
    parameters:
      spread_width: 10.0
      profit_target_min: 0.5
      stop_loss_percent: 0.25
      max_positions: 1
      observation_period: 15  # minutes

  output:
    save_trades: true
    save_equity_curve: true
    save_metrics: true
    output_dir: ./backtest_results
```

### Optimization Configuration
```yaml
optimization:
  strategy: bullish_vertical_put

  param_grid:
    spread_width: [5.0, 10.0, 15.0]
    profit_target_min: [0.3, 0.5, 0.7]
    stop_loss_percent: [0.25]  # Fixed

  fixed_params:
    min_dte: 0
    max_dte: 45
    max_positions: 1

  data:
    ticker: SPXW
    timeframe: 5min
    start_date: 2024-01-01
    end_date: 2024-06-30  # Training
    validation_start: 2024-07-01
    validation_end: 2024-12-31

  execution:
    max_workers: 4
    use_cache: true
    cache_ttl: 3600
```

## API Documentation

### Basic Usage
```python
from quant_vibe.services.backtest_service import BacktestService
from datetime import date

# Initialize service
service = BacktestService(
    db_connection=database_url,
    redis_client=redis_connection
)

# Run single backtest
results = await service.run_backtest(
    strategy_name="bullish_vertical_put",
    parameters={
        "spread_width": 10.0,
        "profit_target_min": 0.5,
        "stop_loss_percent": 0.25
    },
    start_date=date(2024, 1, 1),
    end_date=date(2024, 12, 31),
    initial_capital=100000
)

# Access results
print(f"Total Return: {results.total_return:.2%}")
print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
print(f"Max Drawdown: {results.max_drawdown:.2%}")
print(f"Win Rate: {results.win_rate:.2%}")

# Get detailed trades
for trade in results.trades:
    print(f"{trade.entry_date}: {trade.pnl:.2f} ({trade.pnl_percent:.2%})")
```

### Optimization Usage
```python
from quant_vibe.services.optimization_service import OptimizationService

# Initialize service
optimizer = OptimizationService(redis_client, db_connection)

# Generate parameter grid
param_grid = optimizer.generate_param_grid(
    strategy_name="bullish_vertical_put",
    custom_ranges={
        "spread_width": [5.0, 10.0, 15.0],
        "profit_target_min": [0.3, 0.5, 0.7]
    }
)

# Validate before running
is_valid, errors, warnings, count = optimizer.validate_param_grid(
    strategy_name="bullish_vertical_put",
    param_grid=param_grid,
    max_combinations=200
)

if is_valid:
    # Run optimization
    optimization_id = await optimizer.create_optimization(
        strategy_name="bullish_vertical_put",
        param_grid=param_grid,
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 12, 31)
    )

    # Monitor progress
    while True:
        status = await optimizer.get_status(optimization_id)
        print(f"Progress: {status['progress']:.1f}%")
        if status['status'] == 'completed':
            break
        await asyncio.sleep(5)
```

## Performance Metrics

### Return Metrics
- **Total Return**: Final equity / initial capital - 1
- **Annualized Return**: (1 + total_return) ^ (365/days) - 1
- **CAGR**: Compound annual growth rate
- **Monthly Returns**: Period-based return analysis

### Risk Metrics
- **Sharpe Ratio**: (returns - risk_free) / std_dev
- **Sortino Ratio**: (returns - target) / downside_dev
- **Max Drawdown**: Maximum peak-to-trough decline
- **Calmar Ratio**: Annualized return / max drawdown
- **Value at Risk (VaR)**: 95th percentile loss

### Trading Metrics
- **Win Rate**: Winning trades / total trades
- **Profit Factor**: Gross profit / gross loss
- **Average Win/Loss**: Mean profitable/losing trade
- **Expectancy**: (win_rate * avg_win) - (loss_rate * avg_loss)
- **Recovery Factor**: Net profit / max drawdown

### Statistical Metrics
- **Skewness**: Return distribution asymmetry
- **Kurtosis**: Return distribution tail weight
- **Beta**: Correlation with market returns
- **Alpha**: Excess return over benchmark
- **Information Ratio**: Active return / tracking error

## Testing Strategy

### Unit Testing
- Strategy logic validation
- P&L calculation accuracy
- Risk management rules
- Data transformation correctness

### Integration Testing
- End-to-end workflow validation
- Database query performance
- Cache functionality
- Multi-strategy execution

### Performance Testing
- Memory usage profiling
- Query optimization
- Backtest speed benchmarks
- Optimization scalability

### Data Testing
- Mock data generation
- Edge case handling
- Missing data scenarios
- Extreme market conditions

## Future Enhancements

### Near-term Improvements
1. **Event-driven Architecture**: More realistic order fills and slippage
2. **Parallel Processing**: Multi-core strategy and parameter optimization
3. **Advanced Slippage Models**: Dynamic based on volume and volatility
4. **Portfolio Backtesting**: Multiple concurrent strategies
5. **Real-time Progress**: WebSocket streaming to UI

### Medium-term Goals
1. **Walk-forward Analysis**: Out-of-sample validation
2. **Monte Carlo Simulation**: Risk assessment and confidence intervals
3. **Machine Learning Integration**: Feature engineering and signal generation
4. **Market Regime Detection**: Adaptive strategy parameters
5. **Advanced Optimization**: Genetic algorithms, Bayesian optimization

### Long-term Vision
1. **Paper Trading Bridge**: Seamless transition to live testing
2. **Multi-asset Support**: Futures, forex, crypto integration
3. **Risk Parity Allocation**: Portfolio-level optimization
4. **Execution Algorithms**: TWAP, VWAP, iceberg orders
5. **Cloud-native Architecture**: Distributed backtesting at scale

## Appendix

### Strategy Examples
- **Credit Spreads**: `bullish_vertical_put`, `bearish_vertical_call`
- **Debit Spreads**: `bullish_vertical_call`, `bearish_vertical_put`
- **Volatility Strategies**: `iron_condor`, `straddle`, `strangle`
- **Directional**: `long_call`, `protective_put`, `covered_call`

### Common Pitfalls
1. **Look-ahead Bias**: Using future data in decisions
2. **Survivorship Bias**: Only testing on current symbols
3. **Overfitting**: Too many parameters, not enough data
4. **Transaction Costs**: Underestimating slippage and commissions
5. **Data Snooping**: Repeatedly testing on same dataset

### Best Practices
1. Always use out-of-sample validation
2. Test across different market regimes
3. Include realistic transaction costs
4. Monitor for data quality issues
5. Document all assumptions
6. Version control strategy parameters
7. Regular performance regression tests