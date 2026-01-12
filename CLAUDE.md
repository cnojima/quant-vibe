# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.


### Documentation

- Always use `source venv/bin/activate` before executing a python command
- Schwab API uses `$SPX` as the underlying symbol for SPXW contracts
- don't assume localhost for the timescaleDB and redis.  check the flags in .env

#### Schema & Data Layer Documentation

**IMPORTANT**: When working with schemas, timestamps, or data transformations:

1. **Schema Reference**: See `docs/SCHEMA_MAPPING.md` for:
   - Column name mappings (`option_ticker` ↔ `contract_symbol`)
   - Symbol format standards and normalization
   - Timestamp timezone requirements (always UTC-aware)
   - Data type constraints and validation rules
   - DataFrame schema contracts

2. **Simplification Roadmap**: See `docs/SIMPLIFICATION_PLAN.md` for:
   - Current complexity issues and root causes
   - Pydantic migration plan (long-term)
   - Quick wins already implemented
   - Best practices for avoiding schema bugs

3. **Timestamp Utilities**: Always use `quant_vibe.utils.timestamp_utils`:
   ```python
   from quant_vibe.utils import now_utc, to_utc, ensure_utc_aware

   # ✅ CORRECT: Use these functions
   timestamp = now_utc()  # Always UTC-aware
   utc_dt = to_utc(naive_dt)  # Convert to UTC

   # ❌ WRONG: Never use these
   timestamp = datetime.now()  # Naive local time
   timestamp = datetime.utcnow()  # Naive UTC
   ```

4. **Schema Tests**: Run before deploying:
   ```bash
   pytest tests/integration/test_schema_consistency.py -v
   ```
#### Strategy Optimization Documentation

**IMPORTANT**: When working with strategy optimization:

1. **Optimization Service**: See `docs/OPTIMIZATION_SERVICE_REFACTOR.md` for:
   - Complete architecture and design patterns
   - API endpoint documentation
   - Integration guide
   - Performance optimizations

2. **Using OptimizationService**:
   ```python
   from quant_vibe.services.optimization_service import OptimizationService

   # Initialize service (typically in API dependencies)
   service = OptimizationService(
       redis_client=redis,
       db_connection_string=settings.database_url
   )

   # Generate param grid from strategy registry
   param_grid = service.generate_param_grid(
       strategy_name="bullish_vertical_put",
       custom_ranges={"spread_width": [5.0, 10.0, 15.0]},  # Optional overrides
       optimize_only=["spread_width", "profit_target_min"]  # Optional filter
   )

   # Validate param grid before running
   is_valid, errors, warnings, count = service.validate_param_grid(
       strategy_name="bullish_vertical_put",
       param_grid=param_grid,
       max_combinations=200
   )

   # Create and run optimization (async)
   optimization_id = await service.create_optimization(
       strategy_name="bullish_vertical_put",
       param_grid=param_grid,
       fixed_params={"min_dte": 0, "max_dte": 45},
       start_date=datetime(2024, 1, 1),
       end_date=datetime(2024, 12, 31),
       initial_capital=100000.0
   )

   # Run async (non-blocking)
   await service.run_optimization(optimization_id)
   ```

3. **Parameter Grid Best Practices**:
   - Always validate param grids before running optimizations
   - Keep combinations under 200 for reasonable execution times
   - Use `optimize_only` to focus on key parameters
   - Cache data with Redis for repeated optimizations (95% faster)
   - Monitor permutation count: `count = service.count_permutations(grid)`

4. **Fixed vs Optimizable Parameters**:
   ```python
   # Get fixed (non-optimizable) params from strategy
   fixed_params = service.get_fixed_params("bullish_vertical_put")

   # Fixed params are NOT included in param grid
   # They remain constant across all optimization combinations
   # Examples: min_dte, max_dte, max_trades_daily
   ```

5. **Data Caching**:
   ```python
   # Data is automatically cached in Redis with 1-hour TTL
   # Cache key includes: ticker, dates, DTE range, timeframe
   # Subsequent optimizations reuse cached data (0.1-0.5s vs 5-30s)

   # Clear cache when needed
   await service.clear_cache(cache_key="optimization:data:{hash}")
   ```

6. **Progress Tracking**:
   ```python
   # Check optimization status (includes ETA)
   status = await service.get_status(optimization_id)
   # Returns: {
   #   "status": "running",
   #   "progress": 45.5,
   #   "current_combination": 91,
   #   "total_combinations": 200,
   #   "estimated_completion_time": "2024-01-15T10:30:00Z",
   #   "best_sharpe_ratio": 1.85
   # }

   # Cancel running optimization
   await service.cancel_optimization(optimization_id)
   ```

7. **Frontend Integration**:
   - Use `ParamGridEditor` component for interactive parameter editing
   - Use `FixedParamsPanel` component to display fixed params
   - Real-time validation and permutation counting in UI
   - Warning modal if combinations exceed threshold
   - See `src/admin_ui/frontend/src/pages/StrategyOptimizer.tsx` for example

8. **Common Patterns**:
   ```python
   # Pattern 1: Auto-generate with defaults
   grid = service.generate_param_grid("bullish_vertical_put")

   # Pattern 2: Custom ranges for specific params
   grid = service.generate_param_grid(
       "bullish_vertical_put",
       custom_ranges={
           "spread_width": [5.0, 10.0, 15.0],
           "profit_target_min": [0.3, 0.5, 0.7]
       }
   )

   # Pattern 3: Optimize only key parameters
   grid = service.generate_param_grid(
       "bullish_vertical_put",
       optimize_only=["spread_width", "profit_target_min"]
   )

   # Pattern 4: Quick sanity check (few combinations)
   grid = service.generate_param_grid(
       "bullish_vertical_put",
       custom_ranges={"spread_width": [10.0]},  # Single value
       optimize_only=["spread_width"]
   )
   ```

9. **Performance Tips**:
   - Use 5min timeframe for training (95% memory reduction vs 1min)
   - Keep permutations under 200 for <1 hour execution
   - Reuse same date ranges to maximize cache hits
   - Run multiple smaller optimizations instead of one huge one
   - Check `optimization_cache_status` table for cache statistics

10. **Testing Optimizations**:
    ```bash
    # Test service functionality
    python scripts/test_optimization_service.py

    # Run unit tests
    pytest tests/unit/test_optimization_service.py -v
    ```
