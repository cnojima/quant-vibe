"""DataFrame utility functions for data type conversions."""

import pandas as pd
from decimal import Decimal


def convert_decimals_to_float(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert Decimal columns to float for pandas compatibility.

    Pydantic models use Decimal for precision, but pandas operations
    (like .std(), .mean()) require numeric types that support arithmetic.

    Args:
        df: DataFrame with potential Decimal columns

    Returns:
        DataFrame with Decimal columns converted to float
    """
    if df.empty:
        return df

    for col in df.columns:
        # Check if column contains Decimal objects
        if len(df) > 0 and isinstance(df[col].iloc[0], Decimal):
            df[col] = df[col].astype(float)

    return df


def convert_string_columns_to_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert string representations of numeric values to proper numeric types.

    This is needed after deserializing from Redis/JSON where Pydantic Decimal
    fields are serialized as strings. Common columns that need conversion include
    OHLCV data, Greeks, strikes, bid/ask prices, etc.

    Args:
        df: DataFrame with potential string-typed numeric columns

    Returns:
        DataFrame with numeric columns properly typed

    Example:
        >>> df = pd.DataFrame({'close': ['96.3', '113.5'], 'volume': ['100', '200']})
        >>> df = convert_string_columns_to_numeric(df)
        >>> df['close'].dtype
        dtype('float64')
    """
    if df.empty:
        return df

    # Known numeric columns in market data
    numeric_cols = [
        # OHLCV
        'open', 'high', 'low', 'close', 'volume',
        # Quotes
        'bid', 'ask', 'mark', 'bid_size', 'ask_size',
        # Contract details
        'strike_price',
        # Greeks
        'delta', 'gamma', 'theta', 'vega', 'rho', 'implied_volatility',
        # Other
        'vwap', 'transactions', 'underlying_price',
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    return df
