## LIVE ORDERS - STATUS

### ✅ COMPLETED
- [x] Live order submission (`_submit_to_schwab`)
- [x] Order structure builder (`_build_schwab_order_structure`)
- [x] Live order cancellation (`_cancel_schwab_order`)
- [x] OCO order submission (`_submit_schwab_oco_order`)
- [x] Multi-leg spread orders support
- [x] Opening and closing orders (BUY_TO_OPEN, SELL_TO_CLOSE, etc.)
- [x] LIMIT and MARKET order types
- [x] Broker order ID tracking
- [x] Account number auto-fetch and caching

### 🧪 TESTING
**Test Scripts Available**:
1. `test_live_order_simple.py` - Quick manual test with hardcoded symbol
2. `test_live_order_submission.py` - Auto-finds ATM SPXW option

⚠️ **IMPORTANT**: These place REAL orders at $0.01 (never fills). See `scripts/TEST_LIVE_ORDERS_README.md` for details.

**Quick Start**:
```bash
source venv/bin/activate
python scripts/test_live_order_submission.py  # Automatic
# or
python scripts/test_live_order_simple.py      # Manual symbol
```

**Safety**:
- Orders submitted at $0.01 (way below market)
- Will NOT fill during test
- Automatic cancellation option
- Always verify in Schwab account after test

### 📋 TODO
- [ ] Order status polling/monitoring
- [ ] Handle partial fills
- [ ] Position reconciliation with broker
- [ ] Multiple account support (currently uses account[0])
- [ ] Retry logic for API failures
- [ ] Rate limiting / throttling