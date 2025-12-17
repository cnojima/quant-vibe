#!/usr/bin/env python3
"""Helper to enrich streaming data with option chain details.

Schwab's Level One streaming often doesn't include Greeks and strike price.
This script periodically fetches the option chain and caches contract details
to enrich streaming data.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import schwabdev
from dotenv import load_dotenv
import os

load_dotenv()


class OptionContractEnricher:
    """Fetch and cache option contract details from Schwab API."""

    def __init__(self, schwab_client):
        """
        Initialize enricher.

        Args:
            schwab_client: Initialized schwabdev.Client instance
        """
        self.client = schwab_client
        self.contract_cache: Dict[str, Dict] = {}
        self.last_refresh = None
        self.refresh_interval_minutes = 15  # Refresh every 15 minutes

    def refresh_contract_details(
        self,
        underlying: str = "$SPX",
        strike_count: int = 50
    ) -> int:
        """
        Fetch option chain and update contract cache.

        Args:
            underlying: Underlying symbol (e.g., "$SPX")
            strike_count: Number of strikes to fetch

        Returns:
            Number of contracts cached
        """
        print(f"\n📥 Refreshing option chain from Schwab API...")
        print(f"   Underlying: {underlying}")
        print(f"   Strike count: {strike_count}")

        try:
            response = self.client.option_chains(underlying, strikeCount=strike_count)
            chain_data = response.json()

            contracts_added = 0

            # Process calls and puts
            for option_type in ['callExpDateMap', 'putExpDateMap']:
                if option_type not in chain_data:
                    continue

                exp_map = chain_data[option_type]

                for exp_date_str, strikes in exp_map.items():
                    for strike_str, contract_list in strikes.items():
                        for contract in contract_list:
                            symbol = contract.get('symbol', '')

                            if not symbol:
                                continue

                            # Cache contract details
                            self.contract_cache[symbol] = {
                                'symbol': symbol,
                                'strike_price': contract.get('strikePrice'),
                                'expiration_date': contract.get('expirationDate'),
                                'contract_type': 'call' if option_type == 'callExpDateMap' else 'put',
                                'delta': contract.get('delta'),
                                'gamma': contract.get('gamma'),
                                'theta': contract.get('theta'),
                                'vega': contract.get('vega'),
                                'rho': contract.get('rho'),
                                'implied_volatility': contract.get('volatility'),
                                'bid': contract.get('bid'),
                                'ask': contract.get('ask'),
                                'last': contract.get('last'),
                                'open_interest': contract.get('openInterest'),
                                'cached_at': datetime.now()
                            }
                            contracts_added += 1

            self.last_refresh = datetime.now()
            print(f"   ✅ Cached {contracts_added} contracts")
            print(f"   Last refresh: {self.last_refresh}")

            return contracts_added

        except Exception as e:
            print(f"   ❌ Error refreshing chain: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def get_contract_details(self, symbol: str) -> Optional[Dict]:
        """
        Get cached contract details for a symbol.

        Args:
            symbol: Option symbol (e.g., "SPXW  251219C06100000")

        Returns:
            Dict with contract details or None if not cached
        """
        # Auto-refresh if cache is stale
        if self.should_refresh():
            self.refresh_contract_details()

        return self.contract_cache.get(symbol)

    def should_refresh(self) -> bool:
        """Check if cache should be refreshed."""
        if self.last_refresh is None:
            return True

        elapsed = (datetime.now() - self.last_refresh).total_seconds() / 60
        return elapsed >= self.refresh_interval_minutes

    def enrich_quote(self, quote: Dict) -> Dict:
        """
        Enrich a streaming quote with cached contract details.

        Args:
            quote: Quote dict from streaming data

        Returns:
            Enriched quote dict
        """
        symbol = quote.get('symbol')
        if not symbol:
            return quote

        cached = self.get_contract_details(symbol)

        if cached:
            # Merge cached details (don't override existing streaming data)
            enriched = quote.copy()

            # Add contract details if missing
            if enriched.get('strike') is None:
                enriched['strike'] = cached.get('strike_price')

            if enriched.get('iv') is None:
                enriched['iv'] = cached.get('implied_volatility')

            if enriched.get('delta') is None:
                enriched['delta'] = cached.get('delta')

            if enriched.get('gamma') is None:
                enriched['gamma'] = cached.get('gamma')

            if enriched.get('theta') is None:
                enriched['theta'] = cached.get('theta')

            if enriched.get('vega') is None:
                enriched['vega'] = cached.get('vega')

            if enriched.get('rho') is None:
                enriched['rho'] = cached.get('rho')

            # Parse expiration date if missing
            if enriched.get('exp_year') is None and cached.get('expiration_date'):
                exp_date_str = cached['expiration_date']
                # Format: "2025-12-19:0" (date:DTE)
                exp_date = datetime.strptime(exp_date_str.split(':')[0], '%Y-%m-%d')
                enriched['exp_year'] = exp_date.year
                enriched['exp_month'] = exp_date.month
                enriched['exp_day'] = exp_date.day

            return enriched

        return quote

    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        return {
            'contracts_cached': len(self.contract_cache),
            'last_refresh': self.last_refresh,
            'cache_age_minutes': (datetime.now() - self.last_refresh).total_seconds() / 60 if self.last_refresh else None
        }


def test_enricher():
    """Test the enricher."""
    print("\n" + "="*70)
    print("TESTING OPTION CONTRACT ENRICHER")
    print("="*70)

    # Initialize Schwab client
    tokens_db = "tokens/schwabdev_tokens.db"

    client = schwabdev.Client(
        os.getenv("SCHWAB_API_KEY"),
        os.getenv("SCHWAB_API_SECRET"),
        os.getenv("SCHWAB_CALLBACK_URL"),
        tokens_db=tokens_db,
    )

    # Create enricher
    enricher = OptionContractEnricher(client)

    # Refresh chain
    contracts = enricher.refresh_contract_details("$SPX", strike_count=20)

    print(f"\n📊 Cache Stats:")
    stats = enricher.get_cache_stats()
    print(f"   Contracts cached: {stats['contracts_cached']}")
    print(f"   Last refresh: {stats['last_refresh']}")
    print(f"   Cache age: {stats['cache_age_minutes']:.1f} minutes")

    # Test enrichment
    if enricher.contract_cache:
        sample_symbol = list(enricher.contract_cache.keys())[0]
        print(f"\n🔍 Sample contract: {sample_symbol}")

        # Create mock streaming quote (without Greeks)
        mock_quote = {
            'symbol': sample_symbol,
            'bid': 10.50,
            'ask': 11.00,
            'last': 10.75,
            'volume': 150,
            # Greeks missing from stream
            'strike': None,
            'iv': None,
            'delta': None,
            'gamma': None,
            'theta': None,
            'vega': None,
            'rho': None,
        }

        print(f"\n   Before enrichment:")
        print(f"     Strike: {mock_quote['strike']}")
        print(f"     IV: {mock_quote['iv']}")
        print(f"     Delta: {mock_quote['delta']}")

        # Enrich
        enriched = enricher.enrich_quote(mock_quote)

        print(f"\n   After enrichment:")
        print(f"     Strike: {enriched['strike']}")
        print(f"     IV: {enriched['iv']}")
        print(f"     Delta: {enriched['delta']}")
        print(f"     Gamma: {enriched['gamma']}")
        print(f"     Theta: {enriched['theta']}")
        print(f"     Vega: {enriched['vega']}")
        print(f"     Rho: {enriched['rho']}")

    print("\n" + "="*70)
    print("✅ TEST COMPLETE")
    print("="*70)


if __name__ == "__main__":
    test_enricher()
