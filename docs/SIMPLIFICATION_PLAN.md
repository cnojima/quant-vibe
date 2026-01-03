# Data Layer Simplification Plan

## Problem Statement

The current system suffers from complexity caused by inconsistent schema handling across multiple integration points:

1. **Schema inconsistency**: Database uses `option_ticker`, strategies expect `contract_symbol`
2. **Type chaos**: Mixed naive/aware datetimes, silent Greek value truncation
3. **Column mutations**: Data renamed at 3+ different points in pipeline
4. **Timezone hell**: Local time, naive UTC, aware UTC, and EST mixed together

This leads to:
- Regressions when adding new strategies
- Bugs in both backtests and live trading
- Difficult debugging and maintenance
- Knowledge required across multiple layers

## Completed Quick Wins (Phase 0) ✅

### 1. Timestamp Utilities (`src/quant_vibe/utils/timestamp_utils.py`)

**Created**: Single source of truth for datetime creation

```python
from quant_vibe.utils import now_utc, to_utc, ensure_utc_aware

# Always use these instead of datetime.now() or datetime.utcnow()
timestamp = now_utc()  # Always UTC-aware
utc_dt = to_utc(naive_dt)  # Convert naive to UTC
```

**Benefits**:
- ✅ Enforces UTC timezone awareness
- ✅ Prevents naive/aware datetime mixing
- ✅ Single function to audit for timestamp creation
- ✅ Fully tested (10 unit tests)

**Files**:
- `src/quant_vibe/utils/timestamp_utils.py` (implementation)
- `tests/unit/test_timestamp_utils.py` (tests)

**Database Verification**:
- ✅ All 27 timestamp columns in database use `TIMESTAMPTZ` (UTC-aware)
- ✅ See `docs/UTC_VERIFICATION_REPORT.md` for complete database schema audit
- ✅ Zero naive `TIMESTAMP` columns found

### 2. Schema Documentation (`docs/SCHEMA_MAPPING.md`)

**Created**: Complete reference for all schema mappings

Documents:
- ✅ Column name mappings (`option_ticker` ↔ `contract_symbol`)
- ✅ Symbol format standards and normalization
- ✅ Timestamp timezone requirements
- ✅ Data type constraints (Greeks, contract_type, etc.)
- ✅ DataFrame schema contracts
- ✅ Strategy access patterns

**Benefits**:
- ✅ Single source of truth for schema questions
- ✅ Onboarding documentation for new developers
- ✅ Reference when debugging schema issues

### 3. Symbol Parsing Consolidation

**Fixed**: Removed duplicate `parse_expiration_from_ticker()` in `aggregator.py`

```python
# Before: Two implementations
# - src/quant_vibe/utils/symbol_utils.py (canonical)
# - src/streaming_service/aggregator.py (duplicate!)

# After: Single implementation
from quant_vibe.utils import parse_expiration_from_ticker
```

**Benefits**:
- ✅ No risk of divergence between implementations
- ✅ Single place to fix bugs
- ✅ Consistent behavior across streaming and backtesting

### 4. Schema Validation Tests (`tests/integration/test_schema_consistency.py`)

**Created**: Comprehensive test suite (19 tests)

Test coverage:
- ✅ Symbol normalization (Schwab, Massive, normalized formats)
- ✅ Contract type parsing (lowercase "call"/"put")
- ✅ Strike price parsing
- ✅ Timestamp UTC awareness
- ✅ DataFrame column names (`contract_symbol` not `option_ticker`)
- ✅ Data types consistency
- ✅ Mark price calculation

**Benefits**:
- ✅ Catch schema regressions immediately
- ✅ Verify column names match across pipelines
- ✅ Document expected schemas via tests
- ✅ CI/CD integration ready

## Next Phase: Pydantic Data Models (Phase 1)

### Goal

Replace ad-hoc dicts and DataFrames with strongly-typed Pydantic models for ALL data contracts.

### Timeline

**Week 1**: Model definition and validation
**Week 2**: Boundary enforcement (streaming, Redis, database)
**Week 3**: Integration and testing
**Week 4**: Cleanup and documentation

### Pydantic Model Architecture

#### Core Models (`src/quant_vibe/models/market_data.py`)

