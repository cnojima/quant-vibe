# Pushover Notifications - Quick Start

Get mobile notifications when optimizations complete in just 5 minutes!

## Why Use Pushover?

Optimizations can take 5-60+ minutes to run. Instead of constantly checking the UI, get an instant push notification on your phone when:
- ✅ Optimization completes successfully (with results)
- ❌ Optimization fails (with error message)
- ⏱️ Optimization times out

## 5-Minute Setup

### Step 1: Create Account (2 minutes)
1. Go to [pushover.net](https://pushover.net)
2. Sign up for free
3. Buy the app ($5 one-time for iOS or Android)
4. Install Pushover app on your phone

### Step 2: Get Credentials (1 minute)
1. Log in to [pushover.net](https://pushover.net)
2. Copy your **User Key** from the top of the page
3. Scroll to "Your Applications" → Click "Create an Application/API Token"
4. Name it "Quant-Vibe" and create
5. Copy your **API Token**

### Step 3: Configure (1 minute)
Add to your `.env` file:
```bash
PUSHOVER_API_TOKEN=your_api_token_here
PUSHOVER_USER_KEY=your_user_key_here
PUSHOVER_ENABLED=true
```

### Step 4: Test (1 minute)
1. Restart backend (if running): `docker-compose restart admin_ui_backend`
2. Open Admin UI: `http://localhost:5173/notifications`
3. Click "Send Test Notification"
4. Check your phone! 📱

## What You'll Get

**Success Notification Example:**
```
✅ Optimization Complete: bullish_vertical_put
Optimization opt_20260101_143022 finished successfully.
Best Sharpe: 2.45
Best Return: +12.34%
Runtime: 23.5 min
```

**Failure Notification Example:**
```
❌ Optimization Failed: bullish_vertical_put
Optimization opt_20260101_143022 failed.
Error: Database connection timeout
Runtime: 5.2 min
```

## Typical Workflow

1. **Start optimization** in Admin UI → Optimize tab
2. **Go do other work** - no need to watch progress bar
3. **Get notification** on your phone when done
4. **Review results** when convenient

## Cost

- **One-time:** $5 per platform (iOS/Android)
- **Ongoing:** FREE for 10,000 messages/month
- **No subscriptions or monthly fees**

Perfect for optimizations that run 1-2 times per day!

## Troubleshooting

**Not receiving notifications?**
1. Check credentials in `.env` are correct
2. Verify `PUSHOVER_ENABLED=true`
3. Restart backend: `docker-compose restart admin_ui_backend`
4. Test again from UI

**Still not working?**
See full documentation: `docs/PUSHOVER_NOTIFICATIONS.md`

## Next Steps

- ✅ Setup complete? Run your first optimization!
- 📖 Learn more: `docs/PUSHOVER_NOTIFICATIONS.md`
- 🎯 Optimize strategies: `docs/OPTIMIZATION_UI_GUIDE.md`
