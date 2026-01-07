"""Unit tests for TokenManager."""

import pytest
from unittest.mock import Mock
from datetime import datetime, timedelta
from streaming_service.token_manager import TokenManager


class TestTokenManager:
    """Test cases for TokenManager class."""

    @pytest.fixture
    def mock_client(self):
        """Create a mock schwabdev client."""
        client = Mock()
        client.update_tokens = Mock()
        return client

    @pytest.fixture
    def token_manager(self, mock_client):
        """Create a TokenManager instance with mock client."""
        return TokenManager(mock_client, refresh_interval_minutes=14)

    def test_initialization(self, mock_client):
        """Test TokenManager initialization."""
        tm = TokenManager(mock_client, refresh_interval_minutes=10)

        assert tm.client == mock_client
        assert tm.refresh_interval_minutes == 10
        assert tm.last_refresh is None

    def test_initialization_default_interval(self, mock_client):
        """Test TokenManager initialization with default interval."""
        tm = TokenManager(mock_client)

        assert tm.refresh_interval_minutes == 14

    def test_refresh_success(self, token_manager, mock_client, capsys):
        """Test successful token refresh."""
        # Mock successful refresh
        mock_client.update_tokens.return_value = None

        result = token_manager.refresh()

        assert result is True
        assert token_manager.last_refresh is not None
        assert isinstance(token_manager.last_refresh, datetime)

        # Check console output
        captured = capsys.readouterr()
        assert "Refreshing Schwab OAuth token" in captured.out
        assert "Token refresh successful" in captured.out

        # Verify update_tokens was called
        mock_client.update_tokens.assert_called_once()

    def test_refresh_failure(self, token_manager, mock_client, capsys):
        """Test token refresh failure."""
        # Mock failed refresh
        mock_client.update_tokens.side_effect = Exception("API Error")

        result = token_manager.refresh()

        assert result is False

        # last_refresh should not be updated on failure
        assert token_manager.last_refresh is None

        # Check console output
        captured = capsys.readouterr()
        assert "Refreshing Schwab OAuth token" in captured.out
        assert "Token refresh failed" in captured.out
        assert "API Error" in captured.out

    def test_refresh_updates_timestamp(self, token_manager, mock_client):
        """Test that refresh updates last_refresh timestamp."""
        before = datetime.now()
        token_manager.refresh()
        after = datetime.now()

        assert token_manager.last_refresh is not None
        assert before <= token_manager.last_refresh <= after

    def test_needs_refresh_never_refreshed(self, token_manager):
        """Test needs_refresh returns True when never refreshed."""
        assert token_manager.last_refresh is None
        assert token_manager.needs_refresh() is True

    def test_needs_refresh_recently_refreshed(self, token_manager):
        """Test needs_refresh returns False when recently refreshed."""
        # Simulate recent refresh
        token_manager.last_refresh = datetime.now()

        assert token_manager.needs_refresh() is False

    def test_needs_refresh_old_token(self, token_manager):
        """Test needs_refresh returns True when token is old."""
        # Simulate old refresh (15 minutes ago, interval is 14)
        token_manager.last_refresh = datetime.now() - timedelta(minutes=15)

        assert token_manager.needs_refresh() is True

    def test_needs_refresh_exact_threshold(self, token_manager):
        """Test needs_refresh at exact threshold."""
        # Simulate refresh exactly 14 minutes ago
        token_manager.last_refresh = datetime.now() - timedelta(minutes=14)

        # Should need refresh (>= threshold)
        assert token_manager.needs_refresh() is True

    def test_needs_refresh_just_under_threshold(self, token_manager):
        """Test needs_refresh just under threshold."""
        # Simulate refresh 13.9 minutes ago
        token_manager.last_refresh = datetime.now() - timedelta(minutes=13.9)

        # Should not need refresh yet
        assert token_manager.needs_refresh() is False

    def test_get_token_age_minutes_never_refreshed(self, token_manager):
        """Test get_token_age_minutes when never refreshed."""
        assert token_manager.get_token_age_minutes() == 0.0

    def test_get_token_age_minutes_recently_refreshed(self, token_manager):
        """Test get_token_age_minutes for recent refresh."""
        token_manager.last_refresh = datetime.now()

        age = token_manager.get_token_age_minutes()

        # Should be very close to 0
        assert 0.0 <= age < 0.1

    def test_get_token_age_minutes_old_token(self, token_manager):
        """Test get_token_age_minutes for old token."""
        # Simulate refresh 10 minutes ago
        token_manager.last_refresh = datetime.now() - timedelta(minutes=10)

        age = token_manager.get_token_age_minutes()

        # Should be close to 10 minutes (with small tolerance)
        assert 9.9 <= age <= 10.1

    def test_multiple_refreshes(self, token_manager, mock_client):
        """Test multiple successful refreshes."""
        # First refresh
        token_manager.refresh()
        first_refresh = token_manager.last_refresh

        # Wait a bit (simulate)
        token_manager.last_refresh = datetime.now() - timedelta(minutes=15)

        # Second refresh
        token_manager.refresh()
        second_refresh = token_manager.last_refresh

        assert second_refresh > first_refresh
        assert mock_client.update_tokens.call_count == 2

    def test_refresh_after_failure(self, token_manager, mock_client):
        """Test that refresh can succeed after a failure."""
        # First refresh fails
        mock_client.update_tokens.side_effect = Exception("API Error")
        result1 = token_manager.refresh()
        assert result1 is False

        # Second refresh succeeds
        mock_client.update_tokens.side_effect = None
        result2 = token_manager.refresh()
        assert result2 is True
        assert token_manager.last_refresh is not None

    def test_custom_refresh_interval(self, mock_client):
        """Test TokenManager with custom refresh interval."""
        tm = TokenManager(mock_client, refresh_interval_minutes=5)

        # Simulate refresh 6 minutes ago
        tm.last_refresh = datetime.now() - timedelta(minutes=6)

        # Should need refresh (> 5 minutes)
        assert tm.needs_refresh() is True

    def test_refresh_console_output_format(self, token_manager, mock_client, capsys):
        """Test that refresh console output has correct format."""
        token_manager.refresh()

        captured = capsys.readouterr()
        output = captured.out

        # Should have timestamp
        assert "[20" in output  # Year starts with 20
        assert "]" in output

        # Should have emoji
        assert "🔄" in output

        # Should have success indicator
        assert "✓" in output

    def test_refresh_exception_handling(self, token_manager, mock_client, capsys):
        """Test that refresh handles various exceptions gracefully."""
        # Test different exception types
        exceptions = [
            Exception("Generic error"),
            ValueError("Invalid value"),
            RuntimeError("Runtime error"),
            KeyError("Missing key"),
        ]

        for exc in exceptions:
            mock_client.update_tokens.side_effect = exc
            result = token_manager.refresh()

            assert result is False
            captured = capsys.readouterr()
            assert "Token refresh failed" in captured.out

    def test_token_age_increases_over_time(self, token_manager):
        """Test that token age increases as time passes."""
        token_manager.last_refresh = datetime.now() - timedelta(minutes=5)

        age1 = token_manager.get_token_age_minutes()

        # Simulate 2 more minutes passing
        token_manager.last_refresh = datetime.now() - timedelta(minutes=7)

        age2 = token_manager.get_token_age_minutes()

        assert age2 > age1

    def test_refresh_state_persistence(self, token_manager, mock_client):
        """Test that refresh state persists across operations."""
        # Refresh
        token_manager.refresh()
        refresh_time = token_manager.last_refresh

        # Check needs_refresh (should not modify state)
        token_manager.needs_refresh()
        assert token_manager.last_refresh == refresh_time

        # Check get_token_age_minutes (should not modify state)
        token_manager.get_token_age_minutes()
        assert token_manager.last_refresh == refresh_time
