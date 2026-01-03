># QuantVibe Notification System

Real-time push notifications for trading events via Pushover.

## Table of Contents

- [Overview](#overview)
- [Setup](#setup)
- [Basic Usage](#basic-usage)
- [Trading Integration](#trading-integration)
- [Configuration](#configuration)
- [Priority Levels](#priority-levels)
- [Sounds](#sounds)
- [Testing](#testing)
- [Examples](#examples)

## Overview

The QuantVibe notification system sends real-time push notifications to your mobile devices and desktop via [Pushover](https://pushover.net). Get instant alerts for:

- **Trading Events**: Order fills, position opens/closes, P&L updates
- **Risk Alerts**: Daily loss limits, drawdown warnings, position limits
- **System Events**: Engine start/stop, errors, data issues
- **Daily Summaries**: End-of-day trading statistics

### Why Pushover?

- ✅ Reliable push notifications to iOS, Android, and desktop
- ✅ No monthly fees (one-time $5 per platform after 30-day trial)
- ✅ Rich notification features (priorities, sounds, attachments)
- ✅ Simple API with high rate limits
- ✅ Works anywhere (doesn't require VPN or special network setup)

## Setup

### 1. Create Pushover Account

1. Sign up at https://pushover.net
2. Download the Pushover app on your device(s)
3. Note your **User Key** from the dashboard

### 2. Create Application

1. Go to https://pushover.net/apps/build
2. Create a new application (e.g., "QuantVibe Trading")
3. Note your **API Token/Key**

### 3. Configure Environment

Add to your `.env` file:

```bash
# Pushover Configuration
PUSHOVER_API_TOKEN=your_api_token_here
PUSHOVER_USER_KEY=your_user_key_here
PUSHOVER_DEVICE=                          # Optional: specific device name
PUSHOVER_ENABLED=true                     # Optional: enable/disable (default: true)
```

### 4. Install Dependencies

```bash
pip install requests python-dotenv
```

### 5. Test Configuration

```bash
python scripts/test_pushover.py
```

You should receive test notifications on your device(s).

## Basic Usage

### Quick Notification

```python
from quant_vibe.notifications import send_notification, NotificationPriority

# Simple notification
send_notification("Markets are open", "Trading Alert")

# High priority with custom sound
send_notification(
    message="Order filled: 1 SPX 6200P @ $2.50",
    title="Order Filled",
    priority=NotificationPriority.HIGH,
    sound="cashregister"
)
```

### Using PushoverNotifier

```python
from quant_vibe.notifications import PushoverNotifier, NotificationPriority

# Initialize
notifier = PushoverNotifier()

# Validate credentials
if notifier.validate():
    print("Pushover configured correctly")

# Send notification
notifier.send(
    title="Trading Update",
    message="Position opened: SPX 6200/6180 Bull Put Spread",
    priority=NotificationPriority.HIGH,
    url="https://your-dashboard.com",
    url_title="View Dashboard"
)
```

### Pre-built Trading Notifications

```python
from quant_vibe.notifications import PushoverNotifier

notifier = PushoverNotifier()

# Order filled
notifier.send_order_filled(
    symbol="SPXW 251231P06200",
    quantity=1,
    price=2.50,
    order_type="Limit"
)

# Position opened
notifier.send_position_opened(
    strategy="Bullish Put Spread",
    symbol="SPX 6200/6180",
    entry_price=250.00
)

# Position closed
notifier.send_position_closed(
    strategy="Bullish Put Spread",
    symbol="SPX 6200/6180",
    pnl=150.00,
    pnl_pct=60.0
)

# Critical alert
notifier.send_critical_alert(
    alert_type="Daily Loss Limit",
    message="Daily loss limit reached: $500"
)

# Warning
notifier.send_warning(
    warning_type="Data Stale",
    message="No data received for 5 minutes"
)
```

## Trading Integration

### Using TradingNotifier

The `TradingNotifier` class provides event-driven notifications with filtering and configuration:

```python
from quant_vibe.notifications import TradingNotifier

# Configure notification rules
config = {
    "notify_on_start": True,
    "notify_on_stop": True,
    "notify_on_position_open": True,
    "notify_on_position_close": True,
    "notify_on_order_fill": True,
    "notify_on_order_reject": True,
    "notify_on_risk_alert": True,
    "notify_on_error": True,
    "notify_daily_summary": True,
    "min_pnl_notify": 50.0,  # Only notify for P&L >= $50
    "pushover": {
        "enabled": True,
        # API token and user key loaded from environment
    }
}

notifier = TradingNotifier(config=config)

# Engine events
notifier.on_engine_start(
    mode="live",
    strategies=["Bullish Put Spread", "Iron Condor"]
)

# Position events
notifier.on_position_opened(
    strategy="BPS",
    symbol="SPX 6200/6180",
    entry_price=250.00
)

notifier.on_position_closed(
    strategy="BPS",
    symbol="SPX 6200/6180",
    pnl=75.00,
    pnl_pct=30.0
)

# Order events
notifier.on_order_filled(
    symbol="SPXW 251231P06200",
    quantity=1,
    price=2.50
)

notifier.on_order_rejected(
    symbol="SPXW 251231P06200",
    reason="Insufficient buying power"
)

# Risk alerts
notifier.on_risk_alert(
    alert_type="Daily Loss Limit",
    message="Approaching limit: $480/$500",
    severity="warning"
)

# Errors
notifier.on_error(
    error_type="API Connection",
    message="Failed to connect to Schwab API",
    critical=True
)

# Daily summary
notifier.send_daily_summary(
    date=datetime.now(),
    trades=5,
    pnl=250.00,
    win_rate=80.0
)
```

### Integrating with LiveTradingEngine

Example integration in your live trading engine:

```python
from quant_vibe.notifications import TradingNotifier

class LiveTradingEngine:
    def __init__(self, config_path: str):
        # ... existing init code ...

        # Initialize notifications
        self.notifier = TradingNotifier(
            config=self.config.get('notifications', {}),
            logger=self.logger
        )

    def start(self):
        # ... existing start code ...

        # Notify on start
        self.notifier.on_engine_start(
            mode="live" if not self.paper_trading else "paper",
            strategies=[s.name for s in self.strategies]
        )

    def stop(self):
        # ... existing stop code ...

        # Notify on stop
        stats = {
            'trades': self.total_trades,
            'pnl': self.total_pnl
        }
        self.notifier.on_engine_stop(
            reason="Manual stop",
            stats=stats
        )

    def _on_position_opened(self, position):
        # ... existing code ...

        # Send notification
        self.notifier.on_position_opened(
            strategy=position.strategy_name,
            symbol=position.symbol,
            entry_price=position.entry_price
        )

    def _on_order_filled(self, order):
        # ... existing code ...

        # Send notification
        self.notifier.on_order_filled(
            symbol=order.symbol,
            quantity=order.quantity,
            price=order.fill_price
        )
```

## Configuration

### Notification Config (YAML)

Add to `config/live_trading.yaml`:

```yaml
notifications:
  # Engine events
  notify_on_start: true
  notify_on_stop: true

  # Position events
  notify_on_position_open: true
  notify_on_position_close: true

  # Order events
  notify_on_order_fill: true
  notify_on_order_reject: true

  # Risk & errors
  notify_on_risk_alert: true
  notify_on_error: true

  # Daily summary (sent at market close)
  notify_daily_summary: true

  # P&L threshold (optional)
  min_pnl_notify: 50.0  # Only notify if |P&L| >= $50

  # Pushover settings (credentials from environment)
  pushover:
    enabled: true
    device: null  # All devices
```

### Environment Variables

```bash
# Required
PUSHOVER_API_TOKEN=your_app_token
PUSHOVER_USER_KEY=your_user_key

# Optional
PUSHOVER_DEVICE=iPhone           # Target specific device
PUSHOVER_ENABLED=true            # Enable/disable globally
```

## Priority Levels

Pushover supports 5 priority levels:

| Priority | Value | Behavior | Use Case |
|----------|-------|----------|----------|
| `LOWEST` | -2 | No notification/alert | Debug/verbose logging |
| `LOW` | -1 | No sound/vibration | FYI updates |
| `NORMAL` | 0 | Default notification | General updates |
| `HIGH` | 1 | Bypasses quiet hours | Important events |
| `EMERGENCY` | 2 | Requires acknowledgment | Critical alerts |

```python
from quant_vibe.notifications import NotificationPriority

# Emergency - requires acknowledgment
notifier.send(
    title="CRITICAL ALERT",
    message="Daily loss limit exceeded!",
    priority=NotificationPriority.EMERGENCY,
    retry=30,    # Retry every 30 seconds
    expire=3600  # Give up after 1 hour
)

# High - bypasses quiet hours
notifier.send(
    title="Order Filled",
    message="1 SPX 6200P @ $2.50",
    priority=NotificationPriority.HIGH
)

# Normal - default
notifier.send(
    title="Info",
    message="Market opens in 30 minutes",
    priority=NotificationPriority.NORMAL
)
```

## Sounds

Choose from 20+ notification sounds:

```python
from quant_vibe.notifications import PushoverSound

# Order filled - cash register sound
notifier.send(
    title="Order Filled",
    message="Trade executed",
    sound=PushoverSound.CASHREGISTER
)

# Critical alert - siren sound
notifier.send(
    title="ALERT",
    message="Risk limit breached",
    sound=PushoverSound.SIREN
)

# Warning - space alarm
notifier.send(
    title="Warning",
    message="Data delayed",
    sound=PushoverSound.SPACEALARM
)

# Silent
notifier.send(
    title="Update",
    message="Background update",
    sound=PushoverSound.NONE
)
```

Available sounds: `pushover` (default), `bike`, `bugle`, `cashregister`, `classical`, `cosmic`, `falling`, `gamelan`, `incoming`, `intermission`, `magic`, `mechanical`, `pianobar`, `siren`, `spacealarm`, `tugboat`, `alien`, `climb`, `persistent`, `echo`, `updown`, `vibrate`, `none`

## Testing

### Test Script

Run the comprehensive test script:

```bash
python scripts/test_pushover.py
```

This will test:
- ✅ Credential validation
- ✅ Basic notifications
- ✅ Trading-specific notifications
- ✅ Priority levels
- ✅ TradingNotifier integration

### Manual Testing

```python
from quant_vibe.notifications import PushoverNotifier

notifier = PushoverNotifier()

# Validate setup
if notifier.validate():
    print("✅ Pushover configured correctly")

    # Send test notification
    notifier.send(
        title="Test",
        message="If you see this, notifications are working!",
        priority=NotificationPriority.NORMAL
    )
```

## Examples

### Example 1: Simple Trade Alert

```python
from quant_vibe.notifications import send_notification

send_notification(
    message="Filled: 1 SPX 6200P @ $2.50\nP&L: +$125",
    title="Trade Executed"
)
```

### Example 2: Position Monitoring

```python
from quant_vibe.notifications import PushoverNotifier

notifier = PushoverNotifier()

# Position opened
notifier.send_position_opened(
    strategy="Iron Condor",
    symbol="SPX 6200/6180/6050/6030",
    entry_price=420.00
)

# Position closed (profit)
notifier.send_position_closed(
    strategy="Iron Condor",
    symbol="SPX 6200/6180/6050/6030",
    pnl=210.00,
    pnl_pct=50.0
)
```

### Example 3: Risk Management Alerts

```python
from quant_vibe.notifications import PushoverNotifier, NotificationPriority

notifier = PushoverNotifier()

# Warning - approaching limit
notifier.send_warning(
    warning_type="Daily Loss Warning",
    message="Daily loss: $450/$500 (90% of limit)"
)

# Critical - limit breached
notifier.send_critical_alert(
    alert_type="Daily Loss Limit BREACHED",
    message="Daily loss: $520/$500\nTrading halted"
)
```

### Example 4: Engine Status

```python
from quant_vibe.notifications import PushoverNotifier

notifier = PushoverNotifier()

# Engine started
notifier.send_engine_started(
    mode="paper",
    strategies=["BPS", "Iron Condor", "Strangle"]
)

# Engine stopped
notifier.send_engine_stopped(
    reason="Market closed",
    stats={
        'trades': 12,
        'pnl': 425.00,
        'win_rate': 75.0
    }
)
```

### Example 5: Daily Summary

```python
from quant_vibe.notifications import PushoverNotifier
from datetime import datetime

notifier = PushoverNotifier()

notifier.send_daily_summary(
    date=datetime.now(),
    trades=15,
    pnl=375.50,
    win_rate=73.3
)
```

## Troubleshooting

### Notifications not received

1. **Check credentials**: Verify `PUSHOVER_API_TOKEN` and `PUSHOVER_USER_KEY` are correct
2. **Validate**: Run `notifier.validate()` to check credentials
3. **Check enabled**: Ensure `PUSHOVER_ENABLED=true` (or omit for default)
4. **Device name**: If using `PUSHOVER_DEVICE`, verify the name matches exactly
5. **Rate limits**: Pushover has rate limits (250/month for free apps, higher for licensed)

### Validation fails

```python
notifier = PushoverNotifier()
if not notifier.validate():
    print("Check your PUSHOVER_API_TOKEN and PUSHOVER_USER_KEY")
```

### Testing in development

Disable notifications during development:

```bash
# .env
PUSHOVER_ENABLED=false
```

Or in code:

```python
notifier = PushoverNotifier(enabled=False)
```

## API Limits

- **Free**: 10,000 messages/month
- **Licensed** ($5 one-time per platform): Unlimited messages
- **Rate limits**: 250 messages/month for apps without licensing

For production use, consider licensing your application at https://pushover.net/pricing

## Additional Resources

- **Pushover API**: https://pushover.net/api
- **Pushover FAQ**: https://pushover.net/faq
- **Supported devices**: https://pushover.net/clients
- **Sound samples**: https://pushover.net/api#sounds

## Summary

The QuantVibe notification system provides:

✅ Real-time push notifications for all trading events
✅ Configurable priority levels and sounds
✅ Event filtering and P&L thresholds
✅ Easy integration with live trading engine
✅ Reliable delivery via Pushover
✅ Works on iOS, Android, and desktop

Stay informed about your trading activity anywhere, anytime!
