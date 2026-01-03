# Pushover Notifications Guide

## Overview

Pushover notifications alert you on your mobile device when long-running tasks complete. This is especially useful for:

- **Optimizations** (can take 5-60+ minutes)
- **Backtests** (large date ranges)
- **System errors** (failures, timeouts)

You'll get instant push notifications with results summary, eliminating the need to constantly check the UI.

## Features

### Optimization Notifications

**Success Notifications:**
- ✅ Notification title: "Optimization Complete: {strategy_name}"
- Best Sharpe ratio found
- Best return percentage
- Runtime in minutes
- Sound: "cashregister" (success sound)
- Priority: Normal

**Failure Notifications:**
- ❌ Notification title: "Optimization Failed: {strategy_name}"
- Error message (truncated to 200 chars)
- Runtime before failure
- Sound: "siren" (alert sound)
- Priority: High (overrides quiet hours)

**Example Success Notification:**
```
✅ Optimization Complete: bullish_vertical_put
Optimization opt_20260101_143022 finished successfully.
Best Sharpe: 2.45
Best Return: +12.34%
Runtime: 23.5 min
```

**Example Failure Notification:**
```
❌ Optimization Failed: bullish_vertical_put
Optimization opt_20260101_143022 failed.
Error: Database connection timeout
Runtime: 5.2 min
```

### Backtest Notifications (Future)

Planned support for backtest completion notifications with:
- Total return
- Sharpe ratio
- Number of trades
- Runtime

## Setup Instructions

### 1. Create Pushover Account

