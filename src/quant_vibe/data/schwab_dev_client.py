"""
Schwab API Client using schwabdev Library

This module integrates with Schwab's API using the schwabdev library.
Requires Python 3.9+ and OAuth2 authentication.

Documentation: https://github.com/tylerebowers/Schwab-API-Python
GitHub: https://github.com/tylerebowers/Schwab-API-Python

Setup Instructions:
==================
1. Register at https://developer.schwab.com/
2. Create an app and note:
   - API Key (Consumer Key)
   - App Secret (Consumer Secret)
   - Callback/Redirect URL (e.g., https://quantvibe.net:53430/)
3. Add to .env:
   SCHWAB_API_KEY=your_api_key
   SCHWAB_API_SECRET=your_app_secret
   SCHWAB_CALLBACK_URL=https://quantvibe.net:53430/
   SCHWAB_ACCOUNT_NUMBER=your_account_number
"""

import os
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv

# Import schwabdev
import schwabdev
from quant_vibe.utils.timestamp_utils import now_utc

load_dotenv()


class SchwabDevClient:
    """
    Client for Schwab API using schwabdev library with OAuth2.

    This handles automatic token refresh and provides a cleaner interface
    than direct API calls.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        callback_url: Optional[str] = None,
        tokens_db: Optional[str] = None
    ):
        """
        Initialize Schwab client with OAuth2 authentication.

        Args:
            api_key: API key (reads from .env if not provided)
            app_secret: App secret (reads from .env if not provided)
            callback_url: OAuth callback URL (reads from .env if not provided)
            tokens_db: Path to store OAuth tokens in SQLite DB (reads from .env if not provided)
        """
        self.api_key = api_key or os.getenv("SCHWAB_API_KEY")
        self.app_secret = app_secret or os.getenv("SCHWAB_API_SECRET")
        self.callback_url = callback_url or os.getenv("SCHWAB_CALLBACK_URL", "https://quantvibe.net:53430/")
        self.tokens_db = tokens_db or os.getenv("SCHWAB_TOKENS_DB", "./tokens/schwabdev_tokens.db")
        # Don't use plain account number from env - we'll fetch the encrypted hash
        self.account_number = None

        # Ensure token directory exists
        Path(self.tokens_db).parent.mkdir(parents=True, exist_ok=True)

        # Initialize client
        try:
            self.client = schwabdev.Client(
                app_key=self.api_key,
                app_secret=self.app_secret,
                callback_url=self.callback_url,
                tokens_db=self.tokens_db
            )
            print("✓ Schwab client authenticated successfully!")
        except Exception as e:
            print(f"⚠️  Authentication required: {e}")
            print("\nFirst-time setup:")
            print("1. A browser window will open")
            print("2. Log in to Schwab")
            print("3. Authorize the app")
            print("4. You'll be redirected to callback URL")
            print("5. Copy the FULL URL from browser and paste when prompted")
            raise

    def get_quote(self, symbol: str) -> Dict:
        """
        Get real-time quote for a symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Quote data dictionary
        """
        response = self.client.quote(symbol)
        response.raise_for_status()
        return response.json()

    def get_quotes(self, symbols: List[str]) -> Dict:
        """
        Get quotes for multiple symbols.

        Args:
            symbols: List of ticker symbols

        Returns:
            Dictionary of quotes
        """
        response = self.client.quotes(symbols)
        response.raise_for_status()
        return response.json()

    def get_price_history(
        self,
        symbol: str,
        period_type: Optional[str] = None,
        period: Optional[int] = None,
        frequency_type: Optional[str] = None,
        frequency: Optional[int] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Get historical price data.

        Args:
            symbol: Stock ticker
            period_type: PeriodType ('day', 'month', 'year', 'ytd')
            period: Number of periods
            frequency_type: FrequencyType ('minute', 'daily', 'weekly', 'monthly')
            frequency: Frequency value
            start_datetime: Start date/time
            end_datetime: End date/time

        Returns:
            DataFrame with OHLCV data

        Example:
            >>> client = SchwabDevClient()
            >>> # Get 1 year of daily data
            >>> data = client.get_price_history(
            ...     "AAPL",
            ...     period_type="year",
            ...     period=1,
            ...     frequency_type="daily",
            ...     frequency=1
            ... )
        """
        # Use defaults if not specified AND not using date range
        if start_datetime is None and end_datetime is None:
            # Using period-based query
            if period_type is None:
                period_type = "year"
            if period is None:
                period = 1
            if frequency_type is None:
                frequency_type = "daily"
            if frequency is None:
                frequency = 1

            response = self.client.price_history(
                symbol,
                periodType=period_type,
                period=period,
                frequencyType=frequency_type,
                frequency=frequency
            )
        else:
            # Using date range query - don't pass period_type/period
            if frequency_type is None:
                frequency_type = "daily"
            if frequency is None:
                frequency = 1

            # Convert datetime to milliseconds timestamp for Schwab API
            start_ms = None
            end_ms = None

            if start_datetime is not None:
                if isinstance(start_datetime, datetime):
                    start_ms = int(start_datetime.timestamp() * 1000)
                else:
                    raise ValueError(f"start_datetime must be datetime object, got {type(start_datetime)}")

            if end_datetime is not None:
                if isinstance(end_datetime, datetime):
                    end_ms = int(end_datetime.timestamp() * 1000)
                else:
                    raise ValueError(f"end_datetime must be datetime object, got {type(end_datetime)}")

            response = self.client.price_history(
                symbol,
                frequencyType=frequency_type,
                frequency=frequency,
                startDate=start_ms,
                endDate=end_ms
            )
        response.raise_for_status()

        data = response.json()

        # Convert to DataFrame
        if "candles" in data:
            df = pd.DataFrame(data["candles"])

            # Debug: print available columns
            if df.empty:
                print(f"Warning: No candles returned from API")
                print(f"Response data: {data}")
                return pd.DataFrame()

            # Schwab API uses different timestamp field names depending on the endpoint
            # Try 'datetime' first, fall back to other common names
            time_col = None
            for col_name in ['datetime', 'timestamp', 'date']:
                if col_name in df.columns:
                    time_col = col_name
                    break

            if time_col is None:
                raise ValueError(f"No timestamp column found. Available columns: {df.columns.tolist()}")

            df["datetime"] = pd.to_datetime(df[time_col], unit="ms")
            df.set_index("datetime", inplace=True)

            # Rename columns to match our format
            df = df.rename(columns={
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume"
            })

            return df[["Open", "High", "Low", "Close", "Volume"]]

        return pd.DataFrame()

    def get_index_price_history(
        self,
        index_symbol: str,
        start_datetime: datetime,
        end_datetime: datetime,
        frequency_minutes: int = 1
    ) -> pd.DataFrame:
        """
        Get historical price data for an index (SPX, NDX, etc.)

        Schwab index symbols use .X suffix:
        - SPX (S&P 500): $SPX.X
        - NDX (Nasdaq 100): $NDX.X
        - DJX (Dow Jones): $DJX.X

        Args:
            index_symbol: Index symbol (accepts 'SPX', '$SPX', or '$SPX.X')
            start_datetime: Start date/time
            end_datetime: End date/time
            frequency_minutes: Bar frequency in minutes (1, 5, 10, 15, 30)

        Returns:
            DataFrame with OHLCV data, indexed by datetime

        Example:
            >>> client = SchwabDevClient()
            >>> # Get 1-minute SPX data for Dec 23, 2025
            >>> from datetime import datetime
            >>> data = client.get_index_price_history(
            ...     "SPX",  # or "$SPX" or "$SPX.X"
            ...     start_datetime=datetime(2025, 12, 23, 9, 30),
            ...     end_datetime=datetime(2025, 12, 23, 16, 0),
            ...     frequency_minutes=1
            ... )
        """
        # Normalize symbol to Schwab index format: $SYMBOL.X
        # Remove any existing $ prefix and .X suffix, then add them back
        # clean_symbol = index_symbol.strip()
        # if clean_symbol.startswith('$'):
        #     clean_symbol = clean_symbol[1:]
        # if clean_symbol.endswith('.X'):
        #     clean_symbol = clean_symbol[:-2]

        # schwab_symbol = f"${clean_symbol}.X"

        return self.get_price_history(
            # schwab_symbol,
            index_symbol,
            frequency_type="minute",
            frequency=frequency_minutes,
            start_datetime=start_datetime,
            end_datetime=end_datetime
        )

    def get_account(self, include_positions: bool = True) -> Dict:
        """
        Get account information.

        Args:
            include_positions: Whether to include position data (default: True)

        Returns:
            Account details including positions and balances
        """
        if not self.account_number:
            # Get all accounts and use the first one
            response = self.client.account_numbers()
            response.raise_for_status()
            accounts = response.json()
            if accounts:
                self.account_number = accounts[0]['hashValue']

        # Request positions if needed
        if include_positions:
            response = self.client.account_details(
                self.account_number,
                fields="positions"
            )
        else:
            response = self.client.account_details(self.account_number)

        response.raise_for_status()
        return response.json()

    def get_positions(self) -> List[Dict]:
        """
        Get current positions.

        Returns:
            List of position dictionaries
        """
        account = self.get_account()
        if "securitiesAccount" in account:
            return account["securitiesAccount"].get("positions", [])
        return []

    def place_order(
        self,
        symbol: str,
        quantity: int,
        instruction: str,
        order_type: str = "MARKET",
        price: Optional[float] = None
    ) -> Dict:
        """
        Place an order.

        Args:
            symbol: Stock ticker
            quantity: Number of shares
            instruction: 'BUY' or 'SELL'
            order_type: 'MARKET' or 'LIMIT'
            price: Limit price (for LIMIT orders)

        Returns:
            Order confirmation

        Warning:
            Places REAL orders! Schwab does not support paper trading.
        """
        if not self.account_number:
            self.get_account()  # Sets account_number

        # Build order based on type
        order_data = {
            "orderType": order_type,
            "session": "NORMAL",
            "duration": "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": instruction.upper(),
                    "quantity": quantity,
                    "instrument": {
                        "symbol": symbol,
                        "assetType": "EQUITY"
                    }
                }
            ]
        }

        if order_type == "LIMIT" and price is not None:
            order_data["price"] = price

        response = self.client.order_place(self.account_number, order_data)
        response.raise_for_status()

        return {
            "status": "success",
            "order_id": response.headers.get("Location", "").split("/")[-1]
        }

    def get_orders(self, from_date: Optional[datetime] = None) -> List[Dict]:
        """
        Get orders for account.

        Args:
            from_date: Get orders from this date forward

        Returns:
            List of order dictionaries
        """
        if not self.account_number:
            self.get_account()

        if from_date is None:
            from_date = now_utc() - timedelta(days=60)

        response = self.client.account_orders(
            self.account_number,
            fromEnteredTime=from_date.isoformat()
        )
        response.raise_for_status()
        return response.json()

    def update_tokens(self):
        """
        Refresh OAuth tokens.

        This should be called periodically (every 14-20 minutes) during long-running operations.
        """
        self.client.update_tokens_auto()


