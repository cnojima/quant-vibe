# Stream Data Enrichment Guide

## Problem: Missing Greeks and Strike Price in Streaming Data

**Issue**: Schwab's Level One Options streaming API often doesn't include Greeks (delta, gamma, theta, vega, rho), strike price, or implied volatility in real-time stream updates, even when these fields are requested.

**Why**: Level One data focuses on quote/price updates (bid, ask, last, volume). Contract details and calculated values (Greeks) are typically only available via the REST API option chain endpoint.

**Result**: Database fields for `strike_price`, `implied_volatility`, `delta`, `gamma`, `theta`, `vega`, and `rho` are left NULL when using streaming data alone.

## Solution: Stream Enrichment

The `enrich_stream_with_chain.py` module fetches contract details from Schwab's option chain REST API and caches them locally. The streaming script then merges this cached data with incoming stream updates.

### How It Works

```
1. Start streaming
   ↓
2. Fetch option chain via REST API
   ↓
3. Cache contract details (Greeks, strike, IV)
   ↓
4. Stream receives quote update (bid/ask/last/volume)
   ↓
5. Enrich quote with cached contract details
   ↓
6. Save complete record to database
   ↓
7. Auto-refresh cache every 15 minutes
```

### Architecture

```python
# Option chain REST API (fetched periodically)
{
  "symbol": "SPXW  251219C06100000",
  "strikePrice": 6100.0,
  "delta": 0.52,
  "gamma": 0.0012,
  "theta": -15.3,
  "vega": 12.5,
  "rho": 8.2,
  "volatility": 0.185,  # IV
  ...
}

# Level One stream (real-time updates)
{
  "2": 10.50,  # bid
  "3": 11.00,  # ask
  "4": 10.75,  # last
  "8": 150,    # volume
  # Greeks missing!
}

# Enriched result (merged)
{
  "bid": 10.50,
  "ask": 11.00,
  "last": 10.75,
  "volume": 150,
  # Filled from cache:
  "strike": 6100.0,
  "delta": 0.52,
  "gamma": 0.0012,
  "theta": -15.3,
  "vega": 12.5,
  "rho": 8.2,
  "iv": 0.185
}
```

## Implementation

### 1. OptionContractEnricher Class

Located in `scripts/enrich_stream_with_chain.py`:

```python
from enrich_stream_with_chain import OptionContractEnricher

# Initialize with Schwab client
enricher = OptionContractEnricher(schwab_client)

# Fetch and cache option chain
enricher.refresh_contract_details("$SPX", strike_count=50)

# Enrich streaming quotes
enriched_quote = enricher.enrich_quote(streaming_quote)
```