1. Go to [pushover.net](https://pushover.net)
2. Create a free account
3. **Cost:** $5 one-time per platform (iOS/Android)
   - Unlimited apps and notifications
   - No monthly fees or limits
   - 10,000 messages/month included

### 2. Install Pushover App

Download the Pushover app on your mobile device:
- **iOS:** [App Store](https://apps.apple.com/us/app/pushover-notifications/id506088175)
- **Android:** [Google Play](https://play.google.com/store/apps/details?id=net.superblock.pushover)

### 3. Get Your Credentials

**User Key:**
1. Log in to [pushover.net](https://pushover.net)
2. Your user key is displayed at the top of the dashboard
3. Format: `uQiRzpo4DXghDmr9QzzfQu27cmVRsG` (example)

**API Token:**
1. Scroll down to "Your Applications" section
2. Click "Create an Application/API Token"
3. Fill in:
   - **Name:** Quant-Vibe Trading System
   - **Type:** Application
   - **Description:** Notifications for trading system optimizations
   - **URL:** (optional) Your admin UI URL
   - **Icon:** (optional) Upload an icon
4. Click "Create Application"
5. Copy your API token (e.g., `azGDORePK8gMaC0QOYAMyEEuzJnyUi`)

### 4. Configure Environment Variables

Add to your `.env` file:

```bash
# Pushover Push Notifications
PUSHOVER_API_TOKEN=azGDORePK8gMaC0QOYAMyEEuzJnyUi  # Your app token
PUSHOVER_USER_KEY=uQiRzpo4DXghDmr9QzzfQu27cmVRsG   # Your user key
PUSHOVER_ENABLED=true                                # Enable notifications
```

**Optional Settings:**
```bash
PUSHOVER_DEVICE=                                     # Specific device name (leave empty for all)
```

### 5. Install Python Package

Pushover requires the `requests` library (already included in requirements):

```bash
pip install requests
```

### 6. Test Notifications

**Method 1: Admin UI** (Recommended)
1. Navigate to **Notifications** in the sidebar
2. Click "Send Test Notification"
3. Check your phone for the notification

**Method 2: Python Script**
```python
from quant_vibe.utils import get_notifier

notifier = get_notifier()
notifier.send(
    message="Test notification",
    title="Test",
    priority=0,
)
```

**Method 3: Command Line**
```bash
python -c "from quant_vibe.utils import send_notification; send_notification('Test', 'Test')"
```

## Configuration

### Environment Variables

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `PUSHOVER_API_TOKEN` | Yes | Application API token | None |
| `PUSHOVER_USER_KEY` | Yes | User/group key | None |
| `PUSHOVER_ENABLED` | No | Enable/disable notifications | `true` if credentials provided |
| `PUSHOVER_DEVICE` | No | Specific device name | All devices |

### Priority Levels

Notifications use different priorities for different events:

| Priority | Value | Use Case | Behavior |
|----------|-------|----------|----------|
| Silent | -2 | Debug/verbose events | No sound, no vibration |
| Quiet | -1 | Low-priority info | No sound |
| Normal | 0 | Successful completions | Standard notification |
| High | 1 | Failures/errors | Bypasses quiet hours |
| Emergency | 2 | Critical alerts | Requires acknowledgment |

**Current Usage:**
- Optimization success: Normal (0)
- Optimization failure: High (1)
- Optimization timeout: High (1)

### Sounds

Different sounds for different event types:

| Sound | Use Case |
|-------|----------|
| `magic` | Test notifications |
| `cashregister` | Successful optimizations |
| `siren` | Failures and errors |
| `pushover` | Default sound |

Full list: https://pushover.net/api#sounds

## Usage in Code

### Send Custom Notification

```python
from quant_vibe.utils import send_notification

send_notification(
    message="Custom message",
    title="Custom Title",
    priority=0,
    sound="magic",
)
```

### Send Optimization Notification

```python
from quant_vibe.utils import get_notifier

notifier = get_notifier()

# Success
notifier.send_optimization_complete(
    strategy_name="bullish_vertical_put",
    optimization_id="opt_20260101_143022",
    best_sharpe=2.45,
    best_return=12.34,
    runtime_minutes=23.5,
)

# Failure
notifier.send_optimization_failed(
    strategy_name="bullish_vertical_put",
    optimization_id="opt_20260101_143022",
    error_message="Database connection timeout",
    runtime_minutes=5.2,
)
```

### Send Backtest Notification

```python
from quant_vibe.utils import get_notifier

notifier = get_notifier()

# Success
notifier.send_backtest_complete(
    strategy_name="bullish_vertical_put",
    backtest_id="bt_20260101_143022",
    total_return=12.34,
    sharpe_ratio=2.45,
    num_trades=45,
)

# Failure
notifier.send_backtest_failed(
    strategy_name="bullish_vertical_put",
    backtest_id="bt_20260101_143022",
    error_message="Insufficient data",
)
```

## Troubleshooting

### Notifications Not Sending

**Check 1: Credentials**
```bash
# Verify environment variables are set
echo $PUSHOVER_API_TOKEN
echo $PUSHOVER_USER_KEY
echo $PUSHOVER_ENABLED
```

**Check 2: Enable Status**
```python
from quant_vibe.utils import get_notifier

notifier = get_notifier()
print(f"Enabled: {notifier.enabled}")
print(f"User Key: {notifier.user_key[:10]}..." if notifier.user_key else "None")
print(f"API Token: {notifier.api_token[:10]}..." if notifier.api_token else "None")
```

**Check 3: Test API**
```bash
curl -s \
  --form-string "token=YOUR_API_TOKEN" \
  --form-string "user=YOUR_USER_KEY" \
  --form-string "message=Test" \
  https://api.pushover.net/1/messages.json
```

Expected response:
```json
{"status":1,"request":"xxx-xxx-xxx"}
```

### Invalid Credentials Error

Error: `user identifier is invalid`
- Double-check your user key (not API token)
- Make sure there are no extra spaces or quotes

Error: `application token is invalid`
- Double-check your API token (not user key)
- Create a new application token if needed

### Notifications Disabled

If you see `[Pushover] Notifications disabled, skipping`:
1. Check `PUSHOVER_ENABLED` is set to `true`
2. Verify credentials are present in `.env`
3. Restart backend after updating `.env`

### Rate Limits

Pushover free tier includes:
- **10,000 messages/month**
- **10 messages/minute per user**

If you hit limits:
- Check for infinite loops sending notifications
- Review notification frequency settings
- Consider upgrading to paid tier ($5/month for 100k messages)

## Advanced Features

### Group Notifications

Send to multiple users:
1. Create a group at pushover.net
2. Use group key instead of user key
3. All group members receive notifications

### Device-Specific Notifications

Send to a specific device:
```python
notifier = PushoverNotifier()
notifier.send(
    message="Test",
    title="Test",
    device="iphone",  # or "android", etc.
)
```

### URL Supplementary Links (Future)

Add deep links to notifications:
```python
notifier.send(
    message="Optimization complete",
    title="Success",
    url="http://localhost:5173/optimize",
    url_title="View Results",
)
```

### Emergency Notifications

Require user acknowledgment:
```python
notifier.send(
    message="Critical system error!",
    title="URGENT",
    priority=2,  # Emergency
    retry=30,    # Retry every 30 seconds
    expire=3600, # Give up after 1 hour
)
```

## Cost Summary

**One-Time Costs:**
- iOS App: $5 (one-time)
- Android App: $5 (one-time)
- Total: $5-10 depending on platforms

**Ongoing Costs:**
- Free tier: 10,000 messages/month
- Paid tier: $5/month for 100,000 messages
- No other fees or limits

**Return on Investment:**
- Save time checking optimization status
- Get instant alerts for failures
- Work on other tasks while optimizations run
- Peace of mind with mobile notifications

## Security Considerations

**Credential Protection:**
- Store credentials in `.env` (gitignored)
- Never commit credentials to version control
- Use environment variables for deployment

**API Token Permissions:**
- Tokens are scoped to your application
- Can revoke/regenerate tokens anytime
- No access to other Pushover features

**Message Content:**
- Avoid including sensitive data in messages
- Error messages are truncated to 200 chars
- Consider using codes instead of detailed errors

## Related Documentation

- **Pushover API Docs:** https://pushover.net/api
- **Python API Wrapper:** `src/quant_vibe/utils/pushover.py`
- **Optimization Guide:** `docs/OPTIMIZATION_UI_GUIDE.md`
- **Admin UI Settings:** Navigate to `/notifications` in UI
