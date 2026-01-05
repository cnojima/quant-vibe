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
        # Check if column contains any Decimal objects
        if len(df) > 0:
            # Apply conversion that handles Decimal, None, and other types
            def safe_float_convert(x):
                if isinstance(x, Decimal):
                    return float(x)
                return x

            df[col] = df[col].apply(safe_float_convert)

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

    # pydantic migration should take care of this
    # Convert expiration_date to date objects (handles strings, timestamps, etc.)
    # if 'expiration_date' in df.columns:
    #     df['expiration_date'] = pd.to_datetime(df['expiration_date'], errors='coerce').dt.date

    return df
