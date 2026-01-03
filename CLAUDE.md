# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.


### Documentation

- Always use `source venv/bin/activate` before executing a python command
- Schwab API uses `$SPX` as the underlying symbol for SPXW contracts
- don't assume localhost for the timescaleDB and redis.  check the flags in .env

#### Schema & Data Layer Documentation

**IMPORTANT**: When working with schemas, timestamps, or data transformations:

1. **Schema Reference**: See `docs/SCHEMA_MAPPING.md` for:
   - Column name mappings (`option_ticker` ↔ `contract_symbol`)
   - Symbol format standards and normalization
   - Timestamp timezone requirements (always UTC-aware)
   - Data type constraints and validation rules
   - DataFrame schema contracts

2. **Simplification Roadmap**: See `docs/SIMPLIFICATION_PLAN.md` for:
   - Current complexity issues and root causes
   - Pydantic migration plan (long-term)
   - Quick wins already implemented
   - Best practices for avoiding schema bugs

3. **Timestamp Utilities**: Always use `quant_vibe.utils.timestamp_utils`:
   ```python
   from quant_vibe.utils import now_utc, to_utc, ensure_utc_aware

   # ✅ CORRECT: Use these functions
   timestamp = now_utc()  # Always UTC-aware
   utc_dt = to_utc(naive_dt)  # Convert to UTC

   # ❌ WRONG: Never use these
   timestamp = datetime.now()  # Naive local time
   timestamp = datetime.utcnow()  # Naive UTC
   ```

4. **Schema Tests**: Run before deploying:
   ```bash
   pytest tests/integration/test_schema_consistency.py -v
   ```