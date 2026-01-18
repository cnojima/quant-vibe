"""
Pricing utilities for options and market data calculations.

This module provides standardized pricing calculations to ensure consistency
across the entire codebase.

IMPORTANT: All pricing functions in this module are DETERMINISTIC and always
return valid float values (never None). This prevents downstream TypeErrors
when comparing prices. If no valid price can be calculated, functions return
0.0 by default rather than None. This design choice eliminates a common source
of runtime errors like "TypeError: '>' not supported between 'NoneType' and 'int'".
"""

from typing import Optional, Dict, Any, Union
import pandas as pd
import numpy as np

"""
Float uses binary (base-2) for speed but introduces small rounding errors,
    making it ideal for scientific data where slight inaccuracies are acceptable;
Decimal uses base-10 (like humans do) for exact storage,
    preventing representation errors and making it perfect for 
    financial calculations where precision is critical, though it's slower.
Think of Float as an approximation for physics, and Decimal as exact for money. 
"""
def calculate_mark_price(
    bid: Optional[Union[float, int, np.number]] = None,
    ask: Optional[Union[float, int, np.number]] = None,
    fallback: Optional[Union[float, int, np.number]] = None,
    default: float = 0.0
) -> float:
    """
    Calculate mark price (mid-point) from bid and ask prices.

    The mark price is the midpoint between bid and ask, commonly used
    as a fair value estimate for options pricing. Always returns a valid float.

    Args:
        bid: The bid price
        ask: The ask price
        fallback: Optional fallback value if bid/ask are not available
        default: Default value to return if no price can be determined (default: 0.0)

    Returns:
        The mark price if both bid and ask are available,
        fallback value if provided, otherwise the default value.
        ALWAYS returns a float, never None.

    Examples:
        >>> calculate_mark_price(10.0, 12.0)
        11.0
        >>> calculate_mark_price(None, 12.0, fallback=12.0)
        12.0
        >>> calculate_mark_price(None, None)
        0.0
        >>> calculate_mark_price(None, None, default=0.01)
        0.01
    """
    # Check for None, NaN, or invalid values
    if bid is not None and not pd.isna(bid) and ask is not None and not pd.isna(ask):
        # Both bid and ask are valid
        return float(bid + ask) / 2.0

    # If we can't calculate mark, return fallback if provided
    if fallback is not None and not pd.isna(fallback):
        return float(fallback)

    # Always return a valid float, never None
    return float(default)


def get_mark_price_from_row(
    row: Union[pd.Series, Dict[str, Any]],
    bid_col: str = 'bid',
    ask_col: str = 'ask',
    mark_col: str = 'mark',
    fallback_col: Optional[str] = None,
    default: float = 0.0
) -> float:
    """
    Calculate or retrieve mark price from a DataFrame row or dict.

    This function first attempts to calculate mark from bid/ask,
    then falls back to a pre-calculated mark column if available,
    and finally to any specified fallback column. Always returns a valid float.

    Args:
        row: A pandas Series (DataFrame row) or dictionary
        bid_col: Name of the bid price column
        ask_col: Name of the ask price column
        mark_col: Name of the pre-calculated mark price column
        fallback_col: Optional name of a fallback price column (e.g., 'last', 'close')
        default: Default value to return if no price can be determined (default: 0.0)

    Returns:
        The mark price if calculable, otherwise the default value.
        ALWAYS returns a float, never None.

    Examples:
        >>> data = {'bid': 10.0, 'ask': 12.0}
        >>> get_mark_price_from_row(data)
        11.0
        >>> data = {'bid': None, 'ask': None, 'mark': 11.5}
        >>> get_mark_price_from_row(data)
        11.5
        >>> data = {'bid': None, 'ask': None}
        >>> get_mark_price_from_row(data)
        0.0
    """
    # Try to get values from row (works for both Series and dict)
    bid = row.get(bid_col) if hasattr(row, 'get') else row[bid_col] if bid_col in row else None
    ask = row.get(ask_col) if hasattr(row, 'get') else row[ask_col] if ask_col in row else None

    # Try pre-calculated mark column first for efficiency
    mark_value = row.get(mark_col) if hasattr(row, 'get') else row[mark_col] if mark_col in row else None
    if mark_value is not None and not pd.isna(mark_value) and float(mark_value) > 0:
        return float(mark_value)

    # Calculate mark from bid/ask
    mark = calculate_mark_price(bid, ask)
    if mark > 0:
        return mark

    # Try fallback column if specified
    if fallback_col:
        fallback = row.get(fallback_col) if hasattr(row, 'get') else row[fallback_col] if fallback_col in row else None
        if fallback is not None and not pd.isna(fallback) and float(fallback) > 0:
            return float(fallback)

    # Always return a valid float
    return float(default)


def validate_price(
    price: Optional[float],
    min_price: float = 0.0,
    max_price: Optional[float] = None,
    underlying_price: Optional[float] = None,
    price_type: str = "option"
) -> bool:
    """
    Validate that a price is reasonable.

    Args:
        price: The price to validate
        min_price: Minimum valid price (default 0.0)
        max_price: Maximum valid price (optional)
        underlying_price: Underlying asset price for relative validation
        price_type: Type of price being validated ("option", "stock", etc.)

    Returns:
        True if price is valid, False otherwise
    """
    if price is None or pd.isna(price):
        return False

    # Basic range check
    if price < min_price:
        return False

    if max_price is not None and price > max_price:
        return False

    # For options, check relative to underlying if available
    if price_type == "option" and underlying_price is not None:
        # Option price shouldn't exceed underlying price
        # (for American-style options on non-dividend stocks)
        if price > underlying_price:
            return False

    return True