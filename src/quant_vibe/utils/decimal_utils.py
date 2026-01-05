"""Decimal conversion utilities for safe handling of numeric data."""

from decimal import Decimal, InvalidOperation
from typing import Any, Union, Optional


def safe_decimal(value: Any, fallback: Union[Decimal, int, float, str, None] = None) -> Optional[Decimal]:
    """
    Safely convert a value to Decimal, with fallback handling.

    Args:
        value: Value to convert to Decimal
        fallback: Fallback value if conversion fails (default: None)

    Returns:
        Decimal representation of value, or fallback if conversion fails

    Examples:
        >>> safe_decimal(42.5)
        Decimal('42.5')
        >>> safe_decimal(None, 0)
        Decimal('0')
        >>> safe_decimal('invalid', 100)
        Decimal('100')
        >>> safe_decimal('NaN', 0)
        Decimal('0')
    """
    if value is None:
        if fallback is None:
            return None
        return safe_decimal(fallback, None)

    try:
        result = Decimal(str(value))
        # Check for NaN or Infinity
        if not result.is_finite():
            if fallback is None:
                return None
            return safe_decimal(fallback, None)
        return result
    except (ValueError, TypeError, InvalidOperation, ArithmeticError):
        if fallback is None:
            return None
        return safe_decimal(fallback, None)
