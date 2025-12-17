"""Quick test to see if we can fetch SPXW contracts with schwabdev."""

import os
import schwabdev
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

print("="*70)
print("Testing SPXW Contract Fetching")
print("="*70)

# Initialize client
print("\n1. Initializing schwabdev client...")
client = schwabdev.Client(
    os.getenv("SCHWAB_API_KEY"),
    os.getenv("SCHWAB_API_SECRET"),
    os.getenv("SCHWAB_CALLBACK_URL"),
    tokens_db="tokens/schwabdev_tokens.db",
)
print("✓ Client ready")

# Get SPX price
print("\n2. Getting SPX price...")
response = client.quote("$SPX")
data = response.json()
if "$SPX" in data:
    spx_price = data["$SPX"]["quote"]["lastPrice"]
    print(f"✓ SPX: ${spx_price:.2f}")
else:
    print(f"Response: {data}")
    spx_price = 6000

# Get option chain
print("\n3. Fetching option chain...")
response = client.option_chains("$SPX", strikeCount=10)
chain = response.json()

print(f"✓ Got chain data")
print(f"  Keys: {list(chain.keys())}")

# Count SPXW contracts
spxw_count = 0
sample_contracts = []

for exp_type in ['callExpDateMap', 'putExpDateMap']:
    if exp_type not in chain:
        continue

    for exp_date, strikes in chain[exp_type].items():
        for strike, contracts in strikes.items():
            for contract in contracts:
                symbol = contract.get('symbol', '')
                if 'SPXW' in symbol:
                    spxw_count += 1
                    if len(sample_contracts) < 5:
                        sample_contracts.append(symbol)

print(f"\n4. Results:")
print(f"  Total SPXW contracts: {spxw_count}")
print(f"  Sample contracts:")
for symbol in sample_contracts:
    print(f"    {symbol}")

print("\n✅ Test complete - schwabdev API working!")
