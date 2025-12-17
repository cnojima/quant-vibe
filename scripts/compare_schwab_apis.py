"""
Compare Schwab API Integration Approaches

This script demonstrates two ways to integrate with Schwab's API:

1. Bearer Token Approach (schwab_client.py)
   - Simpler setup, just needs bearer token
   - Manual token refresh required
   - Good for quick prototyping
   
2. OAuth2 Library Approach (schwab_py_client.py)
   - Uses official schwab-py library
   - Automatic token refresh
   - More robust for production
   - Requires Python 3.10+
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.schwab_client import SchwabClient
from quant_vibe.data.schwab_py_client import SchwabPyClient
from schwab.client import Client


def test_bearer_token_approach():
    """Test the direct bearer token approach."""
    print("\n" + "="*70)
    print("APPROACH 1: Bearer Token (schwab_client.py)")
    print("="*70)
    print("\n✓ Pros:")
    print("  - Simple setup (just paste bearer token)")
    print("  - No OAuth flow needed")
    print("  - Works with any Python version")
    print("\n✗ Cons:")
    print("  - Token expires (must refresh manually)")
    print("  - Less secure (token in .env)")
    print("  - No automatic token management")
    
    try:
        client = SchwabClient()
        
        # Get quote
        print("\n📊 Fetching AAPL quote...")
        quote = client.get_quote("AAPL")
        if quote:
            print(f"   Last Price: ${quote.get('lastPrice', 0):.2f}")
            print("   ✓ Success!")
        
        # Get price history
        print("\n📈 Fetching price history...")
        history = client.get_price_history("AAPL", period_type="month", period=1)
        if history:
            print(f"   ✓ Got {len(history.get('candles', []))} days")
        
        print("\n✅ Bearer token approach working!")
        return True
    
    except Exception as e:
        print(f"\n❌ Bearer token approach failed: {e}")
        print("   (Token may have expired)")
        return False


def test_oauth_library_approach():
    """Test the schwab-py library approach."""
    print("\n" + "="*70)
    print("APPROACH 2: OAuth2 Library (schwab_py_client.py)")
    print("="*70)
    print("\n✓ Pros:")
    print("  - Automatic token refresh")
    print("  - Official library (better support)")
    print("  - More secure token storage")
    print("  - Production-ready")
    print("\n✗ Cons:")
    print("  - Requires Python 3.10+")
    print("  - More complex setup (OAuth flow)")
    print("  - Needs API key + secret + callback URL")
    
    try:
        client = SchwabPyClient()
        
        # Get quote
        print("\n📊 Fetching AAPL quote...")
        quote_data = client.get_quote("AAPL")
        if "AAPL" in quote_data:
            price = quote_data["AAPL"]["quote"]["lastPrice"]
            print(f"   Last Price: ${price:.2f}")
            print("   ✓ Success!")
        
        # Get price history
        print("\n📈 Fetching price history...")
        history = client.get_price_history(
            "AAPL",
            period_type=Client.PriceHistory.PeriodType.MONTH,
            period=Client.PriceHistory.Period.ONE_MONTH,
            frequency_type=Client.PriceHistory.FrequencyType.DAILY,
            frequency=Client.PriceHistory.Frequency.DAILY
        )
        if not history.empty:
            print(f"   ✓ Got {len(history)} days")
        
        print("\n✅ OAuth2 library approach working!")
        return True
    
    except FileNotFoundError:
        print("\n⚠️  OAuth2 setup required!")
        print("\nAdd to .env:")
        print("  SCHWAB_API_KEY=your_api_key")
        print("  SCHWAB_API_SECRET=your_app_secret")
        print("  SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/")
        return False
    
    except Exception as e:
        print(f"\n❌ OAuth2 approach failed: {e}")
        print("\nFirst-time setup:")
        print("1. Get API credentials from developer.schwab.com")
        print("2. Add to .env (see above)")
        print("3. Run again - browser will open for auth")
        return False


def recommendation():
    """Provide recommendation on which approach to use."""
    print("\n" + "="*70)
    print("RECOMMENDATION")
    print("="*70)
    print("\n🎯 For Quick Prototyping / Learning:")
    print("   → Use Bearer Token approach (schwab_client.py)")
    print("   → Fast setup, good for testing strategies")
    print("   → Just need to paste token from Schwab website")
    
    print("\n🏗️  For Production / Long-term:")
    print("   → Use OAuth2 Library approach (schwab_py_client.py)")
    print("   → Automatic token refresh = no interruptions")
    print("   → More secure and maintainable")
    print("   → Supports streaming data and websockets")
    
    print("\n💡 Migration Path:")
    print("   1. Start with bearer token for quick testing")
    print("   2. Once strategies work, get API credentials")
    print("   3. Switch to schwab-py for production backtesting")
    print("   4. Keep both for flexibility!")
    
    print("\n⚠️  Important Notes:")
    print("   - Schwab does NOT support paper trading")
    print("   - All orders are REAL (use small quantities!)")
    print("   - Both approaches access same Schwab API")
    print("   - Choose based on your needs and Python version")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("SCHWAB API INTEGRATION COMPARISON")
    print("="*70)
    
    bearer_works = test_bearer_token_approach()
    oauth_works = test_oauth_library_approach()
    
    recommendation()
    
    print("\n" + "="*70)
    print("Summary:")
    print(f"  Bearer Token: {'✅ Working' if bearer_works else '❌ Not configured'}")
    print(f"  OAuth2 Library: {'✅ Working' if oauth_works else '❌ Not configured'}")
    print("="*70 + "\n")