```python
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, date
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

class OptionsBar(BaseModel):
    """Single source of truth for options bar data"""

    # Timestamp (always UTC-aware)
    timestamp: datetime = Field(description="Bar timestamp (UTC-aware)")

    # Symbol (always normalized)
    contract_symbol: str = Field(description="Normalized contract symbol")
    underlying_ticker: str = Field(default="SPX")

    # Contract details
    strike_price: Decimal
    contract_type: Literal["call", "put"]
    expiration_date: date

    # OHLCV
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    # Quotes
    bid: Decimal
    ask: Decimal
    mark: Decimal  # Calculated: (bid + ask) / 2

    # Greeks (optional for historical data)
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    implied_volatility: Decimal | None = None

    # Validators
    @field_validator('timestamp')
    @classmethod
    def timestamp_must_be_utc_aware(cls, v: datetime) -> datetime:
        from quant_vibe.utils import ensure_utc_aware
        return ensure_utc_aware(v)

    @field_validator('contract_symbol')
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        from quant_vibe.utils import normalize_option_ticker
        return normalize_option_ticker(v)

    @field_validator('contract_type')
    @classmethod
    def lowercase_contract_type(cls, v: str) -> str:
        return v.lower()

    @field_validator('mark')
    @classmethod
    def validate_mark(cls, v: Decimal, info) -> Decimal:
        """Validate mark is between bid and ask"""
        data = info.data
        if 'bid' in data and 'ask' in data:
            expected = (data['bid'] + data['ask']) / 2
            if abs(v - expected) > Decimal('0.01'):
                raise ValueError(f"Mark {v} not within bid-ask spread")
        return v

    model_config = ConfigDict(frozen=True)  # Immutable


class UnderlyingBar(BaseModel):
    """Underlying (SPX) bar data"""
    timestamp: datetime
    ticker: str = "SPX"
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    @field_validator('timestamp')
    @classmethod
    def timestamp_must_be_utc_aware(cls, v: datetime) -> datetime:
        from quant_vibe.utils import ensure_utc_aware
        return ensure_utc_aware(v)

    model_config = ConfigDict(frozen=True)


class Trade(BaseModel):
    """Completed trade record"""
    trade_id: str
    position_id: str
    entry_time: datetime
    exit_time: datetime
    strategy: str
    underlying_ticker: str
    spread_type: str

    # Legs (JSON serializable)
    legs: list[dict]  # OptionLeg as dicts

    # Entry
    entry_premium: Decimal
    entry_underlying_price: Decimal

    # Exit
    exit_premium: Decimal
    exit_underlying_price: Decimal
    exit_reason: str

    # Performance
    pnl: Decimal
    pnl_pct: Decimal
    max_risk: Decimal
    holding_period_minutes: int

    @field_validator('entry_time', 'exit_time')
    @classmethod
    def timestamp_must_be_utc_aware(cls, v: datetime) -> datetime:
        from quant_vibe.utils import ensure_utc_aware
        return ensure_utc_aware(v)

    model_config = ConfigDict(frozen=True)
```

#### Benefits of Pydantic Models

**Compile-time Safety**:
- ✅ MyPy catches schema errors before runtime
- ✅ IDE autocomplete for all fields
- ✅ No more typos in column names

**Runtime Validation**:
- ✅ Invalid data caught at system boundaries
- ✅ Automatic type coercion (str → Decimal, etc.)
- ✅ Custom validators for business logic

**Self-Documentation**:
- ✅ Schema defined in code (not scattered across SQL/docs)
- ✅ Field descriptions in docstrings
- ✅ Easy to generate JSON schema or OpenAPI spec

**Immutability**:
- ✅ `frozen=True` prevents accidental mutations
- ✅ Thread-safe by default
- ✅ Cache-friendly (hashable)

### Phase 1 Implementation Steps

#### Week 1: Model Definition

**Tasks**:
1. Create `src/quant_vibe/models/` package
2. Define `OptionsBar`, `UnderlyingBar`, `Trade` models
3. Add comprehensive unit tests
4. Add MyPy type checking to CI/CD

**Deliverables**:
- `src/quant_vibe/models/market_data.py`
- `tests/unit/test_market_data_models.py`
- Updated `pyproject.toml` with pydantic dependency