# Example usage and testing
if __name__ == "__main__":

    print("\n" + "="*70)
    print("SCHWABDEV CLIENT - OAuth2 Integration")
    print("="*70)

    try:
        # Initialize client (will trigger OAuth flow if needed)
        schwab_client = SchwabDevClient()

        # Test 1: Get a quote
        print("\n📊 Test 1: Fetching AAPL quote...")
        quote_data = schwab_client.get_quote("AAPL")
        if "AAPL" in quote_data:
            quote = quote_data["AAPL"]["quote"]
            print(f"   Symbol: {quote.get('symbol', 'N/A')}")
            print(f"   Last Price: ${quote.get('lastPrice', 0):.2f}")
            print(f"   Volume: {quote.get('totalVolume', 0):,}")
            print("   ✓ Quote fetched successfully!")

        # Test 2: Get price history
        print("\n📈 Test 2: Fetching AAPL price history...")
        history = schwab_client.get_price_history(
            "AAPL",
            period_type="month",
            period=1,
            frequency_type="daily",
            frequency=1
        )
        if not history.empty:
            print(f"   ✓ Fetched {len(history)} days of data")
            print(f"   Latest close: ${history['Close'].iloc[-1]:.2f}")

        # Test 3: Get account info
        print("\n💼 Test 3: Fetching account info...")
        account = schwab_client.get_account()
        if "securitiesAccount" in account:
            balances = account["securitiesAccount"]["currentBalances"]
            print(f"   Account Value: ${balances.get('liquidationValue', 0):,.2f}")
            print(f"   Cash: ${balances.get('cashBalance', 0):,.2f}")
            print("   ✓ Account info fetched!")

        print("\n" + "="*70)
        print("✅ schwabdev integration working!")
        print("="*70)
        print("\nToken saved to:", schwab_client.tokens_db)
        print("Future runs will use cached token (no browser needed)")

    except FileNotFoundError:
        print("\n❌ Configuration missing!")
        print("\nAdd to .env:")
        print("  SCHWAB_API_KEY=your_api_key")
        print("  SCHWAB_API_SECRET=your_app_secret")
        print("  SCHWAB_CALLBACK_URL=https://quantvibe.net:53430/")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure you've created an app at developer.schwab.com")
        print("2. Check that API key and secret are correct")
        print("3. Ensure callback URL matches your app settings")
        print("4. First-time setup requires browser authentication")
