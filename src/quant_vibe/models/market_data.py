"""
Pydantic models for market data.

These models define the canonical data structures for all market data
flowing through the system (streaming, Redis, database, backtesting).

All models enforce:
- UTC-aware timestamps
- Normalized symbol formats
- Lowercase contract types
- Type safety at runtime and compile-time

Usage:
    from quant_vibe.models import OptionsBar, UnderlyingBar

    # Create validated bar
    bar = OptionsBar(
        timestamp=now_utc(),
        contract_symbol="SPXW260123P06860000",
        strike_price=6860.0,
        contract_type="put",
        # ... rest of fields
    )

    # Serialize to dict
    data = bar.model_dump()

    # Serialize to JSON
    json_str = bar.model_dump_json()

    # Parse from dict
    bar2 = OptionsBar(**data)
"""

from datetime import datetime, date
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict, ValidationInfo

from quant_vibe.utils.timestamp_utils import ensure_utc_aware, is_utc_aware
from quant_vibe.utils.symbol_utils import (
    normalize_option_ticker,
    parse_contract_type_from_ticker,
    parse_strike_from_ticker,
    parse_expiration_from_ticker,
)


class OptionsBar(BaseModel):
    """
    Options bar data (1-minute OHLCV + quotes + Greeks).

    This is the canonical model for all options market data in the system.
    Used for:
    - Streaming data ingestion
    - Redis pub/sub messages
    - TimescaleDB storage
    - Backtesting engine
    - Live trading engine

    All fields are validated at creation time.
    """

    # Timestamp (always UTC-aware)
    timestamp: datetime = Field(
        description="Bar timestamp (UTC-aware, typically start of bar period)"
    )

    # Symbol (always normalized)
    contract_symbol: str = Field(
        description="Normalized contract symbol (e.g., 'SPXW260123P06860000')",
        min_length=1,
    )

    underlying_ticker: str = Field(
        default="SPX",
        description="Underlying asset ticker",
    )

    # Contract details
    strike_price: Decimal = Field(
        description="Strike price (e.g., 6860.00)",
        ge=0,  # Must be non-negative
    )

    contract_type: Literal["call", "put"] = Field(
        description="Contract type (lowercase 'call' or 'put')"
    )

    expiration_date: date = Field(
        description="Contract expiration date (YYYY-MM-DD)"
    )

    # OHLCV data
    open: Decimal = Field(
        description="Opening price for the bar period",
        ge=0,
    )

    high: Decimal = Field(
        description="Highest price during the bar period",
        ge=0,
    )

    low: Decimal = Field(
        description="Lowest price during the bar period",
        ge=0,
    )

    close: Decimal = Field(
        description="Closing price for the bar period",
        ge=0,
    )

    volume: int = Field(
        default=0,
        description="Total volume during the bar period",
        ge=0,
    )

    # Quote data (bid/ask spreads)
    bid: Optional[Decimal] = Field(
        default=None,
        description="Best bid price at bar close",
        ge=0,
    )

    ask: Optional[Decimal] = Field(
        default=None,
        description="Best ask price at bar close",
        ge=0,
    )

    mark: Optional[Decimal] = Field(
        default=None,
        description="Mark price (midpoint of bid/ask)",
        ge=0,
    )

    bid_size: Optional[int] = Field(
        default=None,
        description="Bid size at bar close",
        ge=0,
    )

    ask_size: Optional[int] = Field(
        default=None,
        description="Ask size at bar close",
        ge=0,
    )

    # Additional OHLCV metrics
    vwap: Optional[Decimal] = Field(
        default=None,
        description="Volume-weighted average price",
        ge=0,
    )

    transactions: Optional[int] = Field(
        default=None,
        description="Number of transactions during bar period",
        ge=0,
    )

    # Greeks (optional - may not be available for historical data)
    delta: Optional[Decimal] = Field(
        default=None,
        description="Delta (rate of change of option value with underlying price)",
    )

    gamma: Optional[Decimal] = Field(
        default=None,
        description="Gamma (rate of change of delta with underlying price)",
    )

    theta: Optional[Decimal] = Field(
        default=None,
        description="Theta (time decay, typically negative)",
    )

    vega: Optional[Decimal] = Field(
        default=None,
        description="Vega (sensitivity to implied volatility)",
    )

    rho: Optional[Decimal] = Field(
        default=None,
        description="Rho (sensitivity to interest rate)",
    )

    implied_volatility: Optional[Decimal] = Field(
        default=None,
        description="Implied volatility (as decimal, e.g., 0.25 = 25%)",
        ge=0,
    )

    # Metadata
    data_source: Optional[str] = Field(
        default=None,
        description="Data source (e.g., 'massive', 'schwab_realtime', 'schwab_poll')",
    )

    # Model configuration
    model_config = ConfigDict(
        frozen=True,  # Immutable after creation
        str_strip_whitespace=True,  # Strip whitespace from strings
        validate_assignment=True,  # Validate on field assignment (if not frozen)
    )

    # Validators
    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_utc_aware(cls, v: datetime) -> datetime:
        """Ensure timestamp is UTC-aware."""
        if not is_utc_aware(v):
            return ensure_utc_aware(v)
        return v

    @field_validator("contract_symbol")
    @classmethod
    def normalize_symbol(cls, v: str) -> str:
        """Normalize contract symbol format."""
        return normalize_option_ticker(v)

    @field_validator("contract_type", mode="before")
    @classmethod
    def normalize_contract_type(cls, v: str) -> str:
        """
        Normalize contract type to 'call' or 'put'.

        Handles both single-character ('c', 'p', 'C', 'P') and
        full-word formats ('call', 'put', 'CALL', 'PUT').
        """
        v_lower = v.lower().strip()
        if v_lower in ('c', 'call'):
            return 'call'
        elif v_lower in ('p', 'put'):
            return 'put'
        # If neither, let Pydantic raise validation error
        return v_lower

    @field_validator("mark")
    @classmethod
    def validate_mark_within_bid_ask(cls, v: Optional[Decimal], info: ValidationInfo) -> Optional[Decimal]:
        """
        Validate mark price is between bid and ask.

        Note: We allow some tolerance since mark may be calculated
        separately or at a different time than bid/ask.
        """
        if v is None:
            return v

        data = info.data
        if "bid" in data and "ask" in data:
            bid = data["bid"]
            ask = data["ask"]

            # Only validate if both bid and ask are present
            if bid is not None and ask is not None:
                # Mark should be between bid and ask (with small tolerance)
                if ask > bid:  # Normal case
                    expected_mark = (bid + ask) / 2
                    tolerance = (ask - bid) * Decimal("0.1")  # 10% of spread

                    if not (bid - tolerance <= v <= ask + tolerance):
                        # Just log warning, don't fail validation
                        # (mark might be stale or calculated differently)
                        pass

        return v

    @field_validator("high")
    @classmethod
    def high_gte_low(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        """Ensure high >= low."""
        data = info.data
        if "low" in data and v < data["low"]:
            raise ValueError(f"High {v} must be >= low {data['low']}")
        return v

    @field_validator("high")
    @classmethod
    def high_gte_open_close(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        """Ensure high >= open and close."""
        data = info.data
        if "open" in data and v < data["open"]:
            raise ValueError(f"High {v} must be >= open {data['open']}")
        if "close" in data and v < data["close"]:
            raise ValueError(f"High {v} must be >= close {data['close']}")
        return v

    @field_validator("low")
    @classmethod
    def low_lte_open_close(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        """Ensure low <= open and close."""
        data = info.data
        if "open" in data and v > data["open"]:
            raise ValueError(f"Low {v} must be <= open {data['open']}")
        if "close" in data and v > data["close"]:
            raise ValueError(f"Low {v} must be <= close {data['close']}")
        return v

    @model_validator(mode='before')
    @classmethod
    def enrich_from_contract_symbol(cls, data: dict) -> dict:
        """
        Enrich missing fields by parsing contract_symbol.

        This allows creating OptionsBar from incomplete data (e.g., from Redis)
        where only contract_symbol is reliable, and other fields might be missing.

        Automatically fills:
        - strike_price (from contract_symbol if missing)
        - contract_type (from contract_symbol if missing)
        - expiration_date (from contract_symbol if missing)
        """
        contract_symbol = data.get('contract_symbol') or data.get('option_ticker')

        if contract_symbol:
            # Rename option_ticker to contract_symbol if needed
            if 'option_ticker' in data and 'contract_symbol' not in data:
                data['contract_symbol'] = data.pop('option_ticker')

            # Enrich strike_price if missing
            if data.get('strike_price') is None:
                strike = parse_strike_from_ticker(contract_symbol)
                if strike is not None:
                    data['strike_price'] = strike

            # Enrich contract_type if missing
            if data.get('contract_type') is None:
                contract_type = parse_contract_type_from_ticker(contract_symbol)
                if contract_type is not None:
                    data['contract_type'] = contract_type

            # Enrich expiration_date if missing
            if data.get('expiration_date') is None:
                exp_date = parse_expiration_from_ticker(contract_symbol)
                if exp_date is not None:
                    data['expiration_date'] = exp_date

        return data

    @model_validator(mode='before')
    @classmethod
    def fix_inverted_spread(cls, data: dict) -> dict:
        """
        Fix inverted bid-ask spreads by swapping them.

        Inverted spreads (bid > ask) can occur in aggregated data when LAST(bid)
        and LAST(ask) are sampled at different times. This affects ~0.02% of
        historical data.

        We swap them to maintain the invariant: bid <= ask.
        """
        bid = data.get('bid')
        ask = data.get('ask')

        if bid is not None and ask is not None:
            if bid > ask:
                # Swap bid and ask
                data['bid'] = ask
                data['ask'] = bid
        return data

    @model_validator(mode='before')
    @classmethod
    def fix_ohlc_consistency(cls, data: dict) -> dict:
        """
        Fix inconsistent OHLC values by adjusting high/low to maintain invariants.

        Inconsistent OHLC data can occur in real-time streaming data when values
        arrive out of order or from different market data sources. This ensures:
        - high >= max(open, low, close)
        - low <= min(open, high, close)

        We adjust high/low rather than open/close to preserve the opening and
        closing prices which are semantically important.
        """
        open_val = data.get('open')
        high_val = data.get('high')
        low_val = data.get('low')
        close_val = data.get('close')

        # Convert to Decimal if they're not None
        if open_val is not None:
            open_val = Decimal(str(open_val))
        if high_val is not None:
            high_val = Decimal(str(high_val))
        if low_val is not None:
            low_val = Decimal(str(low_val))
        if close_val is not None:
            close_val = Decimal(str(close_val))

        # Only fix if all OHLC values are present
        if all(v is not None for v in [open_val, high_val, low_val, close_val]):
            # Ensure high >= max(open, low, close)
            required_high = max(open_val, low_val, close_val)
            if high_val < required_high:
                data['high'] = required_high

            # Ensure low <= min(open, high, close)
            # Use the potentially adjusted high value
            adjusted_high = data.get('high')
            if adjusted_high is not None:
                adjusted_high = Decimal(str(adjusted_high))
            else:
                adjusted_high = high_val

            required_low = min(open_val, adjusted_high, close_val)
            if low_val > required_low:
                data['low'] = required_low

        return data

    # Helper methods
    def to_dict(self) -> dict:
        """Convert to dictionary (alias for model_dump)."""
        return self.model_dump()

    def to_json(self) -> str:
        """Convert to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_dict(cls, data: dict) -> "OptionsBar":
        """Create from dictionary (with validation)."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> "OptionsBar":
        """Create from JSON string."""
        return cls.model_validate_json(json_str)

    def calculate_mark(self) -> Optional[Decimal]:
        """Calculate mark price as midpoint of bid/ask."""
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return None

    def intrinsic_value(self, underlying_price: Decimal) -> Decimal:
        """
        Calculate intrinsic value of the option.

        Args:
            underlying_price: Current price of underlying asset

        Returns:
            Intrinsic value (max of 0 or strike differential)
        """
        if self.contract_type == "call":
            return max(Decimal(0), underlying_price - self.strike_price)
        else:  # put
            return max(Decimal(0), self.strike_price - underlying_price)

    def time_value(self, underlying_price: Decimal) -> Optional[Decimal]:
        """
        Calculate time value (extrinsic value) of the option.

        Args:
            underlying_price: Current price of underlying asset

        Returns:
            Time value (mark price - intrinsic value), or None if mark is unavailable
        """
        if self.mark is None:
            return None
        intrinsic = self.intrinsic_value(underlying_price)
        return self.mark - intrinsic

    def is_itm(self, underlying_price: Decimal) -> bool:
        """Check if option is in-the-money."""
        if self.contract_type == "call":
            return underlying_price > self.strike_price
        else:  # put
            return underlying_price < self.strike_price

    def is_atm(self, underlying_price: Decimal, threshold: Decimal = Decimal("0.01")) -> bool:
        """
        Check if option is at-the-money.

        Args:
            underlying_price: Current price of underlying
            threshold: % threshold for ATM (default 1%)

        Returns:
            True if option is within threshold of ATM
        """
        pct_diff = abs(underlying_price - self.strike_price) / self.strike_price
        return pct_diff <= threshold

    def is_otm(self, underlying_price: Decimal) -> bool:
        """Check if option is out-of-the-money."""
        return not self.is_itm(underlying_price)


class UnderlyingBar(BaseModel):
    """
    Underlying asset bar data (1-minute OHLCV for SPX, SPY, etc.).

    This model represents price data for the underlying asset.
    Used for:
    - Underlying price tracking in streaming
    - Strategy signal generation
    - Intrinsic value calculations
    - Position P&L calculations
    """

    # Timestamp (always UTC-aware)
    timestamp: datetime = Field(
        description="Bar timestamp (UTC-aware)"
    )

    ticker: str = Field(
        default="SPX",
        description="Underlying ticker symbol",
        min_length=1,
    )

    # OHLCV data
    open: Decimal = Field(
        description="Opening price",
        ge=0,
    )

    high: Decimal = Field(
        description="Highest price",
        ge=0,
    )

    low: Decimal = Field(
        description="Lowest price",
        ge=0,
    )

    close: Decimal = Field(
        description="Closing price",
        ge=0,
    )

    volume: int = Field(
        default=0,
        description="Total volume",
        ge=0,
    )

    vwap: Optional[Decimal] = Field(
        default=None,
        description="Volume-weighted average price",
        ge=0,
    )

    transactions: Optional[int] = Field(
        default=None,
        description="Number of transactions",
        ge=0,
    )

    # Metadata
    data_source: Optional[str] = Field(
        default=None,
        description="Data source (e.g., 'schwab', 'polygon', 'yahoo')",
    )

    # Model configuration
    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
    )

    # Validators
    @field_validator("timestamp")
    @classmethod
    def timestamp_must_be_utc_aware(cls, v: datetime) -> datetime:
        """Ensure timestamp is UTC-aware."""
        if not is_utc_aware(v):
            return ensure_utc_aware(v)
        return v

    @field_validator("high")
    @classmethod
    def high_gte_low(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        """Ensure high >= low."""
        data = info.data
        if "low" in data and v < data["low"]:
            raise ValueError(f"High {v} must be >= low {data['low']}")
        return v

    @field_validator("high")
    @classmethod
    def high_gte_open_close(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        """Ensure high >= open and close."""
        data = info.data
        if "open" in data and v < data["open"]:
            raise ValueError(f"High {v} must be >= open {data['open']}")
        if "close" in data and v < data["close"]:
            raise ValueError(f"High {v} must be >= close {data['close']}")
        return v

    @field_validator("low")
    @classmethod
    def low_lte_open_close(cls, v: Decimal, info: ValidationInfo) -> Decimal:
        """Ensure low <= open and close."""
        data = info.data
        if "open" in data and v > data["open"]:
            raise ValueError(f"Low {v} must be <= open {data['open']}")
        if "close" in data and v > data["close"]:
            raise ValueError(f"Low {v} must be <= close {data['close']}")
        return v

    @model_validator(mode='before')
    @classmethod
    def fix_ohlc_consistency(cls, data: dict) -> dict:
        """
        Fix inconsistent OHLC values by adjusting high/low to maintain invariants.

        Inconsistent OHLC data can occur in real-time streaming data when values
        arrive out of order or from different market data sources. This ensures:
        - high >= max(open, low, close)
        - low <= min(open, high, close)

        We adjust high/low rather than open/close to preserve the opening and
        closing prices which are semantically important.
        """
        open_val = data.get('open')
        high_val = data.get('high')
        low_val = data.get('low')
        close_val = data.get('close')

        # Convert to Decimal if they're not None
        if open_val is not None:
            open_val = Decimal(str(open_val))
        if high_val is not None:
            high_val = Decimal(str(high_val))
        if low_val is not None:
            low_val = Decimal(str(low_val))
        if close_val is not None:
            close_val = Decimal(str(close_val))

        # Only fix if all OHLC values are present
        if all(v is not None for v in [open_val, high_val, low_val, close_val]):
            # Ensure high >= max(open, low, close)
            required_high = max(open_val, low_val, close_val)
            if high_val < required_high:
                data['high'] = required_high

            # Ensure low <= min(open, high, close)
            # Use the potentially adjusted high value
            adjusted_high = data.get('high')
            if adjusted_high is not None:
                adjusted_high = Decimal(str(adjusted_high))
            else:
                adjusted_high = high_val

            required_low = min(open_val, adjusted_high, close_val)
            if low_val > required_low:
                data['low'] = required_low

        return data

    # Helper methods
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return self.model_dump()

    def to_json(self) -> str:
        """Convert to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_dict(cls, data: dict) -> "UnderlyingBar":
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> "UnderlyingBar":
        """Create from JSON string."""
        return cls.model_validate_json(json_str)


class Trade(BaseModel):
    """
    Completed trade record (from backtest or live trading).

    Represents a full trade lifecycle from entry to exit.
    Used for:
    - Backtest results storage
    - Live trading history
    - Performance analytics
    - Trade journaling
    """

    # Identification
    trade_id: str = Field(
        description="Unique trade identifier",
        min_length=1,
    )

    position_id: str = Field(
        description="Position identifier (may have multiple trades)",
        min_length=1,
    )

    strategy_name: str = Field(
        description="Strategy that generated the trade",
        min_length=1,
    )

    spread_type: str = Field(
        description="Spread type (e.g., 'vertical_call', 'vertical_put', 'iron_condor')",
        min_length=1,
    )

    # Timing (all UTC-aware)
    entry_time: datetime = Field(
        description="Trade entry timestamp (UTC)"
    )

    exit_time: datetime = Field(
        description="Trade exit timestamp (UTC)"
    )

    # Entry details
    entry_premium: Decimal = Field(
        description="Premium collected/paid at entry (positive = credit, negative = debit)"
    )

    entry_underlying_price: Decimal = Field(
        description="Underlying price at entry",
        ge=0,
    )

    entry_trigger: Optional[str] = Field(
        default=None,
        description="What triggered the entry (e.g., 'signal', 'limit_order')",
    )

    # Exit details
    exit_premium: Decimal = Field(
        description="Premium collected/paid at exit"
    )

    exit_underlying_price: Decimal = Field(
        description="Underlying price at exit",
        ge=0,
    )

    exit_reason: str = Field(
        description="Why the trade was closed (e.g., 'profit_target', 'stop_loss', 'expiration')",
        min_length=1,
    )

    # Performance
    pnl: Decimal = Field(
        description="Profit/loss (exit_premium - entry_premium for credits, reversed for debits)"
    )

    pnl_pct: Decimal = Field(
        description="P&L as percentage of max risk"
    )

    max_risk: Decimal = Field(
        description="Maximum risk (width of spread for defined-risk trades)",
        ge=0,
    )

    # Position tracking
    max_profit: Optional[Decimal] = Field(
        default=None,
        description="Maximum unrealized profit reached during trade",
    )

    peak_value: Optional[Decimal] = Field(
        default=None,
        description="Peak position value during trade",
    )

    # Legs (list of option legs)
    legs: list[dict] = Field(
        description="List of option legs in the trade (each leg is a dict with symbol, quantity, etc.)"
    )

    # Model configuration
    model_config = ConfigDict(
        frozen=True,
        str_strip_whitespace=True,
    )

    # Validators
    @field_validator("entry_time", "exit_time")
    @classmethod
    def timestamp_must_be_utc_aware(cls, v: datetime) -> datetime:
        """Ensure timestamps are UTC-aware."""
        if not is_utc_aware(v):
            return ensure_utc_aware(v)
        return v

    @field_validator("exit_time")
    @classmethod
    def exit_after_entry(cls, v: datetime, info: ValidationInfo) -> datetime:
        """Ensure exit_time > entry_time."""
        data = info.data
        if "entry_time" in data and v <= data["entry_time"]:
            raise ValueError(f"Exit time {v} must be after entry time {data['entry_time']}")
        return v

    # Helper methods
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return self.model_dump()

    def to_json(self) -> str:
        """Convert to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_dict(cls, data: dict) -> "Trade":
        """Create from dictionary."""
        return cls(**data)

    @classmethod
    def from_json(cls, json_str: str) -> "Trade":
        """Create from JSON string."""
        return cls.model_validate_json(json_str)

    def holding_period_seconds(self) -> float:
        """Calculate holding period in seconds."""
        return (self.exit_time - self.entry_time).total_seconds()

    def holding_period_minutes(self) -> float:
        """Calculate holding period in minutes."""
        return self.holding_period_seconds() / 60.0

    def holding_period_hours(self) -> float:
        """Calculate holding period in hours."""
        return self.holding_period_seconds() / 3600.0

    def is_winner(self) -> bool:
        """Check if trade was profitable."""
        return self.pnl > 0

    def is_loser(self) -> bool:
        """Check if trade was unprofitable."""
        return self.pnl < 0

    def risk_reward_ratio(self) -> Optional[Decimal]:
        """Calculate risk/reward ratio (max_profit / max_risk)."""
        if self.max_profit is not None and self.max_risk > 0:
            return self.max_profit / self.max_risk
        return None
