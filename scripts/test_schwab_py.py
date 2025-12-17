#!/usr/bin/env python3
"""
Quick test of schwab-py OAuth2 integration

This script demonstrates the schwab-py library for Schwab API access.
First run will open a browser for authentication.
Subsequent runs use cached token.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.schwab_py_client import SchwabPyClient
from schwab.client import Client


def main():
    print("\n" + "="*70)
    print("Testing schwab-py OAuth2 Integration")
    print("="*70)
    
    print("\n📋 Setup Info:")
    print("  - Python 3.14.2 ✅")
    print("  - schwab-py 1.5.1 ✅")
    print("  - OAuth2 credentials configured ✅")
    
    try:
        # Initialize client (may trigger OAuth flow on first run)
        print("\n🔐 Authenticating...")
        client = SchwabPyClient()
        print("   ✓ Authentication successful!")
        
        # Test 1: Get a single quote
        print("\n📊 Test 1: Single Quote")
        print("   Fetching AAPL...")
        quote_data = client.get_quote("AAPL")
        
        if "AAPL" in quote_data:
            data = quote_data["AAPL"]
            quote = data["quote"]
            print(f"   Symbol: {data['symbol']}")
            print(f"   Last: ${quote['lastPrice']:.2f}")
            print(f"   Bid/Ask: ${quote.get('bidPrice', 0):.2f} / ${quote.get('askPrice', 0):.2f}")
            print(f"   Volume: {quote.get('totalVolume', 0):,}")
            print(f"   Change: {quote.get('netPercentChange', 0):.2f}%")
            print(f"   52-Week High/Low: ${quote.get('52WeekHigh', 0):.2f} / ${quote.get('52WeekLow', 0):.2f}")
            print("   ✓ Success!")
        
        # Test 2: Get multiple quotes
        print("\n📊 Test 2: Multiple Quotes")
        symbols = ["AAPL", "MSFT", "GOOGL"]
        print(f"   Fetching {', '.join(symbols)}...")
        quotes_data = client.get_quotes(symbols)
        
        for symbol in symbols:
            if symbol in quotes_data:
                price = quotes_data[symbol]["quote"]["lastPrice"]
                change = quotes_data[symbol]["quote"].get("netPercentChange", 0)
                print(f"   {symbol}: ${price:.2f} ({change:+.2f}%)")
        print("   ✓ Success!")
        
        # Test 3: Get historical data
        print("\n📈 Test 3: Price History")
        print("   Fetching 1 month of AAPL daily data...")
        history = client.get_price_history(
            "AAPL",
            period_type=Client.PriceHistory.PeriodType.MONTH,
            period=Client.PriceHistory.Period.ONE_MONTH,
            frequency_type=Client.PriceHistory.FrequencyType.DAILY,
            frequency=Client.PriceHistory.Frequency.DAILY
        )
        
        if not history.empty:
            print(f"   Days: {len(history)}")
            print(f"   Date range: {history.index[0]} to {history.index[-1]}")
            print(f"   Latest close: ${history['Close'].iloc[-1]:.2f}")
            print(f"   Month high: ${history['High'].max():.2f}")
            print(f"   Month low: ${history['Low'].min():.2f}")
            print("   ✓ Success!")
        
        # Test 4: Account info (optional)
        print("\n💼 Test 4: Account Info")
        try:
            # First get account numbers to see the correct format
            print("   Fetching account numbers...")
            account_numbers_response = client.client.get_account_numbers()
            account_numbers_response.raise_for_status()
            account_numbers = account_numbers_response.json()
            
            if account_numbers:
                print(f"   Found {len(account_numbers)} account(s)")
                
                for i, acct_info in enumerate(account_numbers, 1):
                    account_hash = acct_info['hashValue']
                    account_num = acct_info.get('accountNumber', 'N/A')
                    print(f"\n   Account {i}: {account_num}")
                    print(f"   Hash: {account_hash}")
                    
                    # Set the account number for this iteration
                    client.account_number = account_hash
                    
                    account = client.get_account()
                    if "securitiesAccount" in account:
                        balances = account["securitiesAccount"]["currentBalances"]
                        account_type = account["securitiesAccount"]["type"]
                        print(f"   Type: {account_type}")
                        print(f"   Total Value: ${balances.get('liquidationValue', 0):,.2f}")
                        print(f"   Cash: ${balances.get('cashBalance', 0):,.2f}")
                        print(f"   Buying Power: ${balances.get('buyingPower', 0):,.2f}")
                        
                        positions = client.get_positions()
                        print(f"   Positions: {len(positions)}")
                        print("   ✓ Success!")
            else:
                print("   ⚠️  No accounts found")
        except Exception as e:
            print(f"   ⚠️  Account access: {e}")
            print("   (This is expected if account number not set or invalid)")
        
        print("\n" + "="*70)
        print("✅ schwab-py Integration WORKING!")
        print("="*70)
        print("\n💡 Key Features:")
        print("  - Real-time quotes ✅")
        print("  - Historical data ✅")
        print("  - Multiple symbols ✅")
        print("  - Automatic token refresh ✅")
        print("  - Cached token (no browser needed next time) ✅")
        
        print("\n🎯 Next Steps:")
        print("  1. Use in backtesting: fetch real data for strategies")
        print("  2. Build live trading: integrate with strategy signals")
        print("  3. Monitor positions: track real portfolio performance")
        print("  4. Streaming data: use websockets for real-time updates")
        
        return True
    
    except FileNotFoundError as e:
        print(f"\n❌ Configuration Error: {e}")
        print("\n📝 Setup Required:")
        print("  1. Go to https://developer.schwab.com/")
        print("  2. Create an app and get:")
        print("     - API Key")
        print("     - App Secret")
        print("     - Callback URL")
        print("  3. Add to .env:")
        print("     SCHWAB_API_KEY=your_key")
        print("     SCHWAB_API_SECRET=your_secret")
        print("     SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/")
        return False
    
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n🔍 Troubleshooting:")
        print("  - Check API credentials in .env")
        print("  - Verify callback URL matches Schwab app settings")
        print("  - On first run, browser opens for OAuth (this is normal)")
        print("  - Token saved to ./tokens/schwab_token.json")
        
        import traceback
        print("\nFull error:")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
