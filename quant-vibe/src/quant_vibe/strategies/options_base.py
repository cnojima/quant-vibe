# filepath: /Users/curisu/dev/quant-vibe/src/quant_vibe/strategies/options_base.py
"""Base classes and interfaces for options strategies."""

from typing import List, Optional
from datetime import datetime
from enum import Enum


class OptionType(Enum):
    CALL = 'C'
    PUT = 'P'


class SpreadType(Enum):
    VERTICAL_CALL = 'Vertical Call'
    VERTICAL_PUT = 'Vertical Put'


class OptionLeg:
    """Represents a single leg of an options position."""
    
    def __init__(
        self,
        contract_symbol: str,
        option_type: OptionType,
        strike_price: float,
        expiration_date: datetime,
        quantity: int,
        entry_price: float
    ) -> None:
        self.contract_symbol = contract_symbol
        self.option_type = option_type
        self.strike_price = strike_price
        self.expiration_date = expiration_date
        self.quantity = quantity
        self.entry_price = entry_price


class OptionsPosition:
    """Represents an options position consisting of multiple legs."""
    
    def __init__(
        self,
        position_id: str,
        spread_type: SpreadType,
        legs: List[OptionLeg],
        entry_time: datetime,
        entry_cost: float,
        underlying_price_at_entry: float,
        profit_target: float,
        trailing_stop: float
    ) -> None:
        self.position_id = position_id
        self.spread_type = spread_type
        self.legs = legs
        self.entry_time = entry_time
        self.entry_cost = entry_cost
        self.underlying_price_at_entry = underlying_price_at_entry
        self.profit_target = profit_target
        self.trailing_stop = trailing_stop
        self.exit_time: Optional[datetime] = None
        self.exit_value: Optional[float] = None


class OptionsStrategy:
    """Base class for options trading strategies."""
    
    def __init__(self, name: str) -> None:
        self.name = name
        self.active_position: Optional[OptionsPosition] = None
        self.positions: List[OptionsPosition] = []

    def analyze_market(self, underlying_data, options_data, current_time):
        raise NotImplementedError

    def should_enter(self, underlying_data, options_data, current_time, market_analysis):
        raise NotImplementedError

    def construct_spread(self, underlying_data, options_data, current_time, market_analysis):
        raise NotImplementedError

    def should_exit(self, position, underlying_data, options_data, current_time):
        raise NotImplementedError

    def update_position_value(self, position, options_data):
        raise NotImplementedError

    def close_position(self, position, current_time, exit_reason):
        position.exit_time = current_time
        # Logic to calculate exit value would go here
        position.exit_value = 0  # Placeholder for exit value calculation
