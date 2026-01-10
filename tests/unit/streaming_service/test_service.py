"""Unit tests for StreamingService."""

import pytest
import json
from unittest.mock import Mock, patch
from datetime import datetime
from streaming_service.service import StreamingService
from streaming_service.config import StreamingConfig


class TestStreamingService:
    """Test cases for StreamingService class."""

    @pytest.fixture
    def mock_env(self, monkeypatch):
        """Mock environment variables."""
        monkeypatch.setenv("SCHWAB_API_KEY", "test_key")
        monkeypatch.setenv("SCHWAB_API_SECRET", "test_secret")
        monkeypatch.setenv("SCHWAB_CALLBACK_URL", "https://test.com")

    @pytest.fixture
    def mock_dependencies(self):
        """Mock all external dependencies."""
        with patch('streaming_service.service.schwabdev') as mock_schwabdev, \
             patch('streaming_service.service.TimescaleStore') as mock_ts, \
             patch('streaming_service.service.OptionContractEnricher') as mock_enricher:

            # Mock schwabdev client
            mock_client = Mock()
            mock_stream = Mock()
            mock_schwabdev.Client.return_value = mock_client
            mock_schwabdev.Stream.return_value = mock_stream

            # Mock TimescaleStore
            mock_store = Mock()
            mock_ts.return_value = mock_store

            # Mock enricher
            mock_enrich = Mock()
            mock_enrich.get_cache_stats.return_value = {
                'contracts_cached': 100,
                'cache_age_minutes': 5.0
            }
            mock_enricher.return_value = mock_enrich

            yield {
                'client': mock_client,
                'stream': mock_stream,
                'store': mock_store,
                'enricher': mock_enrich
            }

    @pytest.fixture
    def service(self, mock_env, mock_dependencies):
        """Create a StreamingService instance with mocked dependencies."""
        config = StreamingConfig(max_dte=7, min_dte=0)
        return StreamingService(config)

    def test_initialization(self, mock_env, mock_dependencies):
        """Test StreamingService initialization."""
        config = StreamingConfig(max_dte=7)
        service = StreamingService(config)

        assert service.config.max_dte == 7
        assert service.message_count == 0
        assert service.contracts_subscribed == []
        assert service.schwab_client is not None
        assert service.streamer is not None
        assert service.ts_store is not None
        assert service.token_manager is not None
        assert service.aggregator is not None
        assert service.enricher is not None

    def test_initialization_default_config(self, mock_env, mock_dependencies):
        """Test StreamingService initialization with default config."""
        service = StreamingService()

        assert service.config.max_dte == 45
        assert service.config.min_dte == 0

    def test_get_spx_price_success(self, service, mock_dependencies, capsys):
        """Test successful SPX price fetch."""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "$SPX": {
                "quote": {
                    "lastPrice": 6050.25
                }
            }
        }
        mock_dependencies['client'].quote.return_value = mock_response

        price = service._get_spx_price()

        assert price == 6050.25
        captured = capsys.readouterr()
        assert "SPX price: $6050.25" in captured.out

    def test_get_spx_price_api_error(self, service, mock_dependencies, capsys):
        """Test SPX price fetch with API error."""
        # Mock error response
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_dependencies['client'].quote.return_value = mock_response

        price = service._get_spx_price()

        assert price == 6000.0  # Default
        captured = capsys.readouterr()
        assert "SPX quote API error" in captured.out

    def test_get_spx_price_exception(self, service, mock_dependencies):
        """Test SPX price fetch with exception."""
        # Mock exception
        mock_dependencies['client'].quote.side_effect = Exception("Network error")

        price = service._get_spx_price()

        assert price == 6000.0  # Default

    def test_get_spx_price_missing_data(self, service, mock_dependencies):
        """Test SPX price fetch with missing data in response."""
        # Mock response without $SPX key
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}
        mock_dependencies['client'].quote.return_value = mock_response

        price = service._get_spx_price()

        assert price == 6000.0  # Default

    def test_get_spxw_contracts_success(self, service, mock_dependencies):
        """Test successful SPXW contract fetching."""
        # Mock SPX quote
        mock_quote_response = Mock()
        mock_quote_response.status_code = 200
        mock_quote_response.json.return_value = {
            "$SPX": {"quote": {"lastPrice": 6000.0}}
        }

        # Mock option chain
        mock_chain_response = Mock()
        mock_chain_response.status_code = 200
        today = datetime.now().date()
        exp_date = today.replace(day=today.day + 5)
        mock_chain_response.json.return_value = {
            'callExpDateMap': {
                f'{exp_date}:5': {
                    '5900.0': [
                        {'symbol': 'SPXW  251225C05900000'}
                    ],
                    '6000.0': [
                        {'symbol': 'SPXW  251225C06000000'}
                    ]
                }
            },
            'putExpDateMap': {
                f'{exp_date}:5': {
                    '6000.0': [
                        {'symbol': 'SPXW  251225P06000000'}
                    ]
                }
            }
        }

        mock_dependencies['client'].quote.return_value = mock_quote_response
        mock_dependencies['client'].option_chains.return_value = mock_chain_response

        contracts = service.get_spxw_contracts()

        assert len(contracts) == 3
        assert 'SPXW  251225C05900000' in contracts
        assert 'SPXW  251225C06000000' in contracts
        assert 'SPXW  251225P06000000' in contracts

    def test_get_spxw_contracts_filters_by_dte(self, service, mock_dependencies):
        """Test that contracts are filtered by DTE range."""
        service.config.min_dte = 3
        service.config.max_dte = 7

        # Mock responses
        mock_quote_response = Mock()
        mock_quote_response.status_code = 200
        mock_quote_response.json.return_value = {
            "$SPX": {"quote": {"lastPrice": 6000.0}}
        }

        today = datetime.now().date()
        exp_date_valid = today.replace(day=today.day + 5)  # 5 DTE (in range)
        exp_date_too_soon = today.replace(day=today.day + 2)  # 2 DTE (out of range)
        exp_date_too_far = today.replace(day=today.day + 10)  # 10 DTE (out of range)

        mock_chain_response = Mock()
        mock_chain_response.status_code = 200
        mock_chain_response.json.return_value = {
            'callExpDateMap': {
                f'{exp_date_valid}:5': {
                    '6000.0': [{'symbol': 'SPXW_VALID'}]
                },
                f'{exp_date_too_soon}:2': {
                    '6000.0': [{'symbol': 'SPXW_TOO_SOON'}]
                },
                f'{exp_date_too_far}:10': {
                    '6000.0': [{'symbol': 'SPXW_TOO_FAR'}]
                }
            },
            'putExpDateMap': {}
        }

        mock_dependencies['client'].quote.return_value = mock_quote_response
        mock_dependencies['client'].option_chains.return_value = mock_chain_response

        contracts = service.get_spxw_contracts()

        assert len(contracts) == 1
        assert 'SPXW_VALID' in contracts
        assert 'SPXW_TOO_SOON' not in contracts
        assert 'SPXW_TOO_FAR' not in contracts

    def test_get_spxw_contracts_filters_by_strike(self, service, mock_dependencies):
        """Test that contracts are filtered by strike range."""
        service.config.strike_range_pct = 0.05  # ±5%

        # Mock responses
        mock_quote_response = Mock()
        mock_quote_response.status_code = 200
        mock_quote_response.json.return_value = {
            "$SPX": {"quote": {"lastPrice": 6000.0}}
        }

        today = datetime.now().date()
        exp_date = today.replace(day=today.day + 5)

        # Strikes: 5700 (out), 5900 (in), 6000 (in), 6100 (in), 6400 (out)
        # Range: 6000 * 0.95 = 5700 to 6000 * 1.05 = 6300
        mock_chain_response = Mock()
        mock_chain_response.status_code = 200
        mock_chain_response.json.return_value = {
            'callExpDateMap': {
                f'{exp_date}:5': {
                    '5700.0': [{'symbol': 'SPXW_TOO_LOW'}],
                    '5900.0': [{'symbol': 'SPXW_IN_RANGE_1'}],
                    '6000.0': [{'symbol': 'SPXW_IN_RANGE_2'}],
                    '6100.0': [{'symbol': 'SPXW_IN_RANGE_3'}],
                    '6400.0': [{'symbol': 'SPXW_TOO_HIGH'}],
                }
            },
            'putExpDateMap': {}
        }

        mock_dependencies['client'].quote.return_value = mock_quote_response
        mock_dependencies['client'].option_chains.return_value = mock_chain_response

        contracts = service.get_spxw_contracts()

        assert 'SPXW_IN_RANGE_1' in contracts
        assert 'SPXW_IN_RANGE_2' in contracts
        assert 'SPXW_IN_RANGE_3' in contracts
        assert 'SPXW_TOO_LOW' not in contracts
        assert 'SPXW_TOO_HIGH' not in contracts

    def test_get_spxw_contracts_api_error(self, service, mock_dependencies, capsys):
        """Test contract fetching with API error."""
        # Mock successful quote
        mock_quote_response = Mock()
        mock_quote_response.status_code = 200
        mock_quote_response.json.return_value = {
            "$SPX": {"quote": {"lastPrice": 6000.0}}
        }

        # Mock error response for option chains
        mock_chain_response = Mock()
        mock_chain_response.status_code = 500
        mock_chain_response.text = "Server Error"

        mock_dependencies['client'].quote.return_value = mock_quote_response
        mock_dependencies['client'].option_chains.return_value = mock_chain_response

        contracts = service.get_spxw_contracts()

        assert contracts == []
        captured = capsys.readouterr()
        assert "API Error: HTTP 500" in captured.out

    def test_handle_message_level_one_options(self, service, mock_dependencies):
        """Test handling LEVELONE_OPTIONS message."""
        message = {
            'data': [{
                'service': 'LEVELONE_OPTIONS',
                'content': [{
                    'key': 'SPXW  260121P06200000',
                    '2': 100.0,  # bid
                    '3': 101.0,  # ask
                    '4': 100.5,  # last
                    '8': 1000,   # volume
                    '20': 6200.0,  # strike
                    '21': 'P',   # contract type
                }]
            }]
        }

        # Mock enricher
        mock_dependencies['enricher'].enrich_quote.side_effect = lambda q: q

        service.handle_message(json.dumps(message))

        assert service.message_count == 1
        assert service.aggregator.get_buffered_symbol_count() == 1

    def test_handle_message_increments_counter(self, service, mock_dependencies):
        """Test that message counter increments."""
        message = {'data': []}

        service.handle_message(json.dumps(message))
        assert service.message_count == 1

        service.handle_message(json.dumps(message))
        assert service.message_count == 2

    def test_handle_message_triggers_flush(self, service, mock_dependencies):
        """Test that message handling triggers flush when ready."""
        message = {
            'data': [{
                'service': 'LEVELONE_OPTIONS',
                'content': [{
                    'key': 'SPXW  260121P06200000',
                    '4': 100.5,
                }]
            }]
        }

        # Mock enricher
        mock_dependencies['enricher'].enrich_quote.side_effect = lambda q: q

        # Set aggregator to need flush
        service.aggregator.last_flush_time = datetime.now()
        service.aggregator.aggregate_interval = 0  # Immediate flush

        # Mock bulk insert
        mock_dependencies['store'].bulk_insert_option_bars.return_value = 1

        service.handle_message(json.dumps(message))

        # Verify flush was called (bulk_insert should have been called)
        mock_dependencies['store'].bulk_insert_option_bars.assert_called_once()

    def test_handle_message_invalid_json(self, service, mock_dependencies):
        """Test handling invalid JSON message."""
        message = "invalid json {"

        # Should not raise exception
        service.handle_message(message)

        # Message count should still increment (attempt was made)
        assert service.message_count == 1

    def test_handle_message_empty_content(self, service, mock_dependencies):
        """Test handling message with empty content."""
        message = {
            'data': [{
                'service': 'LEVELONE_OPTIONS',
                'content': []
            }]
        }

        service.handle_message(json.dumps(message))

        assert service.message_count == 1
        assert service.aggregator.get_buffered_symbol_count() == 0

    def test_handle_message_enrichment(self, service, mock_dependencies):
        """Test that quotes are enriched."""
        message = {
            'data': [{
                'service': 'LEVELONE_OPTIONS',
                'content': [{
                    'key': 'SPXW  260121P06200000',
                    '4': 100.5,
                }]
            }]
        }

        # Mock enricher to add data
        def enrich(quote):
            quote['strike'] = 6200.0
            quote['delta'] = -0.5
            return quote

        mock_dependencies['enricher'].enrich_quote.side_effect = enrich

        service.handle_message(json.dumps(message))

        # Verify enricher was called
        mock_dependencies['enricher'].enrich_quote.assert_called_once()

    def test_flush_bars_success(self, service, mock_dependencies, capsys):
        """Test successful bar flushing."""
        # Add quote to aggregator
        quote = {
            'symbol': 'SPXW  260121P06200000',
            'last': 100.5,
            'bid': 100.0,
            'ask': 101.0,
        }
        service.aggregator.add_quote(quote)

        # Mock successful insert
        mock_dependencies['store'].bulk_insert_option_bars.return_value = 1

        service._flush_bars()

        mock_dependencies['store'].bulk_insert_option_bars.assert_called_once()

        captured = capsys.readouterr()
        assert "Inserted 1 bars" in captured.out

    def test_flush_bars_database_error(self, service, mock_dependencies, capsys):
        """Test bar flushing with database error."""
        # Add quote
        quote = {
            'symbol': 'SPXW  260121P06200000',
            'last': 100.5,
        }
        service.aggregator.add_quote(quote)

        # Mock database error
        mock_dependencies['store'].bulk_insert_option_bars.side_effect = Exception("DB Error")

        service._flush_bars()

        captured = capsys.readouterr()
        assert "Database error" in captured.out

    def test_flush_bars_empty_buffer(self, service, mock_dependencies):
        """Test flushing with empty buffer."""
        service._flush_bars()

        # Should not call database
        mock_dependencies['store'].bulk_insert_option_bars.assert_not_called()

    def test_get_buffered_symbol_count(self, service, mock_dependencies):
        """Test getting buffered symbol count."""
        assert service.aggregator.get_buffered_symbol_count() == 0

        quote = {'symbol': 'SPXW  260121P06200000', 'last': 100.5}
        service.aggregator.add_quote(quote)

        assert service.aggregator.get_buffered_symbol_count() == 1

    def test_stop_flushes_data(self, service, mock_dependencies):
        """Test that stop() flushes remaining data."""
        # Add quote
        quote = {'symbol': 'SPXW  260121P06200000', 'last': 100.5}
        service.aggregator.add_quote(quote)

        # Mock successful insert
        mock_dependencies['store'].bulk_insert_option_bars.return_value = 1

        service.stop()

        # Should have flushed
        mock_dependencies['store'].bulk_insert_option_bars.assert_called_once()

    def test_stop_closes_resources(self, service, mock_dependencies):
        """Test that stop() closes all resources."""
        service.stop()

        # Should close database
        mock_dependencies['store'].close.assert_called_once()

        # Should stop streamer
        mock_dependencies['stream'].stop.assert_called_once()

    def test_message_count_tracking(self, service, mock_dependencies):
        """Test message count tracking."""
        assert service.message_count == 0

        message = {'data': []}

        service.handle_message(json.dumps(message))
        assert service.message_count == 1

        service.handle_message(json.dumps(message))
        service.handle_message(json.dumps(message))
        assert service.message_count == 3

    def test_subscribe_to_contracts_single_batch(self, service, mock_dependencies):
        """Test subscribing to contracts in single batch."""
        contracts = ['SPXW1', 'SPXW2', 'SPXW3']

        service._subscribe_to_contracts(contracts)

        # Should call streamer.send once
        assert mock_dependencies['stream'].send.call_count == 1

    def test_subscribe_to_contracts_multiple_batches(self, service, mock_dependencies):
        """Test subscribing to contracts in multiple batches."""
        # Create more contracts than max per subscription
        service.config.max_symbols_per_subscription = 2
        contracts = ['SPXW1', 'SPXW2', 'SPXW3', 'SPXW4', 'SPXW5']

        service._subscribe_to_contracts(contracts)

        # Should call streamer.send 3 times (2+2+1)
        assert mock_dependencies['stream'].send.call_count == 3
