"""
Pydantic models for type-safe data handling.

These models provide:
- Runtime validation
- Compile-time type checking (via MyPy)
- Automatic serialization/deserialization
- Immutable data structures
- Self-documenting schemas

Usage:
    from quant_vibe.models import OptionsBar, UnderlyingBar, Trade

    # Create validated options bar
    bar = OptionsBar(
        timestamp=now_utc(),
        contract_symbol="SPXW260123P06860000",
        strike_price=6860.0,
        contract_type="put",
        expiration_date=date(2026, 1, 23),
        open=10.2,
        high=10.8,
        low=10.0,
        close=10.5,
        volume=100,
        bid=10.4,  # Optional - can be None
        ask=10.6,  # Optional - can be None
        mark=10.5,  # Optional - can be None
    )

    # Serialize to dict for Redis/database
    data = bar.model_dump()

    # Parse from dict with validation
    bar2 = OptionsBar(**data)

    # Validation errors are raised automatically
    try:
        bad_bar = OptionsBar(timestamp="not-a-datetime", ...)
    except ValidationError as e:
        print(e)  # Detailed error message
"""

from .market_data import OptionsBar, UnderlyingBar, Trade

__all__ = [
    "OptionsBar",
    "UnderlyingBar",
    "Trade",
]
