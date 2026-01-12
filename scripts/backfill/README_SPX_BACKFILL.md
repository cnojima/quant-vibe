# SPX Options Backfill Script

## Overview

`massive_spx_options.py` is a comprehensive script for backfilling historical SPX/SPXW options data from the Massive API into TimescaleDB.

## Features

✅ **Automatic Symbol Normalization**
- Converts Massive API format (`O:SPXW251224P06900000`) to database format (`SPXW251224P06900000`)
- Handles contract_type as lowercase ('call' or 'put')

✅ **SPXW Daily Expirations**
- Supports daily SPXW expirations (Mon-Fri)
- Automatically excludes market holidays
- PM-settled options (expires 4:00 PM ET)

✅ **Flexible DTE Range**
- Default: 0-2 DTE data (same day, 1 day, 2 days before expiration)
- Configurable via `--max-dte` flag

✅ **Automatic Greeks Enrichment**
- Calls `backfill_stream_greeks.py` after data insertion
- Enriches data with delta, gamma, theta, vega, rho, IV
- Can be disabled with `--no-greeks` for faster backfills

✅ **Bid/Ask Estimation**
- Estimates bid/ask spreads based on option price and DTE
- More accurate for 0 DTE (wider spreads)
- Minimum spread: $0.05

## Contract Symbol Format

### Massive API Format (Input)
```
O:SPXW251224P06900000
│ │    │     │ │
│ │    │     │ └─ Strike: 06900000 (6900.0 * 1000)
│ │    │     └─── Type: P (put) or C (call)
│ │    └───────── Expiration: 251224 (Dec 24, 2025)
│ └────────────── Underlying: SPXW
└──────────────── Options prefix
```

### Database Format (Output)
```
SPXW251224P06900000
│   │     │ │
│   │     │ └─ Strike: 06900000 (6900.0 * 1000)
│   │     └─── Type: P (put) or C (call)
│   └───────── Expiration: 251224 (Dec 24, 2025)
└─────────── Underlying: SPXW

Stored with:
- option_ticker: "SPXW251224P06900000" (normalized, no O:)
- underlying_ticker: "SPX" (not "SPXW")
- contract_type: "put" or "call" (lowercase)
- strike_price: 6900.0 (float)
- expiration_date: 2025-12-24 (date)
```

## Usage

### Basic Usage

```bash
# Backfill recent data (last 30 days)
python scripts/backfill/massive_spx_options.py \
  --start 2025-11-24 \
  --end 2025-12-24
```

### Custom DTE Range

```bash
# Backfill 0-5 DTE data
python scripts/backfill/massive_spx_options.py \
  --start 2025-07-01 \
  --end 2025-12-12 \
  --max-dte 5
```

### Custom Strike Range

```bash
# Backfill specific strike range
python scripts/backfill/massive_spx_options.py \
  --start 2025-07-01 \
  --end 2025-12-12 \
  --strike-min 6000.0 \
  --strike-max 7000.0
```

### Skip Greeks Enrichment

```bash
# Faster backfill without Greeks (can enrich later)
python scripts/backfill/massive_spx_options.py \
  --start 2025-07-01 \
  --end 2025-12-12 \
  --no-greeks
```

### Large Backfill

```bash
# Backfill large date range with custom batch size
python scripts/backfill/massive_spx_options.py \
  --start 2025-01-01 \
  --end 2025-12-31 \
  --max-dte 5 \
  --batch-size 2000
```

## Command-Line Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--start` | Required | - | Start date (YYYY-MM-DD) |
| `--end` | Required | - | End date (YYYY-MM-DD) |
| `--strike-min` | Float | 5000.0 | Minimum strike price |
| `--strike-max` | Float | 7500.0 | Maximum strike price |
| `--max-dte` | Int | 2 | Maximum days to expiration (0-N) |
| `--batch-size` | Int | 1000 | Database insert batch size |
| `--no-greeks` | Flag | False | Skip Greeks enrichment |

## Output

The script inserts data into the `options_bars` TimescaleDB table with these columns:

| Column | Type | Description |
|--------|------|-------------|
| `timestamp` | TIMESTAMPTZ | Bar timestamp (1-minute resolution) |
| `option_ticker` | TEXT | Normalized contract symbol (SPXW...) |
| `underlying_ticker` | TEXT | Always "SPX" for SPXW |
| `strike_price` | FLOAT | Strike price (e.g., 6900.0) |
| `contract_type` | TEXT | 'call' or 'put' (lowercase) |
| `expiration_date` | DATE | Expiration date |
| `open`, `high`, `low`, `close` | FLOAT | OHLC prices |
| `volume` | INT | Trading volume |
| `vwap` | FLOAT | Volume-weighted average price |
| `transactions` | INT | Number of transactions |
| `bid`, `ask` | FLOAT | Estimated bid/ask (initial) |
| `delta`, `gamma`, `theta`, `vega`, `rho` | FLOAT | Greeks (from enrichment) |
| `implied_volatility` | FLOAT | IV (from enrichment) |
| `data_source` | TEXT | 'massive' |

## Data Flow

