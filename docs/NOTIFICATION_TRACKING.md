# Notification Tracking System

## Overview

The notification tracking system provides comprehensive logging and auditing of all Pushover notifications sent by Quant-Vibe. All notifications are automatically stored in TimescaleDB for historical analysis and debugging.

## Features

- **Automatic Logging**: All notifications are logged to the database automatically
- **Rich Metadata**: Each notification stores type, priority, metadata, and success status
- **Web UI**: Browse notification history with filtering and pagination
- **Statistics Dashboard**: Analyze notification patterns and success rates
- **API Access**: RESTful API for programmatic access to notification data
- **Data Retention**: Configurable retention policies with manual cleanup

## Architecture

### Database Schema

The `notifications` table is a TimescaleDB hypertable partitioned by `sent_at` timestamp:

```sql
CREATE TABLE notifications (
    notification_id SERIAL,
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Content
    title TEXT,
    message TEXT NOT NULL,

    -- Classification
    notification_type TEXT NOT NULL,
    priority INTEGER DEFAULT 0,
    sound TEXT,
    device TEXT,

    -- Status
    sent_successfully BOOLEAN NOT NULL DEFAULT false,
    error_message TEXT,

    -- Metadata (JSON)
    metadata JSONB,

    -- URLs
    url TEXT,
    url_title TEXT,

    PRIMARY KEY (sent_at, notification_id)
);
```

**Features**:
- 7-day chunk interval for efficient time-based queries
- Automatic compression after 30 days
- Indexed by notification type, sent_at, and success status
- GIN index on metadata for fast JSON queries

### Notification Types

The system tracks the following notification types:

- `order_filled` - Order execution notifications
- `position_opened` - New position notifications
- `position_closed` - Position exit notifications
- `critical_alert` - Emergency alerts
- `warning` - Warning messages
- `info` - Informational messages
- `engine_started` - Trading engine start
- `engine_stopped` - Trading engine stop
- `daily_summary` - Daily trading summaries
- `optimization_complete` - Optimization success
- `optimization_failed` - Optimization failures
- `backtest_complete` - Backtest completion
- `backtest_failed` - Backtest failures
- `custom` - Custom notifications

### Priority Levels

- `-2` - Lowest (no notification/alert)
- `-1` - Low (no sound or vibration)
- `0` - Normal (default)
- `1` - High (bypasses quiet hours)
- `2` - Emergency (requires acknowledgment)

## Usage

### Sending Notifications (Python)

All helper methods automatically log to the database:

```python
from quant_vibe.notifications import PushoverNotifier

# Initialize notifier (database logging enabled by default)
notifier = PushoverNotifier()

# Send notification (automatically logged)
notifier.send_position_closed(
    strategy="BullishVerticalPut",
    symbol="SPXW260122P6180",
    pnl=125.50,
    pnl_pct=25.1
)

# Disable database logging if needed
notifier = PushoverNotifier(db_logging=False)
```

### API Endpoints

**Get Notification History**:
```bash
GET /api/notifications/history?page=1&per_page=50&notification_type=optimization_complete
```

Parameters:
- `page` - Page number (default: 1)
- `per_page` - Items per page (default: 50, max: 500)
- `notification_type` - Filter by type (optional)
- `start_date` - Filter by start date (optional)
- `end_date` - Filter by end date (optional)
- `sent_successfully` - Filter by success status (optional)

**Get Statistics**:
```bash
GET /api/notifications/stats?days=30
```

**Get Available Types**:
```bash
GET /api/notifications/types
```

**Delete Notification**:
```bash
DELETE /api/notifications/{notification_id}
```

**Cleanup Old Notifications**:
```bash
POST /api/notifications/cleanup?days=90
```

### Web UI

Navigate to **Notification History** in the Admin UI sidebar to:

1. **View Notification List**:
   - Filter by notification type
   - Show only failed notifications
   - Paginate through results
   - View metadata for each notification

2. **View Statistics**:
   - Select analysis period (7, 30, 90, 180, 365 days)
   - See notification counts by type
   - View success rates
   - Identify problematic notification types

3. **Cleanup**:
   - Delete notifications older than 90 days
   - Manage database size

## Database Functions

### get_recent_notifications()

Get recent notifications with optional type filter:

```sql
SELECT * FROM get_recent_notifications(100, 'optimization_complete');
```

### get_notification_stats()

Get statistics for a time period:

```sql
SELECT * FROM get_notification_stats('2026-01-01', '2026-01-31');
```

### cleanup_old_notifications()

Delete old notifications:

```sql
SELECT cleanup_old_notifications(90);  -- Delete notifications older than 90 days
```

## Files Created/Modified

### Database
- `scripts/migrations/001_add_notifications_table.sql` - Database migration

### Backend
- `src/quant_vibe/notifications/pushover.py` - Updated to log to database
- `src/admin_ui/backend/api/notifications.py` - API endpoints (NEW)
- `src/admin_ui/backend/main.py` - Added notifications router

### Frontend
- `src/admin_ui/frontend/src/pages/NotificationHistory.tsx` - History page (NEW)
- `src/admin_ui/frontend/src/components/layout/Sidebar.tsx` - Added navigation link
- `src/admin_ui/frontend/src/App.tsx` - Added route

## Migration

To apply the notification tracking table:

```bash
# Apply migration
docker exec -i quant-vibe-timescaledb psql -U quantvibe -d options_data < scripts/migrations/001_add_notifications_table.sql

# Verify table creation
docker exec quant-vibe-timescaledb psql -U quantvibe -d options_data -c "\\d notifications"
```

## Performance Considerations

- **Compression**: Data older than 30 days is automatically compressed
- **Indexes**: Optimized for filtering by type, time, and success status
- **Partitioning**: 7-day chunks for efficient time-based queries
- **Retention**: Optional automatic retention policy (disabled by default)

## Configuration

Database logging is enabled by default. To disable:

```python
# Disable for specific notifier instance
notifier = PushoverNotifier(db_logging=False)
```

No additional environment variables required. Uses existing TimescaleDB connection settings.

## Troubleshooting

### Database Connection Errors

If notifications fail to log to database:
1. Check TimescaleDB is running: `docker ps | grep timescale`
2. Verify connection settings in `.env`
3. Check application logs for database errors

### Missing Notifications

If notifications don't appear in the UI:
1. Verify migration was applied successfully
2. Check backend logs for API errors
3. Ensure notifications are being sent (check Pushover for confirmation)

### Performance Issues

If notification queries are slow:
1. Check table size: `SELECT count(*) FROM notifications;`
2. Run cleanup: `SELECT cleanup_old_notifications(90);`
3. Verify compression is working: `SELECT * FROM timescaledb_information.compressed_chunk_stats;`

## Future Enhancements

Potential improvements:
- Email notifications when failure rate exceeds threshold
- Real-time notification feed via WebSocket
- Export notification history to CSV
- Notification template management
- Rate limiting and throttling
- Notification scheduling
