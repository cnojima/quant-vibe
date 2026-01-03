"""OAuth token management for Schwab API."""

from datetime import datetime
from typing import Optional
import schwabdev
from quant_vibe.utils import now_utc


class TokenManager:
    """Manages OAuth token refresh for Schwab API.

    Attributes:
        refresh_interval_minutes: Minutes between automatic token refreshes
    """

    def __init__(self, client: schwabdev.Client, refresh_interval_minutes: int = 14):
        """Initialize token manager.

        Args:
            client: Schwabdev client instance
            refresh_interval_minutes: Minutes between token refreshes
        """
        self.client = client
        self.refresh_interval_minutes = refresh_interval_minutes
        self.last_refresh: Optional[datetime] = None

    def refresh(self) -> bool:
        """Refresh OAuth token.

        Returns:
            True if refresh successful, False otherwise
        """
        try:
            now = now_utc()
            print(f"\n🔄 [{now.strftime('%Y-%m-%d %H:%M:%S')}] Refreshing Schwab OAuth token...")

            # Call token refresh
            self.client.update_tokens()

            self.last_refresh = now
            print(f"  ✓ Token refresh successful")
            return True

        except Exception as e:
            print(f"  ✗ Token refresh failed: {e}")
            import traceback
            traceback.print_exc()
            return False

    def needs_refresh(self) -> bool:
        """Check if token needs refresh.

        Returns:
            True if token should be refreshed
        """
        if self.last_refresh is None:
            return True

        elapsed_minutes = (now_utc() - self.last_refresh).total_seconds() / 60.0
        return elapsed_minutes >= self.refresh_interval_minutes

    def get_token_age_minutes(self) -> float:
        """Get age of current token in minutes.

        Returns:
            Minutes since last refresh, or 0 if never refreshed
        """
        if self.last_refresh is None:
            return 0.0

        return (now_utc() - self.last_refresh).total_seconds() / 60.0