```
1. Fetch SPXW contracts from Massive API
   ↓
2. For each contract:
   - Fetch 1-minute bars (0 to max-dte days before expiration)
   - Parse contract details (strike, type, expiration)
   - Estimate bid/ask spreads
   ↓
3. Normalize symbols (O:SPXW... → SPXW...)
   ↓
4. Bulk insert into options_bars table
   ↓
5. Run backfill_stream_greeks.py (unless --no-greeks)
   - Fetch Greeks from Schwab API
   - Update records with delta, gamma, theta, vega, rho, IV
   ↓
6. Complete!
```

## Greeks Enrichment

The script automatically runs `backfill_stream_greeks.py` after inserting data, which:

1. Queries Schwab option chain API for contract details
2. Caches Greeks for all active contracts
3. Updates `options_bars` records with:
   - `delta`: Option delta (0-1 for calls, -1-0 for puts)
   - `gamma`: Rate of change of delta
   - `theta`: Time decay per day
   - `vega`: Sensitivity to volatility
   - `rho`: Sensitivity to interest rates
   - `implied_volatility`: Implied volatility (IV)

**Note:** Greeks enrichment requires Schwab API credentials in `.env`:
```bash
SCHWAB_API_KEY=your_api_key
SCHWAB_API_SECRET=your_api_secret
SCHWAB_CALLBACK_URL=https://quantvibe.net:53430/
SCHWAB_TOKENS_DB=./tokens/schwabdev_tokens.db
```

## Error Handling

### Contract Parsing Errors
- Invalid contract symbols are logged and skipped
- Processing continues with remaining contracts

### API Rate Limits
- Massive API has rate limits (check your subscription)
- Script uses batching to minimize API calls
- Add delays between large batches if needed

### Database Errors
- Failed insertions are logged
- Transaction rollback prevents partial data
- Script can be re-run safely (idempotent)

### Greeks Enrichment Errors
- If enrichment fails, data is still in database
- Run `backfill_stream_greeks.py` manually to retry
- Use `--no-greeks` to skip enrichment entirely

## Troubleshooting

### No contracts found
```
⚠️  No SPXW contracts found (found X SPX contracts)
```

**Solution:** Adjust strike range with `--strike-min` and `--strike-max`

### Greeks enrichment fails
```
❌ Error running Greeks backfill: ...
```

**Solution:**
1. Check Schwab API credentials in `.env`
2. Run enrichment manually: `python scripts/backfill/backfill_stream_greeks.py --start YYYY-MM-DD --end YYYY-MM-DD`

### Out of memory
```
MemoryError: Unable to allocate...
```

**Solution:** Reduce `--batch-size` (e.g., `--batch-size 500`)

### Slow performance

**Solution:**
1. Reduce date range (backfill in smaller chunks)
2. Reduce DTE range (`--max-dte 1`)
3. Reduce strike range
4. Skip Greeks initially (`--no-greeks`)

## Manual Greeks Enrichment

If you skipped Greeks enrichment or it failed, run manually:

```bash
# Enrich all data
python scripts/backfill/backfill_stream_greeks.py \
  --start 2025-07-01 \
  --end 2025-12-12

# Dry run (preview only)
python scripts/backfill/backfill_stream_greeks.py \
  --start 2025-07-01 \
  --end 2025-12-12 \
  --dry-run

# Check statistics
python scripts/backfill/backfill_stream_greeks.py --stats-only
```

## Performance Tips

1. **Use smaller date ranges** - Backfill in monthly chunks
2. **Adjust batch size** - Larger batches = fewer DB round trips
3. **Skip Greeks initially** - Use `--no-greeks` for faster initial load
4. **Filter strikes** - Only backfill relevant strikes (e.g., ±10% from ATM)
5. **Use DTE filtering** - Only backfill needed DTEs (e.g., 0-2 DTE)

## Related Scripts

- `backfill_0dte_spxw-massive.py` - Original SPXW backfill (legacy)
- `backfill_stream_greeks.py` - Standalone Greeks enrichment
- `backfill_spx_underlying_1min.py` - SPX index underlying data

## Database Schema

See `src/quant_vibe/data/schema/init_timescale.sql` for complete schema definition.

## Dependencies

- `massive` - Massive API client (formerly Polygon)
- `schwabdev` - Schwab API client (for Greeks)
- `psycopg2` - PostgreSQL adapter
- `pandas` - Data manipulation

Install:
```bash
pip install -e ".[dev,backtest,schwab]"
```

## Environment Variables

Required in `.env`:

```bash
# Massive API (for historical data)
MASSIVE_API_KEY=your_massive_api_key

# Schwab API (for Greeks enrichment)
SCHWAB_API_KEY=your_schwab_api_key
SCHWAB_API_SECRET=your_schwab_secret
SCHWAB_CALLBACK_URL=https://quantvibe.net:53430/
SCHWAB_TOKENS_DB=./tokens/schwabdev_tokens.db

# TimescaleDB
TIMESCALE_HOST=localhost
TIMESCALE_PORT=5432
TIMESCALE_DB=options_data
TIMESCALE_USER=quantvibe
TIMESCALE_PASSWORD=quantvibe_dev
```

## License

Same as parent project (see LICENSE file).
