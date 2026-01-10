# Scheduler Service

The scheduler service is a Docker-based cron alternative that runs scheduled tasks at specific times.

## Overview

Since crontab and launchd have platform issues, this service provides a reliable, containerized way to run scheduled tasks. It uses Python's `schedule` library with timezone-aware scheduling.

## Current Scheduled Tasks

### Nightly Backfill (3:00 PM PST Daily)

Runs the backfill job that:
1. Marks expired options contracts (`--mark-expired`)
2. Backfills active options with Greeks data (`--active-only --batch-size 500`)

This corresponds to the `scripts/backfill-nightly.sh` script.

## Architecture

- **Dockerfile**: `docker/Dockerfile.scheduler`
- **Scheduler Script**: `scripts/run_scheduler.py`
- **Docker Compose Service**: `scheduler` in `docker-compose.yml`

## Usage

### Start the Scheduler Service

```bash
docker-compose up -d scheduler
```

### View Scheduler Logs

```bash
docker-compose logs -f scheduler
```

### Stop the Scheduler Service

```bash
docker-compose stop scheduler
```

### Restart the Scheduler Service

```bash
docker-compose restart scheduler
```

## Configuration

The scheduler service is configured via environment variables in `docker-compose.yml`:

- **TZ**: Set to `America/Los_Angeles` for PST/PDT timezone
- **TIMESCALE_HOST**: TimescaleDB host (uses Docker service name)
- **SCHWAB_API_KEY/SECRET**: Schwab API credentials for backfill scripts
- **LOG_LEVEL**: Logging verbosity (default: INFO)

## Adding New Scheduled Tasks

To add new scheduled tasks, edit `scripts/run_scheduler.py`:

1. Create a function for your task:
```python
def my_scheduled_task():
    logger.info("Running my scheduled task")
    # Your task logic here
```

2. Schedule it in the `main()` function:
```python
# For timezone-aware scheduling (recommended)
def run_at_time():
    now = datetime.now(PST)
    if now.hour == 14 and now.minute == 0:  # 2pm PST
        my_scheduled_task()

schedule.every(1).minutes.do(run_at_time)
```

3. Rebuild and restart the service:
```bash
docker-compose build scheduler
docker-compose restart scheduler
```

## Timezone Handling

The service handles Pacific Time (PST/PDT) correctly, including automatic DST transitions:

- Uses `pytz` library for timezone-aware datetime objects
- Container TZ environment variable set to `America/Los_Angeles`
- Checks every minute if it's the scheduled time in PST/PDT

## Dependencies

The scheduler service depends on:
- TimescaleDB (for backfill scripts to store data)
- Schwab API credentials (for fetching options data)

## Troubleshooting

### Task Not Running at Expected Time

1. Check container logs for errors:
   ```bash
   docker-compose logs scheduler
   ```

2. Verify timezone is correct:
   ```bash
   docker-compose exec scheduler date
   ```

3. Check next scheduled run time in logs (appears at startup)

### Backfill Job Failing

1. Verify TimescaleDB is healthy:
   ```bash
   docker-compose ps timescaledb
   ```

2. Check Schwab API credentials are set in `.env`

3. Review detailed error logs:
   ```bash
   docker-compose logs -f scheduler
   ```

### Container Not Starting

1. Check for syntax errors in `run_scheduler.py`:
   ```bash
   docker-compose logs scheduler
   ```

2. Verify all environment variables are set

3. Rebuild the container:
   ```bash
   docker-compose build --no-cache scheduler
   docker-compose up -d scheduler
   ```

## Testing

To test the scheduler without waiting for the scheduled time:

1. Modify the schedule temporarily in `scripts/run_scheduler.py`:
```python
# Test: run every minute instead of at 3pm
schedule.every(1).minutes.do(run_backfill_job)
```

2. Rebuild and monitor:
```bash
docker-compose build scheduler
docker-compose up scheduler  # Run in foreground to see logs
```

3. Revert the schedule change after testing

## Manual Execution

To manually run the backfill job without the scheduler:

```bash
docker-compose exec scheduler python /app/scripts/backfill/backfill_stream_greeks.py --mark-expired
docker-compose exec scheduler python /app/scripts/backfill/backfill_stream_greeks.py --active-only --batch-size 500
```

## Monitoring

The scheduler logs:
- Startup time and current time in both UTC and PST
- Next scheduled run time
- Task execution start/completion
- Any errors during execution

Monitor these logs to ensure the scheduler is working correctly.
