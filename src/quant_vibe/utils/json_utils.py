"""JSON utilities for handling special values and serialization."""

import math
import numpy as np
import pandas as pd
from datetime import date, datetime
from typing import Any, Dict, List, Union


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize an object for JSON serialization by converting
    NaN and Infinity values to None.

    This handles:
    - Python's math.nan and math.inf
    - NumPy's np.nan and np.inf
    - datetime.date and datetime.datetime objects
    - pandas.Timestamp objects
    - Nested dictionaries and lists
    - Mixed data types

    Args:
        obj: The object to sanitize (dict, list, or primitive value)

    Returns:
        The sanitized object safe for JSON serialization

    Examples:
        >>> import math
        >>> sanitize_for_json({"value": math.nan})
        {'value': None}

        >>> sanitize_for_json([1.0, math.inf, -math.inf, math.nan])
        [1.0, None, None, None]

        >>> sanitize_for_json({"nested": {"value": math.nan}})
        {'nested': {'value': None}}
    """
    if isinstance(obj, dict):
        # Recursively sanitize dictionary values
        return {key: sanitize_for_json(value) for key, value in obj.items()}

    elif isinstance(obj, list):
        # Recursively sanitize list items
        return [sanitize_for_json(item) for item in obj]

    elif isinstance(obj, tuple):
        # Convert tuple to list and sanitize
        return [sanitize_for_json(item) for item in obj]

    elif isinstance(obj, float):
        # Check for NaN or Infinity values
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj

    elif isinstance(obj, np.floating):
        # Handle NumPy float types
        if np.isnan(obj) or np.isinf(obj):
            return None
        return float(obj)  # Convert to native Python float

    elif isinstance(obj, np.integer):
        # Handle NumPy integer types
        return int(obj)  # Convert to native Python int

    elif isinstance(obj, np.ndarray):
        # Convert NumPy arrays to lists and sanitize
        return sanitize_for_json(obj.tolist())

    elif isinstance(obj, (pd.Timestamp, datetime, date)):
        # Handle datetime and date objects
        return obj.isoformat()

    elif hasattr(obj, "tolist"):
        # Handle any other array-like objects
        return sanitize_for_json(obj.tolist())

    elif hasattr(obj, "to_dict"):
        # Handle objects with to_dict method
        return sanitize_for_json(obj.to_dict())

    else:
        # Return other types as-is (strings, integers, booleans, None, etc.)
        return obj


def sanitize_dict_for_json(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convenience function to sanitize a dictionary for JSON serialization.

    This is a wrapper around sanitize_for_json that ensures the input is a dict.

    Args:
        data: Dictionary to sanitize

    Returns:
        Sanitized dictionary safe for JSON serialization

    Raises:
        TypeError: If data is not a dictionary

    Examples:
        >>> import math
        >>> sanitize_dict_for_json({"final_capital": math.nan, "sharpe_ratio": 1.5})
        {'final_capital': None, 'sharpe_ratio': 1.5}
    """
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict, got {type(data)}")

    return sanitize_for_json(data)


def sanitize_list_for_json(data: List[Any]) -> List[Any]:
    """
    Convenience function to sanitize a list for JSON serialization.

    This is a wrapper around sanitize_for_json that ensures the input is a list.

    Args:
        data: List to sanitize

    Returns:
        Sanitized list safe for JSON serialization

    Raises:
        TypeError: If data is not a list

    Examples:
        >>> import math
        >>> sanitize_list_for_json([{"value": math.nan}, {"value": 1.0}])
        [{'value': None}, {'value': 1.0}]
    """
    if not isinstance(data, list):
        raise TypeError(f"Expected list, got {type(data)}")

    return sanitize_for_json(data)