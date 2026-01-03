# Schwab Quote Enrichment for Options Data

This document explains how to enrich Massive options data with real-time quotes from Schwab, including bid/ask spreads and Greeks.

## Overview

The data collection script can combine two data sources:
1. **Massive API**: 1-minute OHLCV bars for options contracts
2. **Schwab API**: Real-time quotes with bid/ask and Greeks

This hybrid approach gives you:
- Historical intraday price action from Massive
- Current market quotes and Greeks from Schwab
- Complete dataset stored in TimescaleDB

## Prerequisites

### 1. Install Schwab Dependencies

```bash
pip install -e ".[schwab]"
```

### 2. Configure Schwab API

Add to your `.env` file:
```bash
# Schwab API Configuration
SCHWAB_API_KEY=your_api_key_here
SCHWAB_API_SECRET=your_app_secret_here
SCHWAB_CALLBACK_URL=https://quantvibe.net:53430/
SCHWAB_TOKEN_PATH=./tokens/schwab_token.json
```

### 3. Complete OAuth Authentication

On first run, you'll need to complete OAuth:
1. A browser window will open
2. Log in to your Schwab account
3. Authorize the application
4. Copy the full redirect URL
5. Paste when prompted

The token will be saved for future use.

## How It Works

### Ticker Format Conversion

Massive and Schwab use different option ticker formats:

**Massive Format:**
```
O:SPXW251226P02000000
│ │    │     │ │
│ │    │     │ └─ Strike: 02000000 (2000.0 * 1000)
│ │    │     └─── Type: P=Put, C=Call
│ │    └───────── Expiration: YYMMDD (251226 = Dec 26, 2025)
│ └────────────── Underlying: SPXW
└──────────────── Options prefix
```

**Schwab/OCC Format:**
```
SPXW  251226P02000000
│     │     │ │
│     │     │ └─ Strike: 02000000 (8 digits)
│     │     └─── Type: C or P
│     └───────── Expiration: YYMMDD
└─────────────── Underlying (6 chars, space-padded)
```

The script automatically converts between formats.

### Data Enrichment Process

1. **Fetch bars from Massive** - Get 1-minute OHLCV data
2. **Convert ticker format** - Massive format → Schwab format
3. **Get quote from Schwab** - Fetch current bid/ask and Greeks
4. **Merge data** - Add quote fields to each bar
5. **Store in database** - Insert enriched data to TimescaleDB

### What Gets Added

When you use `--enrich-schwab`, each bar is enriched with:

**Quote Data:**
- `bid` - Current bid price
- `ask` - Current ask price
- `bid_size` - Bid size (contracts)
- `ask_size` - Ask size (contracts)

**Greeks:**
- `delta` - Rate of change of price with underlying
- `gamma` - Rate of change of delta
- `theta` - Time decay per day
- `vega` - Sensitivity to volatility
- `rho` - Sensitivity to interest rate
- `implied_volatility` - Implied volatility percentage

## Usage

### Basic Collection (Massive Only)

```bash
# Just OHLCV data from Massive
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --from 2025-12-01 \
    --to 2025-12-14
```

Database will contain:
- ✅ OHLCV (open, high, low, close, volume)
- ✅ VWAP and transaction count
- ❌ Bid/ask (NULL)
- ❌ Greeks (NULL)

### Enriched Collection (Massive + Schwab)

```bash
# OHLCV + bid/ask + Greeks
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --from 2025-12-01 \
    --to 2025-12-14 \
    --enrich-schwab
```

Database will contain:
- ✅ OHLCV from Massive
- ✅ Bid/ask from Schwab
- ✅ Greeks from Schwab
- ✅ Implied volatility

### Testing the Enrichment

```bash
# Test ticker conversion and quote fetching
python scripts/test_schwab_enrichment.py
```

This will:
1. Test Massive → Schwab ticker conversion
2. Fetch a sample quote from Schwab
3. Demonstrate the enrichment process

## Important Notes

### Current vs Historical Quotes

⚠️ **Important**: The Schwab enrichment uses the **current quote** at the time of collection.

- If collecting **today's data**: Quote is accurate for recent bars
- If collecting **historical data**: Quote is current, not historical

**Recommendation:**
- For real-time/recent data: Use `--enrich-schwab`
- For historical analysis: Massive data alone is sufficient