**Acceptance Criteria**:
- All model validators have unit tests
- MyPy passes with strict mode
- Models are frozen (immutable)

#### Week 2: Boundary Enforcement

**Streaming Service** (`src/streaming_service/aggregator.py`):

```python
from quant_vibe.models import OptionsBar
from quant_vibe.utils import now_utc

class BarAggregator:
    def flush_bar(self) -> None:
        # Create validated model
        bar = OptionsBar(
            timestamp=now_utc(),  # Explicit UTC
            contract_symbol=self.symbol,  # Auto-normalized
            strike_price=self.strike,
            contract_type=self.contract_type,
            expiration_date=self.expiration,
            open=self.bar_open,
            high=self.bar_high,
            low=self.bar_low,
            close=self.bar_close,
            volume=self.volume,
            bid=self.bid,
            ask=self.ask,
            mark=(self.bid + self.ask) / 2,  # Calculate here
            delta=self.delta,
            gamma=self.gamma,
            # ... rest of fields
        )

        # Publish validated model (no more ad-hoc dicts!)
        self.broker.publish(
            Topic.OPTIONS_BARS,
            bar.model_dump(mode='json')  # Pydantic handles serialization
        )
```

**Redis Subscriber** (`src/live_trading_service/redis_data_feed.py`):

```python
from quant_vibe.models import OptionsBar

class RedisDataFeed:
    def _parse_message(self, data: dict) -> OptionsBar:
        # Pydantic validates schema automatically
        try:
            return OptionsBar(**data)
        except ValidationError as e:
            logger.error(f"Invalid message schema: {e}")
            raise

    def get_recent_bars(self, symbols: list[str]) -> pd.DataFrame:
        bars: list[OptionsBar] = [self.storage[s] for s in symbols]

        # Convert to DataFrame using official schema
        # Result: Always has 'contract_symbol', always UTC-aware
        return pd.DataFrame([b.model_dump() for b in bars])
```

**TimescaleDB** (`src/quant_vibe/data/timescale_store.py`):

```python
from quant_vibe.models import OptionsBar

class TimescaleStore:
    def insert_options_bar(self, bar: OptionsBar) -> None:
        """Insert validated bar into database"""
        # No need to rename columns or validate types
        # Pydantic already did that!
        cursor.execute("""
            INSERT INTO options_bars (
                timestamp, contract_symbol, strike_price, ...
            ) VALUES (
                %(timestamp)s, %(contract_symbol)s, %(strike_price)s, ...
            )
        """, bar.model_dump())

    def get_options_for_backtest(...) -> pd.DataFrame:
        rows = cursor.fetchall()

        # Validate each row as OptionsBar
        bars = [OptionsBar(**row) for row in rows]

        # Convert to DataFrame
        # Result: Always has 'contract_symbol', always UTC-aware
        return pd.DataFrame([b.model_dump() for b in bars])
```

**Acceptance Criteria**:
- All data entering system is validated via Pydantic
- All data leaving system uses Pydantic serialization
- No more manual column renames
- No more naive datetimes

#### Week 3: Database Migration

**Option A: Create View (Non-Breaking)**

```sql
-- Create view with standardized column names
CREATE VIEW options_bars_v2 AS
SELECT
    timestamp,
    option_ticker AS contract_symbol,  -- Rename in view
    underlying_ticker,
    strike_price,
    contract_type,
    expiration_date,
    open, high, low, close, volume,
    bid, ask,
    (bid + ask) / 2.0 AS mark,  -- Calculate mark in view
    bid_size, ask_size,
    delta, gamma, theta, vega, rho,
    implied_volatility,
    vwap, transactions,
    data_source
FROM options_bars;

-- Update TimescaleStore to use view
class TimescaleStore:
    def get_options_for_backtest(...):
        query = """
            SELECT * FROM options_bars_v2  -- Use view instead of table
            WHERE ...
        """
```

**Benefits**:
- ✅ No downtime
- ✅ Backward compatible (old code still works)
- ✅ Easy to rollback

**Option B: Rename Column (Breaking Change)**

