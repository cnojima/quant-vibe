# Real-Time SPXW Options Data Collection

This document explains how to collect SPXW options data in real-time using the quant-vibe system.

## Overview

Two approaches are available for real-time data collection:

1. **Websocket Streaming** (`stream_spxw_realtime.py`) - True real-time via Schwab websockets
2. **Polling** (`poll_spxw_quotes.py`) - Simpler, polls quotes every 60 seconds

Both methods collect:
- ✅ Bid/Ask quotes
- ✅ Options Greeks (delta, gamma, theta, vega, rho)
- ✅ Implied volatility
- ✅ Volume data
- ✅ Aggregated into 1-minute bars
- ✅ Stored in TimescaleDB

## Method 1: Websocket Streaming (Recommended for Production)

### Features
- True real-time updates via websocket
- Lower latency (updates as they happen)
- More efficient (single connection)
- Aggregates quotes into 1-minute OHLCV bars
- Automatic bar closing at minute boundaries

### Setup

```bash
# Ensure Schwab credentials are in .env
SCHWAB_API_KEY=your_api_key
SCHWAB_API_SECRET=your_app_secret
SCHWAB_CALLBACK_URL=https://127.0.0.1:8182/
SCHWAB_TOKEN_PATH=./tokens/schwab_token.json
SCHWAB_ACCOUNT_NUMBER=your_account_number

# Run the streaming collector
source venv/bin/activate
python scripts/stream_spxw_realtime.py
```

### Configuration

Edit `/Users/curisu/dev/quant-vibe/src/quant_vibe/data/realtime_collector.py`:

```python
collector = RealtimeOptionsCollector(
    max_dte=45,           # Maximum days to expiration
    min_dte=0,            # Minimum days to expiration (0 = include 0 DTE)
    strike_range_pct=0.10 # ±10% from ATM
)
```

### How It Works

1. Connects to Schwab websocket API
2. Gets current SPX price to determine ATM
3. Subscribes to SPXW contracts within DTE and strike range
4. Receives real-time quote updates
5. Aggregates quotes into 1-minute bars:
   - Open = first quote in minute
   - High = highest quote in minute
   - Low = lowest quote in minute
   - Close = last quote in minute
   - Volume = total volume
   - Bid/Ask/Greeks = latest values
6. Closes and saves bars to TimescaleDB every minute

## Method 2: Polling (Recommended for Testing)

### Features
- Simpler implementation (no websockets)
- More reliable for long-running collection
- Easier to debug and test
- Better for handling rate limits
- Polls every 60 seconds (configurable)

### Setup

```bash
source venv/bin/activate
python scripts/poll_spxw_quotes.py
```

### Configuration

Edit the script or parameters:

```python
poller = OptionsQuotePoller(
    poll_interval=60,     # Seconds between polls
    max_dte=45,           # Maximum DTE
    min_dte=0,            # Minimum DTE (0 = include 0 DTE)
    strike_range_pct=0.10 # ±10% from ATM
)
```

### How It Works

1. Gets active SPXW contracts from Massive API
2. Every 60 seconds:
   - Gets quotes for all contracts from Schwab API
   - Creates 1-minute bar from quote snapshot
   - Saves bars to TimescaleDB
3. Handles Schwab rate limits (50 symbols per batch)
4. Continues indefinitely until stopped

## Data Storage

Both methods store data in TimescaleDB `options_bars` table with:

```sql
- timestamp (TIMESTAMPTZ)
- option_ticker (TEXT)
- underlying_ticker (TEXT) = 'SPX'
- open, high, low, close (NUMERIC)
- volume (BIGINT)
- bid, ask, bid_size, ask_size (NUMERIC/INT)
- strike_price (NUMERIC)
- contract_type (TEXT) = 'call' or 'put'
- expiration_date (DATE)
- implied_volatility, delta, gamma, theta, vega, rho (NUMERIC)
- data_source (TEXT) = 'schwab_realtime' or 'schwab_poll'
```

## Monitoring

### Check that data is being collected:

```bash
docker exec quant-vibe-timescaledb psql -U quantvibe -d options_data -c "
SELECT
    data_source,
    COUNT(*) as bars,
    MIN(timestamp) as earliest,
    MAX(timestamp) as latest,
    COUNT(DISTINCT option_ticker) as contracts
FROM options_bars
WHERE data_source IN ('schwab_realtime', 'schwab_poll')
GROUP BY data_source;
"
```

### Check recent activity:

```bash
docker exec quant-vibe-timescaledb psql -U quantvibe -d options_data -c "
SELECT
    timestamp,
    option_ticker,
    close,
    bid,
    ask,
    delta,
    volume
FROM options_bars
WHERE data_source IN ('schwab_realtime', 'schwab_poll')
ORDER BY timestamp DESC
LIMIT 10;
"
```

## Running in Background

### Using screen:

```bash
screen -S spxw_stream
source venv/bin/activate
python scripts/poll_spxw_quotes.py

# Detach: Ctrl+A, then D
# Reattach: screen -r spxw_stream
```

### Using tmux:

```bash
tmux new -s spxw_stream
source venv/bin/activate
python scripts/poll_spxw_quotes.py

# Detach: Ctrl+B, then D
# Reattach: tmux attach -t spxw_stream
```

### Using systemd (Linux):

Create `/etc/systemd/system/spxw-collector.service`:

```ini
[Unit]
Description=SPXW Options Data Collector
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/quant-vibe
Environment="PATH=/path/to/quant-vibe/venv/bin"
ExecStart=/path/to/quant-vibe/venv/bin/python scripts/poll_spxw_quotes.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl enable spxw-collector
sudo systemctl start spxw-collector
sudo systemctl status spxw-collector
```

## Troubleshooting

### No contracts found

- Check that SPXW contracts exist for the date/strike range
- Verify Massive API is working: `python scripts/test_massive_client.py`
- Adjust `strike_range_pct` or `max_dte`

### Rate limit errors

- Polling: Increase `poll_interval` (e.g., 120 seconds)
- Reduce number of contracts by tightening strike range

### Missing quotes

- Some contracts may have low liquidity
- Check that market is open (9:30 AM - 4:00 PM ET)
- Verify Schwab API credentials

### Database errors

- Check TimescaleDB is running: `docker ps | grep timescale`
- Verify connection: `docker exec quant-vibe-timescaledb psql -U quantvibe -d options_data -c "SELECT NOW();"`

## Best Practices

1. **Start with polling** - Easier to test and debug
2. **Test during market hours** - No data outside 9:30 AM - 4:00 PM ET
3. **Monitor disk space** - Real-time collection generates large amounts of data
4. **Use compression** - TimescaleDB automatically compresses old data
5. **Filter by DTE** - Don't collect all expirations if not needed
6. **Limit strike range** - ±5-10% is usually sufficient

## Next Steps

- Set up automated rotation of expired contracts
- Add monitoring/alerting for data gaps
- Implement automatic restart on errors
- Add metrics dashboard (Grafana)
