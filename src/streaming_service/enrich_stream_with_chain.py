#!/usr/bin/env python3
"""Helper to enrich streaming data with option chain details.

Schwab's Level One streaming often doesn't include Greeks and strike price.
This script periodically fetches the option chain and caches contract details
to enrich streaming data.
"""

import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import schwabdev
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.utils import normalize_option_ticker, now_utc

load_dotenv()


class OptionContractEnricher:
    """Fetch and cache option contract details from Schwab API."""

    def __init__(self, schwab_client):
        """Initialize enricher.

        Args:
            schwab_client: Initialized schwabdev.Client instance
        """
        self.client = schwab_client
        self.contract_cache: Dict[str, Dict] = {}
        self.last_refresh = None
        self.refresh_interval_minutes = 15

    def refresh_contract_details(
        self,
        underlying: str = "$SPX",
        strike_count: int = 50,
        auto_retry: bool = True
    ) -> int:
        """Fetch option chain and update contract cache.

        Args:
            underlying: Underlying symbol (e.g., "$SPX")
            strike_count: Number of strikes to fetch
            auto_retry: If True, automatically retry with fewer strikes on buffer overflow

        Returns:
            Number of contracts cached
        """
        print(f"\nRefreshing option chain from Schwab API...")
        print(f"   Underlying: {underlying}")
        print(f"   Strike count: {strike_count}")

        try:
            response = self.client.option_chains(underlying, strikeCount=strike_count)

            if response.status_code != 200:
                print(f"   API returned status {response.status_code}")

                if response.status_code == 502 and "Body buffer overflow" in response.text:
                    print(f"   API gateway buffer overflow - too many strikes requested")
                    print(f"   Response: {response.text[:200]}")

                    if auto_retry and strike_count > 5:
                        reduced_strikes = min(20, strike_count // 2)
                        print(f"   Auto-retrying with {reduced_strikes} strikes...")
                        return self.refresh_contract_details(underlying, reduced_strikes, auto_retry=False)

                    print(f"   Reduce strike_count parameter (current: {strike_count})")
                else:
                    print(f"   Response text: {response.text[:500]}")

                return 0

            if not response.text or response.text.strip() == "":
                print("   API returned empty response")
                return 0

            chain_data = response.json()
            contracts_added = self._process_chain_data(chain_data)

            self.last_refresh = now_utc()
            print(f"   Cached {contracts_added} contracts")
            print(f"   Last refresh: {self.last_refresh}")

            return contracts_added

        except Exception as e:
            print(f"   Error refreshing chain: {e}")
            print(f"   Response status code: {response.status_code if 'response' in locals() else 'N/A'}")
            print(f"   Response text (first 500 chars): {response.text[:500] if 'response' in locals() and hasattr(response, 'text') else 'N/A'}")
            traceback.print_exc()
            return 0

    def _process_chain_data(self, chain_data: dict) -> int:
        """Process chain data and populate cache.

        Args:
            chain_data: Option chain data from API

        Returns:
            Number of contracts added
        """
        contracts_added = 0

        for option_type in ['callExpDateMap', 'putExpDateMap']:
            if option_type not in chain_data:
                continue

            exp_map = chain_data[option_type]
            contract_type = 'call' if option_type == 'callExpDateMap' else 'put'

            for exp_date_str, strikes in exp_map.items():
                for strike_str, contract_list in strikes.items():
                    for contract in contract_list:
                        symbol = contract.get('symbol', '')
                        if not symbol:
                            continue

                        normalized_symbol = normalize_option_ticker(symbol)

                        self.contract_cache[normalized_symbol] = {
                            'symbol': normalized_symbol,
                            'strike_price': contract.get('strikePrice'),
                            'expiration_date': contract.get('expirationDate'),
                            'contract_type': contract_type,
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
                            'cached_at': now_utc()
                        }
                        contracts_added += 1

        return contracts_added

    def get_contract_details(self, symbol: str) -> Optional[Dict]:
        """Get cached contract details for a symbol.

        Args:
            symbol: Option symbol

        Returns:
            Dict with contract details or None if not cached
        """
        if self.should_refresh():
            self.refresh_contract_details()

        normalized_symbol = normalize_option_ticker(symbol)
        return self.contract_cache.get(normalized_symbol)

    def should_refresh(self) -> bool:
        """Check if cache should be refreshed."""
        if self.last_refresh is None:
            return True

        elapsed = (now_utc() - self.last_refresh).total_seconds() / 60
        return elapsed >= self.refresh_interval_minutes

    def enrich_quote(self, quote: Dict) -> Dict:
        """Enrich a streaming quote with cached contract details.

        Args:
            quote: Quote dict from streaming data

        Returns:
            Enriched quote dict
        """
        symbol = quote.get('symbol')
        if not symbol:
            return quote

        cached = self.get_contract_details(symbol)
        if not cached:
            return quote

        enriched = quote.copy()

        fields_to_enrich = [
            ('strike', 'strike_price'),
            ('iv', 'implied_volatility'),
            ('delta', 'delta'),
            ('gamma', 'gamma'),
            ('theta', 'theta'),
            ('vega', 'vega'),
            ('rho', 'rho')
        ]

        for quote_field, cache_field in fields_to_enrich:
            if enriched.get(quote_field) is None:
                enriched[quote_field] = cached.get(cache_field)

        if enriched.get('exp_year') is None and cached.get('expiration_date'):
            exp_date_str = cached['expiration_date']
            exp_date = datetime.strptime(exp_date_str.split('T')[0], '%Y-%m-%d')
            enriched['exp_year'] = exp_date.year
            enriched['exp_month'] = exp_date.month
            enriched['exp_day'] = exp_date.day

        return enriched

    def get_cache_stats(self) -> Dict:
        """Get cache statistics."""
        return {
            'contracts_cached': len(self.contract_cache),
            'last_refresh': self.last_refresh,
            'cache_age_minutes': (now_utc() - self.last_refresh).total_seconds() / 60 if self.last_refresh else None
        }


def test_enricher():
    """Test the enricher."""
    print("\n" + "="*70)
    print("TESTING OPTION CONTRACT ENRICHER")
    print("="*70)

    tokens_db = "tokens/schwabdev_tokens.db"

    client = schwabdev.Client(
        os.getenv("SCHWAB_API_KEY"),
        os.getenv("SCHWAB_API_SECRET"),
        os.getenv("SCHWAB_CALLBACK_URL"),
        tokens_db=tokens_db,
    )

    enricher = OptionContractEnricher(client)
    contracts = enricher.refresh_contract_details("$SPX", strike_count=20)

    print("\nCache Stats:")
    stats = enricher.get_cache_stats()
    print(f"   Contracts cached: {stats['contracts_cached']}")
    print(f"   Last refresh: {stats['last_refresh']}")
    print(f"   Cache age: {stats['cache_age_minutes']:.1f} minutes")

    if enricher.contract_cache:
        sample_symbol = list(enricher.contract_cache.keys())[0]
        print(f"\nSample contract: {sample_symbol}")

        mock_quote = {
            'symbol': sample_symbol,
            'bid': 10.50,
            'ask': 11.00,
            'last': 10.75,
            'volume': 150,
            'strike': None,
            'iv': None,
            'delta': None,
            'gamma': None,
            'theta': None,
            'vega': None,
            'rho': None,
        }

        print("\n   Before enrichment:")
        print(f"     Strike: {mock_quote['strike']}")
        print(f"     IV: {mock_quote['iv']}")
        print(f"     Delta: {mock_quote['delta']}")

        enriched = enricher.enrich_quote(mock_quote)

        print("\n   After enrichment:")
        print(f"     Strike: {enriched['strike']}")
        print(f"     IV: {enriched['iv']}")
        print(f"     Delta: {enriched['delta']}")
        print(f"     Gamma: {enriched['gamma']}")
        print(f"     Theta: {enriched['theta']}")
        print(f"     Vega: {enriched['vega']}")
        print(f"     Rho: {enriched['rho']}")

    print("\n" + "="*70)
    print("TEST COMPLETE")
    print("="*70)


if __name__ == "__main__":
    test_enricher()