**Key Features**:
- **Auto-refresh**: Cache refreshes every 15 minutes
- **Non-destructive merge**: Streaming data takes priority (doesn't override real-time values)
- **Efficient**: Only fetches chain periodically, not on every quote
- **Stats tracking**: Monitor cache size and age

### 2. Integration with Stream

The `stream_spxw_schwabdev.py` script now:

1. **Initializes enricher** on startup
2. **Populates cache** before subscribing to stream
3. **Enriches each quote** before buffering
4. **Shows cache stats** in status updates

### Debugging Output

The script now logs the first 3 messages to show what fields Schwab actually sends:

```
🔍 DEBUG - Sample message #1
   Symbol: SPXW  251219C06100000
   Fields received in item: ['key', '2', '3', '4', '8', '16', '17']
   Strike (field 20): None  ← Missing!
   IV (field 10): None      ← Missing!
   Delta (field 28): None   ← Missing!
   Gamma (field 29): None   ← Missing!
   Theta (field 30): None   ← Missing!
   Vega (field 31): None    ← Missing!
   Rho (field 32): None     ← Missing!
```

This confirms that Schwab's stream doesn't include these fields, so enrichment is necessary.

## Usage

### Running the Stream with Enrichment

```bash
# Normal usage - enrichment happens automatically
python scripts/stream_spxw_schwabdev.py

# With specific DTE range
python scripts/stream_spxw_schwabdev.py --max-dte 7 --min-dte 0

# With wider strike range (more contracts = larger cache)
python scripts/stream_spxw_schwabdev.py --strike-range-pct 0.20
```

### Testing the Enricher

```bash
# Test enricher independently
python scripts/enrich_stream_with_chain.py
```

This will:
1. Fetch option chain from Schwab
2. Cache contract details
3. Show sample enrichment
4. Display cache statistics

### Monitoring Enrichment

Watch for these status updates in the stream output:

```
📊 Status Update [2025-12-17 14:30:00]:
   Messages received: 1523
   Contracts streaming: 145
   Buffered symbols: 38
   Contract cache: 287 contracts  ← Cache size
   Cache age: 8.3 minutes         ← Time since refresh
```

**Cache refresh** happens automatically when age > 15 minutes.

## Data Flow

### Startup Sequence

```
1. Initialize Schwab client
2. Initialize TimescaleDB
3. Initialize enricher ← NEW
4. Fetch SPXW contracts (DTE filter, strike range)
5. Populate enricher cache ← NEW (fetch full option chain)
6. Start stream
7. Subscribe to contracts
8. Begin receiving quotes
```

### Per-Quote Processing

```
1. Stream receives message
2. Parse Level One data (bid/ask/last/volume)
3. Enrich with cached details ← NEW (add Greeks, strike, IV)
4. Add to quote buffer
5. Every 60s: Aggregate into 1-min bar
6. Insert into TimescaleDB with complete data ✓
```

### Periodic Maintenance

```
Every 60 seconds:
  - Show status update
  - Check cache age

Every 15 minutes:
  - Auto-refresh option chain
  - Update cached Greeks and contract details
```

## Benefits

### Before Enrichment
```sql
SELECT strike_price, delta, gamma, theta, vega, rho, implied_volatility
FROM options_bars
WHERE data_source = 'schwabdev_stream'
LIMIT 5;

-- Result: All NULL!
 strike_price | delta | gamma | theta | vega | rho | implied_volatility
--------------+-------+-------+-------+------+-----+-------------------
         NULL |  NULL |  NULL |  NULL | NULL | NULL | NULL
         NULL |  NULL |  NULL |  NULL | NULL | NULL | NULL
         NULL |  NULL |  NULL |  NULL | NULL | NULL | NULL
```

### After Enrichment
```sql
SELECT strike_price, delta, gamma, theta, vega, rho, implied_volatility
FROM options_bars
WHERE data_source = 'schwabdev_stream'
LIMIT 5;

-- Result: Populated from option chain!
 strike_price | delta  | gamma   | theta  | vega  | rho   | implied_volatility
--------------+--------+---------+--------+-------+-------+-------------------
      6100.00 | 0.5200 | 0.00120 | -15.30 | 12.50 |  8.20 | 0.185
      6110.00 | 0.4800 | 0.00115 | -14.80 | 12.20 |  7.90 | 0.182
      6090.00 | 0.5600 | 0.00125 | -15.80 | 12.80 |  8.50 | 0.188
```

## Performance Impact

### REST API Calls

- **Startup**: 1 call to fetch option chain (~500ms)
- **Runtime**: 1 call every 15 minutes (~500ms)
- **Per quote**: 0 calls (uses cache)

### Memory Usage

- Cache size: ~287 contracts × ~500 bytes = **~140 KB**
- Negligible impact on total memory

### Latency

- Quote enrichment: **< 1ms** (dictionary lookup)
- No impact on streaming throughput

## Configuration

### Adjust Cache Refresh Interval

Edit `scripts/enrich_stream_with_chain.py`:

```python
class OptionContractEnricher:
    def __init__(self, schwab_client):
        self.refresh_interval_minutes = 15  # Change this (default: 15)
```

### Adjust Strike Count

More strikes = larger cache but better coverage:

```python
# In stream_spxw_schwabdev.py start() method
self.enricher.refresh_contract_details("$SPX", strike_count=50)  # Increase if needed
```

## Limitations

### Greeks Staleness

- Greeks are calculated values that change continuously
- Cache provides snapshot from last refresh (up to 15 min old)
- For backtesting: This is acceptable (15-min refresh is sufficient)
- For live trading decisions: Consider refreshing more frequently

### Missing Contracts

- If a new contract is listed mid-session, it won't be in cache until next refresh
- Auto-refresh (every 15 min) mitigates this
- Can manually refresh: `enricher.refresh_contract_details()`

### Option Chain API Limits

- Schwab has rate limits on REST API calls
- Current strategy (15-min refresh) is well within limits
- Don't set refresh interval < 5 minutes

## Troubleshooting

### Cache not populating

```bash
# Check if enricher can fetch chain
python scripts/enrich_stream_with_chain.py
```

If it fails:
- Check Schwab API credentials in `.env`
- Verify token is valid: `ls -la tokens/schwabdev_tokens.db`
- Check API rate limits

### Still seeing NULLs in database

```sql
-- Check data source
SELECT data_source, COUNT(*)
FROM options_bars
GROUP BY data_source;

-- If showing 'schwabdev_stream', check when data was inserted
SELECT MAX(timestamp) FROM options_bars WHERE data_source = 'schwabdev_stream';
```

If data is old (before enrichment was added):
- New data will have enriched fields
- Old data will remain NULL (re-sync or backfill)

### Cache too small

```
Contract cache: 15 contracts  ← Too small!
Contracts streaming: 145      ← Streaming more than cached
```

**Solution**: Increase `strike_count` in `refresh_contract_details()`:

```python
self.enricher.refresh_contract_details("$SPX", strike_count=100)  # Increased
```

## Alternative Approaches

### Option 1: Parse from Symbol (Strike Price Only)

```python
# SPXW  251219C06100000
#              ^ C = Call
#               ^^^^^^^^ 06100000 = Strike × 1000

def parse_strike_from_symbol(symbol: str) -> float:
    # Extract last 8 digits and divide by 1000
    strike_str = symbol[-8:]
    return float(strike_str) / 1000.0
```

**Pros**: No API calls
**Cons**: Only gets strike, not Greeks or IV

### Option 2: Real-time Option Chain Polling

Poll option chain on every bar flush (every 60s):

**Pros**: Most up-to-date Greeks
**Cons**: High API usage, rate limit issues

### Option 3: Hybrid (Current Implementation)

Use cached Greeks (15-min refresh) + parse strike from symbol as fallback:

**Pros**: Best balance of accuracy and API efficiency
**Cons**: Slightly stale Greeks (acceptable for most use cases)

## Related Files

- `scripts/stream_spxw_schwabdev.py` - Main streaming script
- `scripts/enrich_stream_with_chain.py` - Enrichment module
- `src/quant_vibe/data/timescale_store.py` - Database storage
- `docs/SPXW_FIX.md` - Original streaming troubleshooting

## Summary

**The enrichment solution**:
- ✅ Populates Greeks, strike price, and IV in database
- ✅ Minimal API usage (1 call per 15 minutes)
- ✅ No performance impact on streaming
- ✅ Auto-refreshes to stay current
- ✅ Provides complete data for backtesting

**Run the updated stream**:
```bash
python scripts/stream_spxw_schwabdev.py
```

Watch debug output to confirm fields are being enriched!
