# Expiration Date Parsing Fix

## Problem

The streaming script (`stream_spxw_schwabdev.py`) was storing NULL `expiration_date` values for many contracts because:
- The script relied on Schwab's streaming API providing `exp_year`, `exp_month`, and `exp_day` fields
- These fields were often missing from the quote data
- Without these fields, `expiration_date` was set to NULL

This caused backtests to only find a small fraction of available contracts because the DTE (days-to-expiration) filter in `get_options_for_backtest()` requires valid expiration dates.

## Solution

### 1. Fallback Parsing in Streaming Script

Updated `stream_spxw_schwabdev.py` to parse expiration dates from the option ticker symbol as a fallback:

**Added Helper Function** (lines 92-139):
```python
def parse_expiration_from_ticker(ticker: str) -> Optional[datetime]:
    """
    Parse expiration date from SPXW option ticker.

    Format: SPXW  YYMMDDX########
    Example: SPXW  260121P06200000 = Jan 21, 2026 Put
    """
```

**Updated flush_to_database()** (lines 471-473):
```python
# Fallback: parse expiration date from ticker symbol if not available from quote data
if exp_date is None:
    exp_date = parse_expiration_from_ticker(symbol)
```

### 2. Backfill Script for Existing Data

Created `scripts/backfill_expiration_dates.py` to fix existing NULL values:

```bash
# Check what would be updated
python scripts/backfill_expiration_dates.py --dry-run

# Backfill all NULL expiration dates
python scripts/backfill_expiration_dates.py
```

## Impact

**Before Fix:**
- Backtest for today (2025-12-17) with `min_dte=0, max_dte=0`: **1 contract**, 1 bar
- 2,702 contracts had NULL expiration_date

**After Fix:**
- Backtest for today with `min_dte=0, max_dte=0`: **100 contracts**, 34,114 bars
- All contracts now have valid expiration dates

## Usage

### For Future Streaming
No action needed - the streaming script now automatically parses expiration dates from tickers when Schwab API fields are missing.

### For Existing Data
Run the backfill script once to fix historical data:

```bash
source venv/bin/activate
python scripts/backfill_expiration_dates.py
```

The script is safe to run multiple times - it only updates NULL values.

## Technical Details

### SPXW Ticker Format
```
SPXW  251217P05900000
      ^^^^^^ ^^^^^^^^^
      |      |
      |      Strike price (padded to 8 digits)
      |
      YYMMDD + P/C (expiration date + option type)
```

- `YY` = Year (25 = 2025)
- `MM` = Month (12 = December)
- `DD` = Day (17 = 17th)
- `P/C` = Put or Call
- Strike = Last 8 digits / 1000 (05900000 → 5900.0)

### Validation
Tested with various ticker formats:
- ✅ `SPXW  260121P06200000` → 2026-01-21
- ✅ `SPXW251217P05900000` (no spaces) → 2025-12-17
- ✅ Invalid formats return None

## Related Files

- `scripts/stream_spxw_schwabdev.py` - Updated streaming script
- `scripts/backfill_expiration_dates.py` - Backfill tool for existing data
- `src/quant_vibe/data/timescale_store.py` - Database queries using expiration_date

## Date
Fixed: December 17, 2025
