"""Symbol normalization utilities for options tickers."""


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
