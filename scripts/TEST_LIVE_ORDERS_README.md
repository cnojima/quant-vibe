# Live Order Testing Scripts

Test scripts for validating Schwab API live order submission without risk of fills.

## ⚠️ IMPORTANT SAFETY NOTES

1. **These scripts place REAL orders** to your Schwab brokerage account
2. Orders use extremely low prices ($0.01) that will **never fill**
3. Always cancel orders after testing (or they'll expire as GTC)
4. Verify cancellation in your Schwab account after testing
5. **DO NOT** modify prices closer to market without understanding the risk

## Scripts

### 1. `test_live_order_simple.py` - Quick Manual Test

**Best for**: Quick verification with manual symbol entry.

**Usage**:
```bash
source venv/bin/activate
python scripts/test_live_order_simple.py
```

**You must edit the script** to set:
- `TEST_SYMBOL`: A valid SPXW option symbol
- `TEST_STRIKE`: The strike price
- `TEST_EXPIRATION`: Expiration date (YYYY-MM-DD)

**Flow**:
1. Confirms with user before submission
2. Submits order at $0.01
3. Displays order ID and broker ID
4. Prompts to cancel order
5. Cancels if confirmed

### 2. `test_live_order_submission.py` - Automatic Chain Lookup

**Best for**: Fully automated testing that finds current ATM options.

**Usage**:
```bash
source venv/bin/activate
python scripts/test_live_order_submission.py
```

**Flow**:
1. Fetches SPX current price
2. Finds ATM call expiring next Friday
3. Shows option details
4. Confirms with user before submission
5. Submits order at $0.01
6. Displays order results
7. Prompts to cancel order
8. Cancels if confirmed

**Advantages**:
- No manual symbol lookup required
- Always uses current market data
- More realistic test of full workflow

## What Gets Tested

Both scripts validate:
- ✅ Schwab API authentication
- ✅ Account number fetching
- ✅ Order structure building
- ✅ Multi-leg order support (can be extended)
- ✅ Order submission to Schwab
- ✅ Broker order ID extraction
- ✅ Order cancellation
- ✅ Error handling

## Expected Output

### Successful Test
```
SCHWAB LIVE ORDER TEST
Testing order placement with never-fillable price ($0.01)
======================================================================

1. Initializing Schwab client...
   ✓ Schwab client initialized

2. Initializing OrderManager (LIVE MODE)...
   ✓ OrderManager initialized in LIVE mode

...

7. Submitting order to Schwab...
   ⚠️  This will submit a REAL order to Schwab!
   Price is $0.01 so it will NEVER fill

   Continue? (yes/no): yes

   ✓ Order submitted successfully!
   Order ID: ORD_abc123def456
   Broker Order ID: 123456789
   Status: submitted

8. Cancel order?
   Cancel the order? (yes/no): yes

   Cancelling order...
   ✓ Order cancelled: Order cancelled successfully
```

## Troubleshooting

### Authentication Error
```
⚠️  Authentication required: ...
```
**Solution**: Run `python scripts/authorize_schwab.py` to set up OAuth tokens.

### No Accounts Found
```
✗ No Schwab accounts found
```
**Solution**: Verify your API credentials have access to account data.

### Order Submission Failed
```
✗ Order submission failed: ...
```
**Check**:
1. API credentials are valid
2. Account is approved for options trading
3. Symbol format is correct (SPXW uses OCC format)
4. Check Schwab API status

### Cancel Failed - Order Not Found
```
✗ Failed to cancel: order not found
```
**Possible causes**:
1. Order already filled (unlikely at $0.01)
2. Order already cancelled
3. Order ID mismatch

**Action**: Check your Schwab account to verify order status.

## Integration with Live Trading

Once tests pass, the same code works in production by:

1. Setting `paper_trading=False` in OrderManager
2. Using real market prices instead of $0.01
3. Monitoring order status until filled
4. Implementing position tracking

## Next Steps

After successful testing:
- [ ] Implement order status polling
- [ ] Add partial fill handling
- [ ] Build position reconciliation
- [ ] Set up production monitoring
- [ ] Configure risk limits

## Safety Checklist

Before running tests:
- [ ] Verified Schwab account has limited funds
- [ ] Confirmed order price is $0.01
- [ ] Understood orders are REAL
- [ ] Have plan to cancel orders
- [ ] Not during market hours (for GTC orders)

After running tests:
- [ ] Checked Schwab account for pending orders
- [ ] Cancelled all test orders
- [ ] Verified no unexpected fills
- [ ] Documented any issues

---

**Remember**: These are REAL orders to REAL accounts. Always verify in Schwab after testing!
