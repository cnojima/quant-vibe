# SPXW Quick Reference

## TL;DR

**Problem**: `--ticker SPXW` showed "No contracts found"
**Root Cause**: SPXW contracts have `underlying_ticker="SPX"` in Massive API
**Fix**: Script now maps SPXW → SPX for queries and filters by ticker pattern

---

## SPX vs SPXW at a Glance

| Feature | SPX (Monthly) | SPXW (Weekly) |
|---------|---------------|---------------|
| **Ticker** | `O:SPX260116C05900000` | `O:SPXW251226C05900000` |
| **Underlying** | `SPX` | `SPX` (same!) |
| **Expiration** | 3rd Friday (monthly) | Multiple weekly |
| **Settlement** | AM (opening prices) | PM (closing prices) |
| **Use Case** | Long-term positions | 0DTE, short-term |

---

## How It Works Now

### When you use `--ticker SPXW`:
1. Script queries Massive API with `underlying_ticker="SPX"`
2. Gets all SPX contracts (monthly + weekly)
3. Filters to keep only `O:SPXW...` tickers
4. Returns SPXW weekly contracts only

### When you use `--ticker SPX`:
1. Script queries Massive API with `underlying_ticker="SPX"`
2. Gets all SPX contracts (monthly + weekly)
3. Filters to exclude `O:SPXW...` tickers
4. Returns SPX monthly contracts only

---

## Usage Examples

### Collect SPXW 0DTE
```bash
python scripts/collect_options_1min_data.py \
    --ticker SPXW \
    --from 2025-12-26 \
    --to 2025-12-26 \
    --expiration 2025-12-26 \
    --contract-type put \
    --strike-min 5800 \
    --strike-max 6000
```

### Collect SPX Monthly
```bash
python scripts/collect_options_1min_data.py \
    --ticker SPX \
    --from 2026-01-16 \
    --to 2026-01-16 \
    --expiration 2026-01-16 \
    --contract-type call \
    --strike-min 5900 \
    --strike-max 6100
```

---

## Expected Output

### SPXW (Working)
```
Fetching options contracts for SPXW...
  Note: SPXW uses underlying_ticker='SPX', filtering for weekly contracts
  Filtered 50 -> 25 contracts (pattern: SPXW)
Found 25 contracts

[1/25] O:SPXW251226C05900000
  Strike: 5900 | Type: call | Exp: 2025-12-26
```

### SPX (Working)
```
Fetching options contracts for SPX...
  Filtered 50 -> 25 contracts (pattern: SPX)
Found 25 contracts

[1/25] O:SPX260116C05900000
  Strike: 5900 | Type: call | Exp: 2026-01-16
```

---

## Common Errors

### "Your plan doesn't include this data timeframe"
```
Error: Your plan doesn't include this data timeframe.
```
- ✅ Contract discovery worked
- ❌ Your Massive/Polygon plan doesn't cover that timeframe
- **Fix**: Check plan at https://polygon.io/pricing

### "No contracts found"
- Check expiration date is valid for SPXW (check database for available dates)
- Use `--verbose` flag to see filtering details
- See [SPXW_FIX.md](docs/SPXW_FIX.md) for troubleshooting

---

## Check Available SPXW Expirations

```python
from quant_vibe.data import TimescaleStore

store = TimescaleStore()
conn = store.pool.getconn()
cursor = conn.cursor()

cursor.execute('''
    SELECT DISTINCT expiration_date
    FROM options_bars
    WHERE option_ticker LIKE '%SPXW%'
    ORDER BY expiration_date
''')

for row in cursor.fetchall():
    print(row[0])

store.pool.putconn(conn)
```

---

## See Also

- [docs/SPXW_FIX.md](docs/SPXW_FIX.md) - Complete technical details
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) - All common issues
- [docs/ENRICHMENT_FIX.md](docs/ENRICHMENT_FIX.md) - Schwab enrichment fix
