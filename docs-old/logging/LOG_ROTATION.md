# Log Rotation - EST Calendar Day

## Overview

The quant-vibe logging system now includes **automatic log rotation based on US Eastern Time (EST/EDT) calendar days**. This ensures that logs rotate consistently at midnight EST regardless of the server's timezone or daylight saving time changes.

## Features

- **EST-based rotation**: Logs rotate at midnight Eastern Time, not local server time
- **Automatic file naming**: Files include date suffix (e.g., `app_20251230.log`)
- **Rotation history**: Rotated files include `_EST` suffix (e.g., `app_20251230.log.2025-12-29_EST`)
- **Configurable retention**: Default keeps 30 days of log history
- **Timezone-aware timestamps**: All log timestamps displayed in EST
- **Normalized format**: Consistent `[datetime][app][level][msg]` format

## How It Works

### EST Timezone Handling

The logging system uses Python's `pytz` library to handle EST timezone consistently:

1. **Log timestamps**: All timestamps in log messages are displayed in EST
2. **File naming**: Log file names use EST date (YYYYMMDD format)
3. **Rotation timing**: Files rotate at midnight EST (00:00:00 America/New_York)
4. **Rotated file suffix**: Includes `_EST` to indicate timezone

### Rotation Behavior

```
Current log file: app_20251230.log
After midnight EST:
  - Old file renamed to: app_20251230.log.2025-12-30_EST
  - New file created: app_20251231.log
```

### Retention Policy

- **Default**: 30 days of rotated logs are kept
- **Configurable**: Can be changed via `backupCount` parameter
- **Automatic cleanup**: Files older than retention period are deleted automatically

## Usage

### Basic Setup

```python
from quant_vibe.config.logging_config import setup_normalized_logging

# Create logger with EST rotation
logger = setup_normalized_logging(
    app_name="my_app",
    log_level="INFO",
    log_dir="logs/my_app",
)

# Log messages (timestamps will be in EST)
logger.info("Application started")
logger.warning("Warning message")
logger.error("Error occurred", exc_info=True)
```

### Advanced Configuration

```python
from quant_vibe.config.unified_logging import setup_normalized_logging

# Custom configuration
logger = setup_normalized_logging(
    app_name="my_service",
    log_level="DEBUG",
    log_dir="logs/services",
    log_file="custom_name_20251230.log",  # Custom filename
    console_output=True,  # Enable console output
    include_func=False,  # Don't include function names in console
)
```

### Direct Use of ESTTimedRotatingFileHandler

```python
import logging
from quant_vibe.config.unified_logging import ESTTimedRotatingFileHandler, NormalizedFormatter

# Create logger
logger = logging.getLogger("my_app")

# Create EST rotating handler
handler = ESTTimedRotatingFileHandler(
    filename="logs/my_app.log",
    when='midnight',     # Rotate at midnight
    interval=1,          # Every 1 day
    backupCount=30,      # Keep 30 days
    encoding='utf-8'
)

# Add formatter
formatter = NormalizedFormatter(app_name="my_app")
handler.setFormatter(formatter)
logger.addHandler(handler)
```

## Log Format

### Console Output (simplified)
```
[2025-12-30 12:00:00][my_app][INFO    ] Application started
[2025-12-30 12:00:01][my_app][WARNING ] Database connection slow
[2025-12-30 12:00:02][my_app][ERROR   ] Failed to process order
```

### File Output (detailed)
```
[2025-12-30 12:00:00][my_app][INFO    ][main:42] Application started
[2025-12-30 12:00:01][my_app][WARNING ][db_connect:105] Database connection slow
[2025-12-30 12:00:02][my_app][ERROR   ][process_order:234] Failed to process order
                                                            Traceback (most recent call last):
                                                              File "orders.py", line 232, in process_order
                                                                result = api.submit(order)
                                                            ValueError: Invalid order amount
```

## Testing

Run the test script to verify log rotation:

```bash
python scripts/test_log_rotation.py
```

Expected output:
```
============================================================
Log Rotation Test - EST Timezone
============================================================
Current EST time: 2025-12-30 12:25:18 EST
Current UTC time: 2025-12-30 17:25:18 UTC
============================================================

[2025-12-30 12:25:18][rotation_test][INFO    ] Testing log rotation based on EST calendar day
...

Log files in logs/rotation_test:
  - rotation_test_20251230.log (1257 bytes)

============================================================
Log rotation configured to rotate at midnight EST
Rotated files will have suffix: YYYY-MM-DD_EST
Keeping last 30 days of logs
============================================================
```

