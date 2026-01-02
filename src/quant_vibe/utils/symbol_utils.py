"""Symbol normalization utilities for options tickers."""

from datetime import datetime
from typing import Optional


def parse_expiration_from_ticker(ticker: str) -> Optional[datetime]:
    """
    Parse expiration date from option ticker symbol.

    Format: {UNDERLYING}{YYMMDD}{C|P}{STRIKE8DIGITS}
    Example: "SPXW251231C06875000" -> December 31, 2025

    Args:
        ticker: Normalized option ticker

    Returns:
        Expiration date or None if parsing fails
    """
    try:
        # Remove prefix to find date portion
        # For SPXW: skip 4 chars, for SPX: skip 3 chars
        if ticker.startswith('SPXW'):
            date_start = 4
        elif ticker.startswith('SPX'):
            date_start = 3
        else:
            # Generic: find first digit sequence of length 6
            for i, char in enumerate(ticker):
                if char.isdigit():
                    date_str = ticker[i:i+6]
                    if len(date_str) == 6 and date_str.isdigit():
                        year = 2000 + int(date_str[0:2])
                        month = int(date_str[2:4])
                        day = int(date_str[4:6])
                        return datetime(year, month, day).date()
            return None

        # Extract YYMMDD
        date_str = ticker[date_start:date_start+6]
        if len(date_str) != 6 or not date_str.isdigit():
            return None

        year = 2000 + int(date_str[0:2])
        month = int(date_str[2:4])
        day = int(date_str[4:6])

        return datetime(year, month, day).date()
    except (ValueError, IndexError):
        return None


def parse_contract_type_from_ticker(ticker: str) -> Optional[str]:
    """
    Parse contract type (call/put) from option ticker symbol.

    Format: {UNDERLYING}{YYMMDD}{C|P}{STRIKE8DIGITS}
    Example: "SPXW251231C06875000" -> "call"

    Args:
        ticker: Normalized option ticker

    Returns:
        'call' or 'put', or None if parsing fails
    """
    try:
        # Find 'C' or 'P' after 6-digit date
        # For SPXW: position 10 (4 + 6)
        # For SPX: position 9 (3 + 6)
        if ticker.startswith('SPXW'):
            type_pos = 10
        elif ticker.startswith('SPX'):
            type_pos = 9
        else:
            # Generic: find C or P after date sequence
            for i, char in enumerate(ticker):
                if char in ('C', 'P') and i > 6:
                    return 'call' if char == 'C' else 'put'
            return None

        if type_pos < len(ticker):
            type_char = ticker[type_pos]
            if type_char == 'C':
                return 'call'
            elif type_char == 'P':
                return 'put'

        return None
    except (ValueError, IndexError):
        return None


def parse_strike_from_ticker(ticker: str) -> Optional[float]:
    """
    Parse strike price from option ticker symbol.

    Format: {UNDERLYING}{YYMMDD}{C|P}{STRIKE8DIGITS}
    Example: "SPXW251231C06875000" -> 6875.0

    Strike is encoded as 8 digits with 3 decimal places.
    Example: 06875000 -> 6875.000

    Args:
        ticker: Normalized option ticker

    Returns:
        Strike price as float, or None if parsing fails
    """
    try:
        # Strike is always the last 8 digits
        if len(ticker) < 8:
            return None

        strike_str = ticker[-8:]
        if not strike_str.isdigit():
            return None

        # Convert to float with 3 decimal places
        # Example: 06875000 -> 6875.000
        strike = int(strike_str) / 1000.0

        return strike
    except (ValueError, IndexError):
        return None


def normalize_option_ticker(ticker: str) -> str:
    """
    Normalize option ticker to canonical format.

    Handles multiple input formats from different data sources:
    - Schwab streaming: "SPXW  260123P06860000" → "SPXW260123P06860000"
    - Schwab poll: "SPXW251226C06875000" → "SPXW251226C06875000" (already normalized)
    - Massive API: "O:SPXW251219C06945000" → "SPXW251219C06945000"

    Target format: {UNDERLYING}{YYMMDD}{C|P}{STRIKE8DIGITS}
    Example: "SPXW251226C06875000"

    This normalization ensures consistent storage in the database and lookups
    across different data sources.

    Args:
        ticker: Raw option ticker from any data source

    Returns:
        Normalized ticker (no spaces, no O: prefix)

    Examples:
        >>> normalize_option_ticker("SPXW  260123P06860000")
        'SPXW260123P06860000'
        >>> normalize_option_ticker("O:SPXW251219C06945000")
        'SPXW251219C06945000'
        >>> normalize_option_ticker("SPXW251226C06875000")
        'SPXW251226C06875000'
    """
    if not ticker:
        return ticker

    # Remove "O:" prefix (Massive API format)
    if ticker.startswith("O:"):
        ticker = ticker[2:]

    # Remove all spaces (Schwab streaming format has extra spaces)
    ticker = ticker.replace(" ", "")

    return ticker
