"""Poll SPXW options quotes periodically (polling alternative to streaming).

This is a simpler alternative to websocket streaming that:
1. Polls Schwab API for option quotes every 60 seconds
2. Aggregates quotes into 1-minute bars
3. Stores in TimescaleDB

Useful for:
- Testing without websocket complexity
- Lower-frequency data collection
- More reliable for long-running collection

Run with:
    python scripts/poll_spxw_quotes.py
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import time
from typing import List, Dict, Set
from collections import defaultdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from quant_vibe.data.schwab_dev_client import SchwabDevClient
from quant_vibe.data.timescale_store import TimescaleStore
from quant_vibe.utils import normalize_option_ticker


class OptionsQuotePoller:
    """
    Poll options quotes periodically and aggregate into bars.

    Simpler alternative to websocket streaming.
    """

    def __init__(
        self,
        poll_interval: int = 60,  # seconds
        max_dte: int = 45,
        min_dte: int = 0,
        strike_range_pct: float = 0.10,
    ):
        """
        Initialize quote poller.

        Args:
            poll_interval: Seconds between polls (default: 60)
            max_dte: Maximum days to expiration
            min_dte: Minimum days to expiration
            strike_range_pct: Strike range percentage from ATM
        """
        self.poll_interval = poll_interval
        self.max_dte = max_dte
        self.min_dte = min_dte
        self.strike_range_pct = strike_range_pct

        # Clients
        self.schwab = SchwabDevClient()
        self.ts_store = TimescaleStore()

        # Tracking
        self.contract_details: Dict[str, Dict] = {}
        self.current_bar_time: datetime = None

    def get_active_contracts(self) -> List[Dict]:
        """Get list of SPXW contracts to monitor using Schwab API."""

        print(f"\nFinding active SPXW contracts ({self.min_dte}-{self.max_dte} DTE)...")

        # Get SPX price
        spx_quote = self.schwab.get_quote("$SPX")
        spx_price = spx_quote.get("$SPX", {}).get("quote", {}).get("lastPrice", 6000)

        print(f"SPX Price: ${spx_price:.2f}")

        # Calculate strike range
        strike_min = spx_price * (1 - self.strike_range_pct)
        strike_max = spx_price * (1 + self.strike_range_pct)

        print(f"Strike Range: ${strike_min:.0f} - ${strike_max:.0f}")

        # Calculate DTE range
        today = datetime.now().date()
        min_exp_date = today + timedelta(days=self.min_dte)
        max_exp_date = today + timedelta(days=self.max_dte)

        print(f"Expiration Range: {min_exp_date} to {max_exp_date}")

        # Get option chain from Schwab
        # Note: We use strike_count to get strikes around ATM
        # Schwab returns strikes above and below ATM
        # Limit to 50 to avoid 502 errors
        strike_count = min(50, int((strike_max - strike_min) / 5) + 10)

        print(f"Fetching option chain from Schwab (strike_count={strike_count})...")

        # Retry logic for API calls
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                response = self.schwab.client.option_chains(
                    "$SPX",
                    strikeCount=strike_count
                )

                if response.status_code == 200:
                    chain_data = response.json()
                    break
                elif response.status_code == 502 and attempt < max_retries - 1:
                    print(f"⚠️  Got 502 error, retrying in {retry_delay}s (attempt {attempt+1}/{max_retries})...")
                    time.sleep(retry_delay)
                    continue
                else:
                    print(f"❌ Failed to fetch option chain: {response.status_code}")
                    return []

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️  Error: {e}, retrying in {retry_delay}s (attempt {attempt+1}/{max_retries})...")
                    time.sleep(retry_delay)
                    continue
                else:
                    print(f"❌ Error fetching option chain: {e}")
                    return []
        else:
            print(f"❌ Failed to fetch option chain after {max_retries} attempts")
            return []

        # Extract contracts from chain
        contracts = []

        # Process calls
        if "callExpDateMap" in chain_data:
            for exp_date_key, strikes in chain_data["callExpDateMap"].items():
                # Parse expiration date from key (format: "2025-12-15:7")
                exp_date_str = exp_date_key.split(":")[0]
                exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d").date()

                # Check DTE range
                dte = (exp_date - today).days
                if dte < self.min_dte or dte > self.max_dte:
                    continue

                for strike_str, contract_list in strikes.items():
                    strike = float(strike_str)

                    # Check strike range
                    if strike < strike_min or strike > strike_max:
                        continue

                    for contract_data in contract_list:
                        symbol = contract_data.get("symbol", "")

                        # Only include SPXW (weekly) contracts
                        if not symbol.startswith("SPXW"):
                            continue

                        contracts.append({
                            "ticker": symbol,
                            "strike_price": strike,
                            "contract_type": "call",
                            "expiration_date": exp_date,
                        })

        # Process puts
        if "putExpDateMap" in chain_data:
            for exp_date_key, strikes in chain_data["putExpDateMap"].items():
                exp_date_str = exp_date_key.split(":")[0]
                exp_date = datetime.strptime(exp_date_str, "%Y-%m-%d").date()

                # Check DTE range
                dte = (exp_date - today).days
                if dte < self.min_dte or dte > self.max_dte:
                    continue

                for strike_str, contract_list in strikes.items():
                    strike = float(strike_str)

                    # Check strike range
                    if strike < strike_min or strike > strike_max:
                        continue

                    for contract_data in contract_list:
                        symbol = contract_data.get("symbol", "")

                        # Only include SPXW (weekly) contracts
                        if not symbol.startswith("SPXW"):
                            continue

                        contracts.append({
                            "ticker": symbol,
                            "strike_price": strike,
                            "contract_type": "put",
                            "expiration_date": exp_date,
                        })

        print(f"✅ Found {len(contracts)} SPXW contracts")

        # Cache contract details
        for contract in contracts:
            self.contract_details[contract["ticker"]] = contract

        return contracts

    def poll_quotes(self, contracts: List[Dict]):
        """
        Poll quotes for all contracts and store as a bar.

        Args:
            contracts: List of contract dictionaries
        """
        current_time = datetime.now()
        bar_time = current_time.replace(second=0, microsecond=0)

        # Only create new bar if we're in a new minute
        if self.current_bar_time == bar_time:
            return

        self.current_bar_time = bar_time

        print(f"\n[{bar_time.strftime('%Y-%m-%d %H:%M')}] Polling {len(contracts)} contracts...")

        # Get quotes (Schwab has rate limits, so we'll batch)
        batch_size = 50  # Schwab allows ~50 symbols per request
        bars_to_insert = []

        for i in range(0, len(contracts), batch_size):
            batch = contracts[i:i + batch_size]
            tickers = [c['ticker'] for c in batch]

            try:
                # Get quotes for batch
                quotes = self.schwab.get_quotes(tickers)

                # Process each quote
                for contract in batch:
                    ticker = contract['ticker']
                    quote_data = quotes.get(ticker, {}).get('quote', {})

                    if not quote_data:
                        continue

                    # Extract data
                    bid = quote_data.get('bidPrice')
                    ask = quote_data.get('askPrice')
                    last = quote_data.get('lastPrice')
                    volume = quote_data.get('totalVolume', 0)

                    # Greeks
                    delta = quote_data.get('delta')
                    gamma = quote_data.get('gamma')
                    theta = quote_data.get('theta')
                    vega = quote_data.get('vega')
                    rho = quote_data.get('rho')
                    iv = quote_data.get('volatility')

                    if not last or last <= 0:
                        continue

                    # Normalize ticker to canonical format (remove spaces)
                    normalized_ticker = normalize_option_ticker(ticker)

                    # Create bar (using last price for OHLC since we poll once per minute)
                    bar = {
                        'timestamp': bar_time,
                        'option_ticker': normalized_ticker,
                        'underlying_ticker': 'SPX',
                        'open': last,
                        'high': last,
                        'low': last,
                        'close': last,
                        'volume': volume,
                        'strike_price': contract['strike_price'],
                        'contract_type': contract['contract_type'],
                        'expiration_date': contract['expiration_date'],
                        'bid': bid,
                        'ask': ask,
                        'implied_volatility': iv,
                        'delta': delta,
                        'gamma': gamma,
                        'theta': theta,
                        'vega': vega,
                        'rho': rho,
                        'data_source': 'schwab_poll',
                    }

                    bars_to_insert.append(bar)

                # Rate limit
                time.sleep(0.5)

            except Exception as e:
                print(f"  ⚠️  Error getting quotes for batch {i//batch_size + 1}: {e}")
                continue

        # Insert all bars at once
        if bars_to_insert:
            try:
                inserted = self.ts_store.bulk_insert_option_bars(bars_to_insert, batch_size=1000)
                print(f"  ✅ Saved {inserted} bars to database")
            except Exception as e:
                print(f"  ❌ Error inserting bars: {e}")

    def run(self):
        """Start polling loop."""

        print("="*70)
        print("SPXW OPTIONS QUOTE POLLING")
        print("="*70)
        print(f"Poll Interval: {self.poll_interval} seconds")
        print(f"DTE Range: {self.min_dte} - {self.max_dte} days")
        print(f"Strike Range: ±{self.strike_range_pct*100}% from ATM")
        print("="*70)

        # Get contracts to monitor
        contracts = self.get_active_contracts()

        if not contracts:
            print("❌ No contracts to monitor")
            return

        print(f"\n🚀 Starting polling for {len(contracts)} contracts")
        print("Press Ctrl+C to stop\n")

        try:
            while True:
                self.poll_quotes(contracts)

                # Wait for next poll
                time.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print("\n\n⚠️  Stopping poller...")

        finally:
            self.cleanup()

    def cleanup(self):
        """Clean up resources."""
        print("Cleaning up...")
        if self.ts_store:
            self.ts_store.close()
        print("✅ Cleanup complete")


def main():
    """Main entry point."""

    # Configuration
    poller = OptionsQuotePoller(
        poll_interval=60,  # Poll every 60 seconds (1 minute bars)
        max_dte=45,
        min_dte=0,
        strike_range_pct=0.10,
    )

    poller.run()


if __name__ == "__main__":
    main()
