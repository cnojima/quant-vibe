"""
Schwab API Client using schwab-py Library

This module integrates with Schwab's API using the official schwab-py library.
Requires Python 3.10+ and OAuth2 authentication.

Documentation: https://schwab-py.readthedocs.io/
GitHub: https://github.com/alexgolec/schwab-py

Setup Instructions:
==================
1. Register at https://developer.schwab.com/
2. Create an app and note:
   - API Key (Consumer Key)
   - App Secret (Consumer Secret)
   - Callback/Redirect URL (e.g., https://127.0.0.1:8182/)
3. Add to .env:
   SCHWAB_API_KEY=your_api_key
   SCHWAB_API_SECRET=your_app_secret
   SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
   SCHWAB_TOKEN_PATH=./tokens/schwab_token.json
   SCHWAB_ACCOUNT_NUMBER=your_account_number
"""

import os
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv

# Import schwab-py
from schwab import auth, client
from schwab.client import Client

load_dotenv()


class SchwabPyClient:
    """
    Client for Schwab API using schwab-py library with OAuth2.
    
    This handles automatic token refresh and provides a cleaner interface
    than direct API calls.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        app_secret: Optional[str] = None,
        callback_url: Optional[str] = None,
        token_path: Optional[str] = None
    ):
        """
        Initialize Schwab client with OAuth2 authentication.
        
        Args:
            api_key: API key (reads from .env if not provided)
            app_secret: App secret (reads from .env if not provided)
            callback_url: OAuth callback URL (reads from .env if not provided)
            token_path: Path to store OAuth token (reads from .env if not provided)
        """
        self.api_key = api_key or os.getenv("SCHWAB_API_KEY")
        self.app_secret = app_secret or os.getenv("SCHWAB_API_SECRET")
        self.callback_url = callback_url or os.getenv("SCHWAB_CALLBACK_URL", "https://127.0.0.1:8182/")
        self.token_path = token_path or os.getenv("SCHWAB_TOKEN_PATH", "./tokens/schwab_token.json")
        # Don't use plain account number from env - we'll fetch the encrypted hash
        self.account_number = None
        
        # Ensure token directory exists
        Path(self.token_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize client using easy_client (handles OAuth flow)
        try:
            self.client = auth.easy_client(
                api_key=self.api_key,
                app_secret=self.app_secret,
                callback_url=self.callback_url,
                token_path=self.token_path
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
        response = self.client.get_quote(symbol)
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
        response = self.client.get_quotes(symbols)
        response.raise_for_status()
        return response.json()
    
    def get_price_history(
        self,
        symbol: str,
        period_type: Optional[client.Client.PriceHistory.PeriodType] = None,
        period: Optional[client.Client.PriceHistory.Period] = None,
        frequency_type: Optional[client.Client.PriceHistory.FrequencyType] = None,
        frequency: Optional[client.Client.PriceHistory.Frequency] = None,
        start_datetime: Optional[datetime] = None,
        end_datetime: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Get historical price data.
        
        Args:
            symbol: Stock ticker
            period_type: PeriodType (DAY, MONTH, YEAR, YTD)
            period: Number of periods
            frequency_type: FrequencyType (MINUTE, DAILY, WEEKLY, MONTHLY)
            frequency: Frequency value
            start_datetime: Start date/time
            end_datetime: End date/time
            
        Returns:
            DataFrame with OHLCV data
            
        Example:
            >>> client = SchwabPyClient()
            >>> # Get 1 year of daily data
            >>> data = client.get_price_history(
            ...     "AAPL",
            ...     period_type=Client.PriceHistory.PeriodType.YEAR,
            ...     period=Client.PriceHistory.Period.ONE_YEAR,
            ...     frequency_type=Client.PriceHistory.FrequencyType.DAILY,
            ...     frequency=Client.PriceHistory.Frequency.DAILY
            ... )
        """
        # Use defaults if not specified
        if period_type is None:
            period_type = client.Client.PriceHistory.PeriodType.YEAR
        if period is None:
            period = client.Client.PriceHistory.Period.ONE_YEAR
        if frequency_type is None:
            frequency_type = client.Client.PriceHistory.FrequencyType.DAILY
        if frequency is None:
            frequency = client.Client.PriceHistory.Frequency.DAILY
        
        response = self.client.get_price_history(
            symbol,
            period_type=period_type,
            period=period,
            frequency_type=frequency_type,
            frequency=frequency,
            start_datetime=start_datetime,
            end_datetime=end_datetime
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Convert to DataFrame
        if "candles" in data:
            df = pd.DataFrame(data["candles"])
            df["datetime"] = pd.to_datetime(df["datetime"], unit="ms")
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
            response = self.client.get_account_numbers()
            response.raise_for_status()
            accounts = response.json()
            if accounts:
                self.account_number = accounts[0]['hashValue']
        
        # Request positions if needed
        if include_positions:
            response = self.client.get_account(
                self.account_number,
                fields=client.Client.Account.Fields.POSITIONS
            )
        else:
            response = self.client.get_account(self.account_number)
        
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
        
        from schwab.orders.equities import equity_buy_market, equity_sell_market, equity_buy_limit, equity_sell_limit
        
        # Build order based on type
        if order_type == "MARKET":
            if instruction.upper() == "BUY":
                order = equity_buy_market(symbol, quantity)
            else:
                order = equity_sell_market(symbol, quantity)
        elif order_type == "LIMIT" and price is not None:
            if instruction.upper() == "BUY":
                order = equity_buy_limit(symbol, quantity, price)
            else:
                order = equity_sell_limit(symbol, quantity, price)
        else:
            raise ValueError(f"Unsupported order type: {order_type}")
        
        response = self.client.place_order(self.account_number, order)
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
            from_date = datetime.now() - timedelta(days=60)
        
        response = self.client.get_orders_for_account(
            self.account_number,
            from_entered_datetime=from_date
        )
        response.raise_for_status()
        return response.json()


# Example usage and testing
if __name__ == "__main__":
    
    print("\n" + "="*70)
    print("SCHWAB-PY CLIENT - OAuth2 Integration")
    print("="*70)
    
    try:
        # Initialize client (will trigger OAuth flow if needed)
        schwab_client = SchwabPyClient()
        
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
            period_type=Client.PriceHistory.PeriodType.MONTH,
            period=Client.PriceHistory.Period.ONE_MONTH,
            frequency_type=Client.PriceHistory.FrequencyType.DAILY,
            frequency=Client.PriceHistory.Frequency.DAILY
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
        print("✅ schwab-py integration working!")
        print("="*70)
        print("\nToken saved to:", schwab_client.token_path)
        print("Future runs will use cached token (no browser needed)")
        
    except FileNotFoundError:
        print("\n❌ Configuration missing!")
        print("\nAdd to .env:")
        print("  SCHWAB_API_KEY=your_api_key")
        print("  SCHWAB_API_SECRET=your_app_secret")
        print("  SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure you've created an app at developer.schwab.com")
        print("2. Check that API key and secret are correct")
        print("3. Ensure callback URL matches your app settings")
        print("4. First-time setup requires browser authentication")
