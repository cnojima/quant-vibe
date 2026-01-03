# LaunchDaemon Setup for Backfill Greeks

This directory contains the LaunchDaemon configuration for automated backfilling of Greeks data.

## Installation

1. **Copy the plist to LaunchAgents directory:**
   ```bash
   cp launchd/com.quantvibe.backfill-greeks.plist ~/Library/LaunchAgents/
   ```

2. **Load the job:**
   ```bash
   launchctl load ~/Library/LaunchAgents/com.quantvibe.backfill-greeks.plist
   ```

3. **Verify it's loaded:**
   ```bash
   launchctl list | grep quantvibe
   ```

## Management Commands

**Start the job immediately:**
```bash
launchctl start com.quantvibe.backfill-greeks
```

**Stop the job:**
```bash
launchctl stop com.quantvibe.backfill-greeks
```

**Unload the job:**
```bash
launchctl unload ~/Library/LaunchAgents/com.quantvibe.backfill-greeks.plist
```

**Reload after changes:**
```bash
launchctl unload ~/Library/LaunchAgents/com.quantvibe.backfill-greeks.plist
cp launchd/com.quantvibe.backfill-greeks.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.quantvibe.backfill-greeks.plist
```

## Schedule

The job is configured to run **daily at 6:00 PM (18:00)**.

To change the schedule, edit the `StartCalendarInterval` section in the plist:
- `Hour`: 0-23 (24-hour format)
- `Minute`: 0-59

Example schedules:
```xml
<!-- Every day at 2:30 AM -->
<key>StartCalendarInterval</key>
<dict>
    <key>Hour</key>
    <integer>2</integer>
    <key>Minute</key>
    <integer>30</integer>
</dict>

<!-- Multiple times per day -->
<key>StartCalendarInterval</key>
<array>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <dict>
        <key>Hour</key>
        <integer>18</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</array>
```

## Execution Order

The job runs two commands sequentially:

1. **Mark Expired Contracts:**
   ```bash
   python ./scripts/backfill/backfill_stream_greeks.py --mark-expired
   ```
   This marks expired contracts with sentinel values to exclude them from future queries.

2. **Backfill Active Contracts:**
   ```bash
   python ./scripts/backfill/backfill_stream_greeks.py --active-only
   ```
   This backfills only active (non-expired) contracts with full Greeks data.

## Logs

Logs are written to:
- **stdout**: `/Users/curisu/dev/quant-vibe/logs/backfill_greeks_stdout.log`
- **stderr**: `/Users/curisu/dev/quant-vibe/logs/backfill_greeks_stderr.log`

View logs:
```bash
tail -f logs/backfill_greeks_stdout.log
tail -f logs/backfill_greeks_stderr.log
```

## Troubleshooting

**Job not running:**
1. Check if it's loaded: `launchctl list | grep quantvibe`
2. Check logs for errors
3. Verify permissions: `ls -la ~/Library/LaunchAgents/com.quantvibe.backfill-greeks.plist`
4. Test manually: `launchctl start com.quantvibe.backfill-greeks`

**Python environment issues:**
- The plist activates the virtual environment before running
- If using a different Python path, update the `ProgramArguments` section

**Permission errors:**
- Ensure the user running launchd has read/write access to the project directory
- Check TimescaleDB connection credentials in `.env`

## Environment Variables

The job uses environment variables from your `.env` file (via the bash script execution context). If you need to add specific env vars to the LaunchDaemon, add them to the `EnvironmentVariables` dict in the plist.

## Notes

- LaunchDaemon runs as a background process
- It will NOT run if your Mac is asleep (consider using `caffeinate` or scheduling during active hours)
- The job runs in the context of your user account (LaunchAgent, not LaunchDaemon)
- For system-wide daemons (running as root), use `/Library/LaunchDaemons/` instead