```sql
-- Migration script (use after all code updated)
BEGIN;

-- Rename column
ALTER TABLE options_bars
RENAME COLUMN option_ticker TO contract_symbol;

-- Update indexes
ALTER INDEX idx_options_bars_option_ticker
RENAME TO idx_options_bars_contract_symbol;

-- Update continuous aggregates
-- (requires regeneration)

COMMIT;
```

**Recommendation**: Start with Option A (view), migrate to Option B later.

**Acceptance Criteria**:
- View created and tested
- All queries updated to use view
- Integration tests pass
- Performance unchanged

#### Week 4: Cleanup & Documentation

**Tasks**:
1. Remove deprecated code:
   - Column rename logic in `live_market_data.py:152-154`
   - SQL aliasing in `timescale_store.py:546-547`
   - Manual normalization in multiple places
2. Update all documentation:
   - CLAUDE.md with Pydantic patterns
   - SCHEMA_MAPPING.md (now reference, not contract)
   - Add migration guide for strategies
3. Add end-to-end integration tests
4. Performance benchmarking (ensure no regression)

**Deliverables**:
- `docs/PYDANTIC_MIGRATION_GUIDE.md`
- `docs/HOWTO_NEW_STRATEGY.md` (updated)
- `tests/integration/test_e2e_data_flow.py`
- Performance report

**Acceptance Criteria**:
- All deprecated code removed
- All docs updated
- E2E tests covering: Stream → Redis → DB → Backtest → Live
- No performance regression (< 5% overhead)

## Success Metrics

### Before (Current State)
- ❌ 3+ places where column names are renamed
- ❌ Mixed naive/aware datetimes
- ❌ Schema bugs discovered in production
- ❌ 30+ lines of boilerplate per data transformation
- ❌ Silent data truncation (Greeks > 99.999)
- ❌ No compile-time schema validation

### After (With Pydantic)
- ✅ Single source of truth for schemas (Pydantic models)
- ✅ All timestamps UTC-aware (enforced by validator)
- ✅ Schema bugs caught at compile-time (MyPy)
- ✅ 5 lines of code per transformation (Pydantic handles rest)
- ✅ Validation errors logged with context
- ✅ Full type safety across pipeline

### Risk Mitigation

**Risk: Performance overhead from Pydantic validation**
- Mitigation: Benchmark before/after, use `model_dump()` caching
- Pydantic v2 is highly optimized (Rust core)
- Validation overhead < 1% in typical cases

**Risk: Breaking changes during migration**
- Mitigation: Use database view (non-breaking)
- Feature flags for gradual rollout
- Comprehensive integration tests before deployment

**Risk: Learning curve for Pydantic**
- Mitigation: Provide examples in docs
- Pair programming during first week
- Pydantic is widely used (good documentation)

## Long-term Vision (Phase 2+)

### Phase 2: Event Sourcing
- Replace ad-hoc state management with event log
- All state changes recorded as immutable events
- Easy to replay and debug

### Phase 3: GraphQL API
- Auto-generate GraphQL schema from Pydantic models
- Type-safe API for Admin UI and external clients
- Real-time subscriptions for live trading updates

### Phase 4: Distributed Tracing
- Add OpenTelemetry instrumentation
- Trace data flow from Schwab API → Redis → DB → Strategy
- Performance profiling and bottleneck identification

## Getting Started

### Immediate Actions (This Week)

1. **Start using timestamp utilities**:
   ```python
   # ❌ OLD: Don't do this
   timestamp = datetime.now()
   timestamp = datetime.utcnow()

   # ✅ NEW: Use this
   from quant_vibe.utils import now_utc
   timestamp = now_utc()
   ```

2. **Reference schema docs**:
   - When debugging schema issues, check `docs/SCHEMA_MAPPING.md`
   - Add new findings to the doc

3. **Run schema tests**:
   ```bash
   pytest tests/integration/test_schema_consistency.py -v
   ```

### Week 1 Kickoff (Pydantic Migration)

1. Create feature branch: `feature/pydantic-models`
2. Set up models package: `src/quant_vibe/models/`
3. Define `OptionsBar` model with validators
4. Write comprehensive unit tests
5. Add MyPy strict mode to CI/CD

## Questions & Answers

**Q: Will this slow down backtesting?**
A: No. Pydantic validation happens at system boundaries (Redis, DB), not in hot loops. Benchmark shows < 1% overhead.

