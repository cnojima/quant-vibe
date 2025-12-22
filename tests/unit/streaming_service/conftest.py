"""Common fixtures for streaming service tests."""

import pytest
from datetime import datetime
from unittest.mock import Mock


@pytest.fixture
def sample_spxw_quote():
    """Create a sample SPXW option quote."""
    return {
        'timestamp': datetime.now(),
        'symbol': 'SPXW  260121P06200000',
        'bid': 100.0,
        'ask': 101.0,
        'last': 100.5,
        'high': 102.0,
        'low': 99.0,
        'close': 100.5,
        'volume': 1000,
        'open': 100.0,
        'bid_size': 10,
        'ask_size': 15,
        'strike': 6200.0,
        'contract_type': 'P',
        'exp_year': 2026,
        'exp_month': 1,
        'exp_day': 21,
        'iv': 0.15,
        'delta': -0.5,
        'gamma': 0.001,
        'theta': -0.05,
        'vega': 0.10,
        'rho': -0.02,
    }


@pytest.fixture
def sample_call_quote():
    """Create a sample call option quote."""
    return {
        'timestamp': datetime.now(),
        'symbol': 'SPXW  260121C06000000',
        'bid': 50.0,
        'ask': 51.0,
        'last': 50.5,
        'high': 52.0,
        'low': 49.0,
        'close': 50.5,
        'volume': 500,
        'open': 50.0,
        'bid_size': 5,
        'ask_size': 8,
        'strike': 6000.0,
        'contract_type': 'C',
        'exp_year': 2026,
        'exp_month': 1,
        'exp_day': 21,
        'iv': 0.18,
        'delta': 0.6,
        'gamma': 0.002,
        'theta': -0.08,
        'vega': 0.12,
        'rho': 0.03,
    }


@pytest.fixture
def mock_schwab_client():
    """Create a mock schwabdev client."""
    client = Mock()
    client.update_tokens = Mock()
    client.quote = Mock()
    client.option_chains = Mock()
    return client


@pytest.fixture
def mock_timescale_store():
    """Create a mock TimescaleStore."""
    store = Mock()
    store.bulk_insert_option_bars = Mock(return_value=1)
    store.close = Mock()
    return store


@pytest.fixture
def mock_enricher():
    """Create a mock OptionContractEnricher."""
    enricher = Mock()
    enricher.enrich_quote = Mock(side_effect=lambda q: q)
    enricher.get_cache_stats = Mock(return_value={
        'contracts_cached': 100,
        'cache_age_minutes': 5.0
    })
    enricher.refresh_contract_details = Mock()
    return enricher


@pytest.fixture
def levelone_options_message():
    """Create a sample LEVELONE_OPTIONS stream message."""
    return {
        'data': [{
            'service': 'LEVELONE_OPTIONS',
            'content': [{
                'key': 'SPXW  260121P06200000',
                '2': 100.0,   # bid
                '3': 101.0,   # ask
                '4': 100.5,   # last
                '5': 102.0,   # high
                '6': 99.0,    # low
                '7': 100.5,   # close
                '8': 1000,    # volume
                '10': 0.15,   # IV
                '15': 100.0,  # open
                '16': 10,     # bid_size
                '17': 15,     # ask_size
                '20': 6200.0, # strike
                '21': 'P',    # contract_type
                '12': 2026,   # exp_year
                '23': 1,      # exp_month
                '26': 21,     # exp_day
                '28': -0.5,   # delta
                '29': 0.001,  # gamma
                '30': -0.05,  # theta
                '31': 0.10,   # vega
                '32': -0.02,  # rho
            }]
        }]
    }


@pytest.fixture
def option_chain_response():
    """Create a sample option chain API response."""
    return {
        'callExpDateMap': {
            '2026-01-21:5': {
                '6000.0': [
                    {'symbol': 'SPXW  260121C06000000'}
                ],
                '6100.0': [
                    {'symbol': 'SPXW  260121C06100000'}
                ]
            }
        },
        'putExpDateMap': {
            '2026-01-21:5': {
                '6000.0': [
                    {'symbol': 'SPXW  260121P06000000'}
                ],
                '6100.0': [
                    {'symbol': 'SPXW  260121P06100000'}
                ]
            }
        }
    }
