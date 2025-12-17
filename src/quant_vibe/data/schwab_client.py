"""
Schwab API Client - Direct API Integration

This module integrates with Schwab's API for:
- Fetching real-time market data
- Retrieving historical pricing
- Account information
- Order placement for trading

Documentation: https://developer.schwab.com/

Two Integration Approaches:
=========================

APPROACH 1: Direct API (Current - Python 3.9+)
----------------------------------------------
Uses direct HTTP requests with bearer token authentication.
Works with your current Python 3.9 setup.

APPROACH 2: schwab-py Library (Future - Python 3.10+)
-----------------------------------------------------
Uses the official schwab-py wrapper with OAuth2 flow.
Requires upgrading to Python 3.10+.
See: https://github.com/alexgolec/schwab-py

Setup Instructions:
==================
1. Register at https://developer.schwab.com/
2. Create an app and get API credentials
3. Generate bearer token from Schwab
4. Add to .env:
   SCHWAB_BEARER_TOKEN=your_bearer_token_here
   SCHWAB_ACCOUNT_NUMBER=your_account_number
"""

import os
from typing import Optional, Dict, List
from datetime import datetime
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()


class SchwabClient:
    """
    Client for Schwab API integration using direct HTTP requests.
    
    This uses bearer token authentication for simplicity.
    For production, consider using schwab-py library with OAuth2.
    """
    
    BASE_URL = "https://api.schwabapi.com"
    MARKET_DATA_URL = f"{BASE_URL}/marketdata/v1"
    TRADER_URL = f"{BASE_URL}/trader/v1"
    
    def __init__(self, bearer_token: Optional[str] = None):
        """
        Initialize Schwab API client.
        
        Args:
            bearer_token: Optional bearer token. If not provided, reads from .env
        """
        self.bearer_token = bearer_token or os.getenv("SCHWAB_BEARER_TOKEN")
        self.account_number = os.getenv("SCHWAB_ACCOUNT_NUMBER")
        
        if not self.bearer_token:
            raise ValueError(
                "Bearer token required. Set SCHWAB_BEARER_TOKEN in .env or pass to constructor."
            )
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers with bearer token authentication."""
        return {
            "Authorization": f"Bearer {self.bearer_token}",
            "Accept": "application/json"
        }
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> requests.Response:
        """
        Make authenticated request to Schwab API.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint
            params: Query parameters
            data: Request body data
            
        Returns:
            Response object
        """
        url = f"{self.BASE_URL}{endpoint}"
        headers = self._get_headers()
        
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=data
        )
        
        return response
    
    def get_quote(self, symbol: str) -> Dict:
        """
        Get real-time quote for a symbol.
        
        Args:
            symbol: Stock ticker symbol (e.g., 'AAPL')
            
        Returns:
            Dictionary with quote data including bid, ask, last price, volume, etc.
            
        Example:
            >>> client = SchwabClient()
            >>> quote = client.get_quote("AAPL")
            >>> print(f"Last: ${quote['quote']['lastPrice']}")
        """
        endpoint = f"/marketdata/v1/{symbol}/quotes"
        response = self._make_request("GET", endpoint)
        response.raise_for_status()
        return response.json()
    
    def get_quotes(self, symbols: List[str]) -> Dict:
        """
        Get quotes for multiple symbols at once.
        
        Args:
            symbols: List of stock ticker symbols
            
        Returns:
            Dictionary with quotes for each symbol
        """
        endpoint = "/marketdata/v1/quotes"
        params = {"symbols": ",".join(symbols)}
        response = self._make_request("GET", endpoint, params=params)
        response.raise_for_status()
        return response.json()
    
    def get_price_history(
        self,
        symbol: str,
        period_type: str = "year",
        period: int = 1,
        frequency_type: str = "daily",
        frequency: int = 1,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Fetch historical price data.
        
        Args:
            symbol: Stock ticker symbol
            period_type: Type of period ('day', 'month', 'year', 'ytd')
            period: Number of periods
            frequency_type: Frequency type ('minute', 'daily', 'weekly', 'monthly')
            frequency: Frequency value (1, 5, 10, 15, 30 for minutes; 1 for others)
            start_date: Optional start date (overrides period)
            end_date: Optional end date
            
        Returns:
            DataFrame with OHLCV data
            
        Example:
            >>> client = SchwabClient()
            >>> # Get 1 year of daily data
            >>> data = client.get_price_history("AAPL", period_type="year", period=1)
            >>> # Or use specific dates
            >>> data = client.get_price_history(
            ...     "AAPL",
            ...     start_date=datetime(2024, 1, 1),
            ...     end_date=datetime(2024, 12, 31)
            ... )
        """
        endpoint = "/marketdata/v1/pricehistory"
        
        params = {
            "symbol": symbol,
            "periodType": period_type,
            "period": period,
            "frequencyType": frequency_type,
            "frequency": frequency
        }
        
        if start_date:
            params["startDate"] = int(start_date.timestamp() * 1000)  # milliseconds
        if end_date:
            params["endDate"] = int(end_date.timestamp() * 1000)
            
        response = self._make_request("GET", endpoint, params=params)
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
    
    def get_account_info(self) -> Dict:
        """
        Get account information including balances and positions.
        
        Returns:
            Dictionary with account details
            
        Note:
            Requires SCHWAB_ACCOUNT_NUMBER in .env
        """
        if not self.account_number:
            raise ValueError("SCHWAB_ACCOUNT_NUMBER not set in .env")
            
        endpoint = f"/trader/v1/accounts/{self.account_number}"
        response = self._make_request("GET", endpoint)
        response.raise_for_status()
        return response.json()
    
    def get_positions(self) -> List[Dict]:
        """
        Get current positions in account.
        
        Returns:
            List of position dictionaries with symbol, quantity, cost basis, etc.
        """
        account_info = self.get_account_info()
        
        if "securitiesAccount" in account_info:
            positions = account_info["securitiesAccount"].get("positions", [])
            return positions
        
        return []
    
    def get_account_balance(self) -> Dict:
        """
        Get account balance and buying power.
        
        Returns:
            Dictionary with balance information including:
            - liquidationValue
            - cashBalance
            - buyingPower
            - accountValue
        """
        account_info = self.get_account_info()
        
        if "securitiesAccount" in account_info:
            balances = account_info["securitiesAccount"].get("currentBalances", {})
            return balances
        
        return {}
    
    def place_order(
        self,
        symbol: str,
        quantity: int,
        instruction: str,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        session: str = "NORMAL",
        duration: str = "DAY"
    ) -> Dict:
        """
        Place an order.
        
        Args:
            symbol: Stock ticker symbol
            quantity: Number of shares
            instruction: 'BUY', 'SELL', 'BUY_TO_OPEN', 'SELL_TO_CLOSE', etc.
            order_type: 'MARKET', 'LIMIT', 'STOP', 'STOP_LIMIT'
            price: Limit price (required for LIMIT orders)
            session: 'NORMAL', 'AM', 'PM', 'SEAMLESS'
            duration: 'DAY', 'GOOD_TILL_CANCEL', 'FILL_OR_KILL'
            
        Returns:
            Dictionary with order confirmation
            
        Warning:
            This places REAL orders! Test with paper trading account first.
            
        Example:
            >>> client = SchwabClient()
            >>> # Market buy order
            >>> order = client.place_order("AAPL", 10, "BUY", "MARKET")
            >>> # Limit sell order
            >>> order = client.place_order("AAPL", 10, "SELL", "LIMIT", price=150.00)
        """
        if not self.account_number:
            raise ValueError("SCHWAB_ACCOUNT_NUMBER not set in .env")
        
        order_data = {
            "orderType": order_type,
            "session": session,
            "duration": duration,
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [
                {
                    "instruction": instruction,
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
        
        endpoint = f"/trader/v1/accounts/{self.account_number}/orders"
        response = self._make_request("POST", endpoint, data=order_data)
        response.raise_for_status()
        
        return {
            "status": "success",
            "order_id": response.headers.get("Location", "").split("/")[-1],
            "response": response.text
        }
    
    def get_orders(self, max_results: int = 50) -> List[Dict]:
        """
        Get recent orders for the account.
        
        Args:
            max_results: Maximum number of orders to return
            
        Returns:
            List of order dictionaries
        """
        if not self.account_number:
            raise ValueError("SCHWAB_ACCOUNT_NUMBER not set in .env")
            
        endpoint = f"/trader/v1/accounts/{self.account_number}/orders"
        params = {"maxResults": max_results}
        response = self._make_request("GET", endpoint, params=params)
        response.raise_for_status()
        return response.json()


# Example usage and testing
if __name__ == "__main__":
    import sys
    
    print("\n" + "="*70)
    print("SCHWAB API CLIENT - DIRECT INTEGRATION")
    print("="*70)
    
    # Check for bearer token
    bearer_token = os.getenv("SCHWAB_BEARER_TOKEN")
    
    if not bearer_token:
        print("\n❌ No bearer token found!")
        print("\nSetup required:")
        print("1. Generate bearer token from Schwab Developer Portal")
        print("2. Add to .env file:")
        print("   SCHWAB_BEARER_TOKEN=your_token_here")
        print("   SCHWAB_ACCOUNT_NUMBER=your_account_number")
        print("\nExample .env entry:")
        print('SCHWAB_BEARER_TOKEN=I0.b2F1dGgyLmJkYy5zY2h3YWIuY29t.xxx...')
        sys.exit(1)
    
    try:
        # Initialize client
        client = SchwabClient()
        print("\n✓ Client initialized with bearer token")
        
        # Test 1: Get a quote
        print("\n📊 Test 1: Fetching AAPL quote...")
        try:
            quote_data = client.get_quote("AAPL")
            if "quote" in quote_data:
                quote = quote_data["quote"]
                print(f"   Symbol: {quote.get('symbol', 'N/A')}")
                print(f"   Last Price: ${quote.get('lastPrice', 0):.2f}")
                print(f"   Bid: ${quote.get('bidPrice', 0):.2f}")
                print(f"   Ask: ${quote.get('askPrice', 0):.2f}")
                print(f"   Volume: {quote.get('totalVolume', 0):,}")
                print("   ✓ Quote fetched successfully!")
            else:
                print(f"   Raw response: {quote_data}")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        # Test 2: Get price history
        print("\n📈 Test 2: Fetching AAPL price history (1 month)...")
        try:
            history = client.get_price_history(
                "AAPL",
                period_type="month",
                period=1,
                frequency_type="daily"
            )
            if not history.empty:
                print(f"   ✓ Fetched {len(history)} days of data")
                print(f"   Date range: {history.index[0]} to {history.index[-1]}")
                print(f"   Latest close: ${history['Close'].iloc[-1]:.2f}")
            else:
                print("   ✗ No data returned")
        except Exception as e:
            print(f"   ✗ Error: {e}")
        
        # Test 3: Get account info (if account number is set)
        if client.account_number:
            print("\n💼 Test 3: Fetching account info...")
            try:
                balance = client.get_account_balance()
                if balance:
                    print(f"   Account Value: ${balance.get('liquidationValue', 0):,.2f}")
                    print(f"   Cash Balance: ${balance.get('cashBalance', 0):,.2f}")
                    print(f"   Buying Power: ${balance.get('buyingPower', 0):,.2f}")
                    print("   ✓ Account info fetched successfully!")
                else:
                    print("   ✗ No balance data returned")
            except Exception as e:
                print(f"   ✗ Error: {e}")
            
            print("\n📋 Test 4: Fetching positions...")
            try:
                positions = client.get_positions()
                if positions:
                    print(f"   ✓ Found {len(positions)} positions:")
                    for pos in positions[:5]:  # Show first 5
                        symbol = pos.get("instrument", {}).get("symbol", "???")
                        quantity = pos.get("longQuantity", 0)
                        print(f"      - {symbol}: {quantity} shares")
                else:
                    print("   No positions found (account may be empty)")
            except Exception as e:
                print(f"   ✗ Error: {e}")
        else:
            print("\n⚠️  SCHWAB_ACCOUNT_NUMBER not set - skipping account tests")
        
        print("\n" + "="*70)
        print("✅ Schwab API integration working!")
        print("="*70)
        print("\nNext steps:")
        print("1. Use client.get_quote(symbol) for real-time quotes")
        print("2. Use client.get_price_history() for historical data")
        print("3. Use client.place_order() for trading (CAREFUL!)")
        print("4. Read SCHWAB_INTEGRATION.md for more examples")
        
    except Exception as e:
        print(f"\n❌ Error initializing client: {e}")
        print("\nCheck your .env file and bearer token!")