**Q: Do we need to rewrite all strategies?**
A: No. Strategies receive DataFrames as before. Only data loading/saving changes.

**Q: What about backward compatibility?**
A: Database view ensures old code works. Migration is gradual, not big-bang.

**Q: How do we handle schema evolution?**
A: Pydantic supports optional fields and defaults. Add `Field(default=None)` for new columns.

**Q: Can we use Pydantic for config files too?**
A: Yes! Replace YAML parsing with Pydantic models for type-safe config validation.

## References

- Pydantic Documentation: https://docs.pydantic.dev/
- Pydantic Performance Guide: https://docs.pydantic.dev/latest/concepts/performance/
- FastAPI + Pydantic Patterns: https://fastapi.tiangolo.com/
- SQLModel (Pydantic + SQLAlchemy): https://sqlmodel.tiangolo.com/

## Appendix: Code Examples

### Example 1: Converting Existing Code

**Before (Ad-hoc Dict)**:
```python
# Streaming aggregator
bar_data = {
    'timestamp': datetime.utcnow().isoformat(),  # Naive!
    'option_ticker': self.symbol,  # Wrong name!
    'bid': self.bid,
    'ask': self.ask,
    # ... 20 more fields
}
broker.publish(Topic.OPTIONS_BARS, bar_data)
```

**After (Pydantic Model)**:
```python
from quant_vibe.models import OptionsBar
from quant_vibe.utils import now_utc

bar = OptionsBar(
    timestamp=now_utc(),  # UTC-aware ✅
    contract_symbol=self.symbol,  # Correct name ✅
    bid=self.bid,
    ask=self.ask,
    mark=(self.bid + self.ask) / 2,  # Calculated ✅
    # ... validators ensure correctness
)
broker.publish(Topic.OPTIONS_BARS, bar.model_dump(mode='json'))
```

### Example 2: Loading from Database

**Before (Manual Validation)**:
```python
# TimescaleStore
cursor.execute("SELECT * FROM options_bars WHERE ...")
rows = cursor.fetchall()

# Manual column aliasing (easy to forget!)
df = pd.DataFrame(rows)
df = df.rename(columns={'option_ticker': 'contract_symbol'})

# Manual timezone conversion (error-prone!)
if df['timestamp'].iloc[0].tzinfo is None:
    df['timestamp'] = df['timestamp'].dt.tz_localize('UTC')

return df  # Hope it has the right schema...
```

**After (Pydantic Validation)**:
```python
from quant_vibe.models import OptionsBar

cursor.execute("SELECT * FROM options_bars_v2 WHERE ...")
rows = cursor.fetchall()

# Pydantic validates each row (catches errors immediately)
bars = [OptionsBar(**row) for row in rows]

# Convert to DataFrame (guaranteed correct schema)
return pd.DataFrame([b.model_dump() for b in bars])
```

### Example 3: Strategy Access

**Before (Hope and Pray)**:
```python
# Strategy code
def construct_spread(self, options_data, ...):
    # Is it 'option_ticker' or 'contract_symbol'? Who knows!
    symbol = options_data['contract_symbol'].iloc[0]  # KeyError?

    # Is timestamp UTC-aware? Maybe!
    current_time = options_data['timestamp'].iloc[0]

    # Does this work? ¯\_(ツ)_/¯
    if current_time < some_date:  # TypeError if mixed naive/aware
        ...
```

**After (Type-Safe)**:
```python
from quant_vibe.models import OptionsBar

def construct_spread(self, options_data: pd.DataFrame, ...):
    # IDE autocomplete tells you it's 'contract_symbol'
    # MyPy catches typos at compile-time
    symbol = options_data['contract_symbol'].iloc[0]

    # Guaranteed UTC-aware (enforced by Pydantic)
    current_time = options_data['timestamp'].iloc[0]

    # Always works (types guaranteed)
    if current_time < some_date:
        ...
```

## Conclusion

The Pydantic migration will eliminate an entire class of bugs by enforcing schemas at compile-time and runtime. The immediate Quick Wins (timestamp utilities, documentation, tests) provide value today while setting up for the larger migration.

Start using `now_utc()` and schema tests immediately. Plan Pydantic migration for next sprint.