### Rate Limiting

- Massive API: Check your plan's rate limits
- Schwab API: Generally allows 120 requests/minute
- Script includes built-in delays (0.1s between contracts)

### Data Availability

Not all fields are always available:

| Field | Availability |
|-------|-------------|
| Bid/Ask | Usually available during market hours |
| Greeks | Available for standard options |
| Implied Vol | Usually available |
| VWAP | From Massive, usually available |
| Transactions | From Massive, may be limited |

## Example Output

### Without Enrichment
```
[63/100] O:SPXW251226P02000000
  Strike: 2000.0 | Type: put | Exp: 2025-12-26
  ✓ Inserted 390 bars (OHLCV only)
```

### With Enrichment
```
[63/100] O:SPXW251226P02000000
  Strike: 2000.0 | Type: put | Exp: 2025-12-26
  ✓ Enriched with Schwab quote data (bid: 0.35, ask: 0.40)
  ✓ Inserted 390 bars (OHLCV + quotes + Greeks)
```

## Database Schema

Enriched data is stored in the `options_bars` table:

```sql
SELECT
    timestamp,
    option_ticker,
    -- OHLCV from Massive
    open, high, low, close, volume,
    -- Quote data from Schwab
    bid, ask, bid_size, ask_size,
    -- Greeks from Schwab
    delta, gamma, theta, vega, rho,
    implied_volatility
FROM options_bars
WHERE option_ticker = 'O:SPXW251226P02000000'
ORDER BY timestamp DESC
LIMIT 10;
```

## Troubleshooting

### "Could not convert ticker"
**Cause:** Invalid Massive ticker format
**Solution:** Verify the ticker follows the pattern `O:SYMBOL[YYMMDD][C/P][STRIKE]`

### "No quote data for [ticker]"
**Cause:** Option may not be trading or ticker format mismatch
**Solutions:**
- Verify the contract is currently active
- Check if the option is during market hours
- Test with a known active contract first

### "Schwab client not available"
**Cause:** schwab-py not installed
**Solution:** `pip install -e ".[schwab]"`

### Authentication Required
**Cause:** First-time setup or expired token
**Solution:**
1. Complete OAuth flow in browser
2. Authorize the application
3. Copy redirect URL when prompted

### Rate Limit Errors
**Cause:** Too many API requests
**Solutions:**
- Add longer delays with `--batch-size`
- Reduce number of contracts
- Collect data in smaller chunks

## Best Practices

1. **Test First**: Use `test_schwab_enrichment.py` before bulk collection
2. **Start Small**: Test with a single expiration before collecting all
3. **Market Hours**: Run during market hours for best quote data
4. **Error Handling**: Script continues on errors, check logs
5. **Token Management**: Keep `tokens/` directory in `.gitignore`

## Performance Considerations

With enrichment enabled:
- **Speed**: ~1 contract per second (includes Schwab API call)
- **Data**: ~2x data size (additional fields per bar)
- **Cost**: Uses both Massive and Schwab API quotas

Without enrichment:
- **Speed**: ~10 contracts per second
- **Data**: Standard OHLCV only
- **Cost**: Massive API only

## Example: Complete Workflow

```bash
# 1. Start TimescaleDB
docker-compose up -d

# 2. Test Schwab connection
python scripts/test_schwab_enrichment.py

# 3. Collect recent SPX data with enrichment
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --from 2025-12-13 \
    --to 2025-12-14 \
    --expiration 2025-12-20 \
    --strike-min 5800 \
    --strike-max 6000 \
    --enrich-schwab \
    --verbose

# 4. Query the enriched data
python -c "
from quant_vibe.data import TimescaleStore
from datetime import datetime

store = TimescaleStore()
bars = store.get_option_bars(
    'O:SPX251220C05900000',
    start_time=datetime(2025, 12, 13),
    end_time=datetime(2025, 12, 14)
)

print(f'Retrieved {len(bars)} bars')
print(bars[['Open', 'High', 'Low', 'Close', 'bid', 'ask', 'delta']].tail())
"
```

## See Also

- [TimescaleDB Setup Guide](TIMESCALE_SETUP.md)
- [Schwab Integration Documentation](SCHWAB_INTEGRATION.md)
- [Troubleshooting Guide](TROUBLESHOOTING.md)