## File Structure

Typical log directory after several days:

```
logs/my_app/
├── my_app_20251230.log              # Current day (active)
├── my_app_20251230.log.2025-12-29_EST  # Yesterday's log
├── my_app_20251229.log.2025-12-28_EST  # 2 days ago
├── my_app_20251228.log.2025-12-27_EST  # 3 days ago
└── ...                              # Up to 30 days retained
```

## Implementation Details

### ESTTimedRotatingFileHandler Class

```python
class ESTTimedRotatingFileHandler(TimedRotatingFileHandler):
    """
    TimedRotatingFileHandler that rotates at midnight EST.

    Key features:
    - Uses America/New_York timezone for rotation
    - Computes rollover at midnight EST
    - Adds _EST suffix to rotated files
    """
```

### Key Methods

**computeRollover(currentTime)**
- Converts current time to EST
- Calculates next midnight EST
- Returns UTC timestamp for rotation

**format(record)**
- Formats timestamps in EST
- Includes timezone indicator
- Handles multi-line messages and stack traces

## Timezone Handling

### Why EST?

- **Market hours**: US stock markets operate in EST
- **Trading consistency**: All trading data aligned to market timezone
- **Log correlation**: Easy to correlate logs with market events
- **Team coordination**: Standard timezone for entire trading system

### Daylight Saving Time

The system automatically handles EST/EDT transitions:
- Uses `pytz.timezone('America/New_York')`
- Automatically adjusts for daylight saving time
- Transparent to users - always shows correct local time

### Example Timezone Conversion

```
Server time: 2025-12-30 09:00:00 PST (Pacific)
Log timestamp: 2025-12-30 12:00:00 EST (Eastern)
Log rotation: 2025-12-31 00:00:00 EST (midnight Eastern)
```

## Configuration

### Retention Period

Change the number of days to keep logs:

```python
logger = setup_normalized_logging(
    app_name="my_app",
    log_level="INFO",
    log_dir="logs/my_app",
)

# Handler is already configured with backupCount=30
# To change: access handler directly
for handler in logger.handlers:
    if isinstance(handler, ESTTimedRotatingFileHandler):
        handler.backupCount = 60  # Keep 60 days instead
```

### Custom Rotation Schedule

While the default is midnight rotation, you can customize:

```python
from quant_vibe.config.unified_logging import ESTTimedRotatingFileHandler

# Hourly rotation
handler = ESTTimedRotatingFileHandler(
    filename="logs/my_app.log",
    when='H',           # Hour
    interval=1,         # Every 1 hour
    backupCount=168,    # Keep 1 week (7*24 hours)
)

# Weekly rotation
handler = ESTTimedRotatingFileHandler(
    filename="logs/my_app.log",
    when='W0',          # Monday
    interval=1,         # Every 1 week
    backupCount=52,     # Keep 1 year
)
```

## Dependencies

- **pytz**: Timezone handling (`pip install pytz`)
  - Added to `pyproject.toml` dependencies
  - Already installed with standard quant-vibe installation

## Troubleshooting

### Logs not rotating at expected time

1. Check server timezone: `date` (should not matter, but verify)
2. Check EST time: `TZ=America/New_York date`
3. Verify log handler: Check if using `ESTTimedRotatingFileHandler`
4. Check log file permissions: Ensure write access to log directory

### Multiple log files created

- Expected behavior: New file starts each day at midnight EST
- Rotated files keep previous day's logs
- Check `backupCount` setting for retention

### Timestamp mismatch

- All timestamps should be in EST
- If seeing UTC or local time, check logger configuration
- Verify using `NormalizedFormatter` class

## Benefits

1. **Consistency**: All services use same timezone regardless of server location
2. **Market alignment**: Logs aligned with trading day (market hours)
3. **Easy correlation**: Match logs with market events and trades
4. **Automatic cleanup**: Old logs removed based on retention policy
5. **DST handling**: Automatic daylight saving time adjustments
6. **Standard format**: Normalized format across all components

## Migration from Old Logging

If you're using the old logging setup:

```python
# OLD: Basic file handler
file_handler = logging.FileHandler('logs/app.log')

# NEW: EST rotating handler (automatic in setup_normalized_logging)
logger = setup_normalized_logging(app_name="app", log_dir="logs")
```

No code changes needed if already using `setup_normalized_logging()` - rotation is now automatic!

## See Also

- `CLAUDE.md` - Logging section for general logging guidelines
- `src/quant_vibe/config/unified_logging.py` - Implementation details
- `scripts/test_log_rotation.py` - Test script and examples
