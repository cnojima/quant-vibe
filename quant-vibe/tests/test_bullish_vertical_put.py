from datetime import datetime, timedelta
import pandas as pd
import pytest

from src.quant_vibe.strategies.bullish_vertical_put import BullishVerticalPutStrategy
from src.quant_vibe.strategies.options_base import OptionsPosition, OptionLeg, OptionType, SpreadType

@pytest.fixture
def setup_strategy():
    strategy = BullishVerticalPutStrategy()
    return strategy

def test_analyze_market_bullish(setup_strategy):
    strategy = setup_strategy
    current_time = datetime(2023, 10, 1, 10, 0)
    underlying_data = pd.DataFrame({
        'Close': [4000, 4010, 4020],
        'High': [4010, 4020, 4030],
        'Low': [3990, 4000, 4010]
    }, index=pd.date_range(start='2023-10-01 09:30', periods=3, freq='T'))

    options_data = pd.DataFrame({
        'expiration_date': [datetime(2023, 10, 15)] * 3,
        'strike_price': [3980, 4000, 4020],
        'option_type': ['P', 'P', 'P'],
        'mark': [20, 15, 10]
    })

    analysis = strategy.analyze_market(underlying_data, options_data, current_time)

    assert analysis['direction'] == 'bullish'
    assert analysis['pullback_signal'] is True

def test_should_enter(setup_strategy):
    strategy = setup_strategy
    current_time = datetime(2023, 10, 1, 10, 0)
    underlying_data = pd.DataFrame({
        'Close': [4000, 4010, 4020],
        'High': [4010, 4020, 4030],
        'Low': [3990, 4000, 4010]
    }, index=pd.date_range(start='2023-10-01 09:30', periods=3, freq='T'))

    options_data = pd.DataFrame({
        'expiration_date': [datetime(2023, 10, 15)] * 3,
        'strike_price': [3980, 4000, 4020],
        'option_type': ['P', 'P', 'P'],
        'mark': [20, 15, 10]
    })

    market_analysis = strategy.analyze_market(underlying_data, options_data, current_time)
    strategy.reset_daily_state()
    strategy.should_enter(underlying_data, options_data, current_time, market_analysis)

    assert strategy.should_enter(underlying_data, options_data, current_time, market_analysis) is True

def test_construct_spread(setup_strategy):
    strategy = setup_strategy
    current_time = datetime(2023, 10, 1, 10, 0)
    underlying_data = pd.DataFrame({
        'Close': [4000],
        'High': [4010],
        'Low': [3990]
    }, index=pd.date_range(start='2023-10-01 09:30', periods=1, freq='T'))

    options_data = pd.DataFrame({
        'expiration_date': [datetime(2023, 10, 15)] * 3,
        'strike_price': [3980, 4000, 4020],
        'option_type': ['P', 'P', 'P'],
        'mark': [20, 15, 10]
    })

    market_analysis = strategy.analyze_market(underlying_data, options_data, current_time)
    position = strategy.construct_spread(underlying_data, options_data, current_time, market_analysis)

    assert position is not None
    assert len(position.legs) == 2
    assert position.spread_type == SpreadType.VERTICAL_PUT

def test_should_exit(setup_strategy):
    strategy = setup_strategy
    current_time = datetime(2023, 10, 1, 10, 0)
    position = OptionsPosition(
        position_id='test_position',
        spread_type=SpreadType.VERTICAL_PUT,
        legs=[
            OptionLeg(contract_symbol='PUT1', option_type=OptionType.PUT, strike_price=3980, expiration_date=datetime(2023, 10, 15), quantity=1, entry_price=20),
            OptionLeg(contract_symbol='PUT2', option_type=OptionType.PUT, strike_price=4000, expiration_date=datetime(2023, 10, 15), quantity=-1, entry_price=15)
        ],
        entry_time=current_time,
        entry_cost=500,
        underlying_price_at_entry=4000,
        profit_target=0.5,
        trailing_stop=0.05
    )

    underlying_data = pd.DataFrame({
        'Close': [4000, 4050],
        'High': [4010, 4060],
        'Low': [3990, 4000]
    }, index=pd.date_range(start='2023-10-01 09:30', periods=2, freq='T'))

    options_data = pd.DataFrame({
        'expiration_date': [datetime(2023, 10, 15)] * 3,
        'strike_price': [3980, 4000, 4020],
        'option_type': ['P', 'P', 'P'],
        'mark': [20, 15, 10]
    })

    should_exit, exit_reason = strategy.should_exit(position, underlying_data, options_data, current_time)

    assert should_exit is False
    assert exit_reason is None