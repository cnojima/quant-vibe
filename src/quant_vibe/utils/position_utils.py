"""Position utility functions.

Provides helper functions for position ID generation and management.
"""

import uuid
from datetime import datetime
from typing import Optional


def generate_position_id(
    strategy_prefix: str,
    current_time: datetime,
    counter: Optional[int] = None,
    include_uuid: bool = False
) -> str:
    """
    Generate a unique position ID.

    This function creates a globally unique position ID using a combination of:
    - Strategy prefix (e.g., "BVP", "COIN", "BB")
    - Timestamp (YYYYMMDD_HHMMSS)
    - Optional counter (for strategies that track daily trades)
    - Optional UUID suffix (for guaranteed uniqueness)

    Args:
        strategy_prefix: Short strategy identifier (e.g., "BVP", "COIN", "BB")
        current_time: Current datetime
        counter: Optional trade counter for the day (1-based)
        include_uuid: If True, append a short UUID for guaranteed uniqueness

    Returns:
        Unique position ID string

            'BVP_20260102_153045'
        >>> generate_position_id("COIN", dt, counter=3)
        'COIN_20260102_153045_3'
        >>> generate_position_id("BB", dt, include_uuid=True)
        'BB_20260102_153045_a1b2c3d4'

    Note:
        - Timestamp format ensures chronological sorting
        - Counter is optional and should only be used if strategy tracks daily trades
        - UUID suffix provides guaranteed uniqueness if needed (e.g., for testing)
        - Maximum ID length: ~50 characters with UUID, ~25 without
    """
    # Base format: PREFIX_YYYYMMDD_HHMMSS
    timestamp_str = current_time.strftime("%Y%m%d_%H%M%S")
    position_id = f"{strategy_prefix}_{timestamp_str}"

    # Add counter if provided
    if counter is not None:
        position_id = f"{position_id}_{counter}"

    # Add UUID suffix if requested
    if include_uuid:
        uuid_suffix = uuid.uuid4().hex[:8]
        position_id = f"{position_id}_{uuid_suffix}"

    return position_id
