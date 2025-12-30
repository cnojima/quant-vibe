# Dynamic DNS Setup (Sonic.net)

This guide explains how to configure and use Sonic.net's DynDNS service to maintain remote access to your Quant-Vibe instance.

## Overview

The DynDNS service automatically updates your Sonic.net DNS records when your public IP address changes. This ensures that your hostname (e.g., `myserver.sonic.net`) always points to your current IP address, enabling reliable remote access.

**Features:**
- Automatic IP change detection
- Configurable update intervals (default: 5 minutes)
- Retry logic with exponential backoff
- Comprehensive logging with rotation
- Docker-based deployment
- Force update on startup option

## Architecture

```
Internet → Your ISP (dynamic IP) → Home Network → Docker Host
                                                      ↓
                                              DynDNS Service
                                                      ↓
                                    Sonic.net API (update DNS records)
```

The DynDNS service runs as a Docker container and:
1. Checks your current public IP via Sonic.net API
2. Compares it with the last known IP
3. Updates DNS records if IP has changed
4. Logs all operations to `logs/dyndns/`

## Prerequisites

1. **Sonic.net Account**: You must have an active Sonic.net account
2. **DynDNS-enabled Hostname**: Your hostname must support DynDNS updates
3. **API Credentials**: You need to obtain API credentials (see below)

## Getting API Credentials

### Method 1: Using curl (Recommended)

1. Generate an API key using your Sonic.net credentials:

```bash
curl -X POST https://public-api.sonic.net/dyndns/api_key \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_sonic_username",
    "password": "your_sonic_password"
  }'
```

2. The response will contain your credentials:

```json
{
  "result": 200,
  "message": "API key created successfully",
  "userid": "your_userid",
  "apikey": "your_apikey_here"
}
```

3. Save the `userid` and `apikey` values for configuration.

### Method 2: Via Sonic.net Dashboard

1. Log in to your Sonic.net account
2. Navigate to the DynDNS API section
3. Request API credentials for your hostname
4. Copy the userid and apikey provided

### Listing Existing API Keys

To see your existing API keys:

```bash
curl -X POST https://public-api.sonic.net/dyndns/list_api_key \
  -H "Content-Type: application/json" \
  -d '{
    "username": "your_sonic_username",
    "password": "your_sonic_password"
  }'
```

## Configuration

### 1. Update Environment Variables

Edit your `.env` file and add the following:

```bash
# =============================================================================
# Dynamic DNS Settings (Sonic.net)
# =============================================================================

# Required: API credentials from Sonic.net
SONIC_DYNDNS_USERID=your_sonic_userid_here
SONIC_DYNDNS_APIKEY=your_sonic_apikey_here
SONIC_DYNDNS_HOSTNAME=your-hostname.sonic.net

# Optional: Advanced settings
SONIC_DYNDNS_RECORD_TYPE=A               # DNS record type (A, AAAA, TXT)
SONIC_DYNDNS_TTL=300                     # Time-to-live in seconds
SONIC_DYNDNS_UPDATE_INTERVAL=300         # Check interval in seconds (5 min)
SONIC_DYNDNS_FORCE_UPDATE=true           # Force update on service start
```

**Configuration Options:**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SONIC_DYNDNS_USERID` | ✅ | - | Your Sonic.net user ID |
| `SONIC_DYNDNS_APIKEY` | ✅ | - | Your Sonic.net API key |
| `SONIC_DYNDNS_HOSTNAME` | ✅ | - | Hostname to update (e.g., `server.sonic.net`) |
| `SONIC_DYNDNS_RECORD_TYPE` | ❌ | `A` | DNS record type (`A`, `AAAA`, `TXT`) |
| `SONIC_DYNDNS_TTL` | ❌ | `300` | DNS record TTL in seconds |
| `SONIC_DYNDNS_UPDATE_INTERVAL` | ❌ | `300` | How often to check for IP changes (seconds) |
| `SONIC_DYNDNS_FORCE_UPDATE` | ❌ | `true` | Force DNS update when service starts |

### 2. Start the Service

The DynDNS service is included in `docker-compose.yml` and will start automatically:

```bash
# Start all services (including DynDNS)
docker-compose up -d

# Or start only DynDNS service
docker-compose up -d dyndns
```

### 3. Verify Operation

Check the logs to verify the service is working:

```bash
# View real-time logs
docker-compose logs -f dyndns

# View recent logs
docker-compose logs --tail=50 dyndns
```

Expected output on startup:
```
[2025-12-30 12:00:00][dyndns][INFO    ] DynDNS Update Service Starting
[2025-12-30 12:00:00][dyndns][INFO    ] Hostname: myserver.sonic.net
[2025-12-30 12:00:00][dyndns][INFO    ] Record Type: A
[2025-12-30 12:00:00][dyndns][INFO    ] TTL: 300 seconds
[2025-12-30 12:00:00][dyndns][INFO    ] Update Interval: 300 seconds
[2025-12-30 12:00:01][dyndns][INFO    ] Testing API connectivity...
[2025-12-30 12:00:01][dyndns][INFO    ] API connection successful
[2025-12-30 12:00:01][dyndns][INFO    ] Performing initial DNS update...
[2025-12-30 12:00:02][dyndns][INFO    ] Successfully updated myserver.sonic.net (A) to 203.0.113.42
[2025-12-30 12:00:02][dyndns][INFO    ] Entering update loop...
```

## Usage

### Running as Docker Service (Recommended)

The service runs automatically with docker-compose:

```bash
# Start service
docker-compose up -d dyndns

# Stop service
docker-compose stop dyndns

# Restart service
docker-compose restart dyndns

# View logs
docker-compose logs -f dyndns
```

### Running Standalone (Development)

For testing or development, you can run the script directly:

```bash
# Activate virtual environment
source venv/bin/activate

# Run DynDNS service
python scripts/run_dyndns.py
```

Press `Ctrl+C` to stop the service.

## Monitoring

### Log Files

Logs are stored in `logs/dyndns/` with automatic rotation:
- Current log: `logs/dyndns/dyndns_YYYYMMDD.log`
- Rotated logs: `logs/dyndns/dyndns_YYYYMMDD.log.YYYY-MM-DD_EST`

### Periodic Status Updates

The service logs status updates every hour:
```
[2025-12-30 13:00:00][dyndns][INFO    ] Stats: 12 successful checks, current IP: 203.0.113.42
```

### Health Monitoring

The service integrates with the watcher service for automated health monitoring and notifications (if configured).

## Troubleshooting

### Issue: "Missing required DynDNS configuration"

**Solution:** Ensure all required environment variables are set in `.env`:
- `SONIC_DYNDNS_USERID`
- `SONIC_DYNDNS_APIKEY`
- `SONIC_DYNDNS_HOSTNAME`

### Issue: "Failed to connect to Sonic.net DynDNS API"

**Possible causes:**
1. Network connectivity issues
2. Sonic.net API is down
3. Firewall blocking outbound HTTPS

**Solution:**
1. Test API connectivity manually:
   ```bash
   curl https://public-api.sonic.net/dyndns/ping
   ```
2. Check Docker network settings
3. Verify firewall rules allow outbound HTTPS

### Issue: "HTTP 401 Unauthorized"

**Cause:** Invalid or expired API credentials

**Solution:**
1. Verify your credentials are correct in `.env`
2. Generate new API credentials if needed (see "Getting API Credentials")
3. Check that your hostname supports DynDNS updates

### Issue: "Update failed: hostname not found"

**Cause:** Hostname doesn't exist or isn't DynDNS-enabled

**Solution:**
1. Verify hostname spelling in `.env`
2. Confirm hostname is DynDNS-enabled in Sonic.net dashboard
3. Contact Sonic.net support if needed

### Issue: Service exits with "Too many consecutive errors"

**Cause:** Persistent API failures (network, auth, or service issues)

**Solution:**
1. Check recent logs for specific error messages
2. Verify network connectivity and API credentials
3. Restart the service after fixing the underlying issue:
   ```bash
   docker-compose restart dyndns
   ```

## Advanced Configuration

### Using IPv6 (AAAA Records)

To update IPv6 addresses instead of IPv4:

```bash
# In .env
SONIC_DYNDNS_RECORD_TYPE=AAAA
```

### Custom Update Interval

Adjust how often the service checks for IP changes:

```bash
# Check every 2 minutes (120 seconds)
SONIC_DYNDNS_UPDATE_INTERVAL=120

# Check every 10 minutes (600 seconds)
SONIC_DYNDNS_UPDATE_INTERVAL=600
```

**Note:** More frequent updates don't improve reliability but increase API load. The default 5 minutes is recommended.

### Disable Force Update on Startup

If you don't want to force a DNS update every time the service starts:

```bash
SONIC_DYNDNS_FORCE_UPDATE=false
```

The service will still update DNS if it detects an IP change.

### Manual DNS Update

To manually trigger a DNS update without restarting the service:

```bash
# Get current IP
curl https://public-api.sonic.net/dyndns/ip

# Update DNS record manually
curl -X PUT https://public-api.sonic.net/dyndns/host \
  -H "Content-Type: application/json" \
  -d '{
    "userid": "your_userid",
    "apikey": "your_apikey",
    "hostname": "your-hostname.sonic.net",
    "type": "A",
    "value": "203.0.113.42",
    "ttl": 300
  }'
```

## Security Considerations

### Protecting API Credentials

1. **Never commit `.env` to version control**
   - The `.env` file is gitignored by default
   - Use `.env.example` as a template

2. **Use environment-specific credentials**
   - Development: Use a test hostname if available
   - Production: Use secure, dedicated credentials

3. **Rotate credentials periodically**
   - Generate new API keys every 6-12 months
   - Delete old keys after rotation

### Network Security

The DynDNS service:
- Only makes outbound HTTPS connections to Sonic.net API
- Does not expose any ports
- Runs in isolated Docker network
- Uses TLS for all API communication

## Integration with Other Services

### Accessing Services Remotely

Once DynDNS is configured, you can access your services using your hostname:

```bash
# Access Admin UI
https://your-hostname.sonic.net:8000

# Access TimescaleDB (if port forwarded)
psql -h your-hostname.sonic.net -p 5432 -U quantvibe options_data
```

**Important:** Configure your router/firewall to forward necessary ports.

### Recommended Port Forwarding

| Service | Internal Port | External Port | Protocol |
|---------|---------------|---------------|----------|
| Admin UI | 8000 | 8000 | TCP |
| TimescaleDB | 5432 | 5432 | TCP |
| Redis | 6379 | 6379 | TCP |

**Security:** Only expose ports that are necessary. Use strong authentication and consider VPN for sensitive services.

## API Reference

The DynDNS service uses the following Sonic.net API endpoints:

### GET /dyndns/ping
Test API connectivity
```bash
curl https://public-api.sonic.net/dyndns/ping
```

### GET /dyndns/ip
Get current public IP address
```bash
curl https://public-api.sonic.net/dyndns/ip
```

### PUT /dyndns/host
Update DNS host record
```bash
curl -X PUT https://public-api.sonic.net/dyndns/host \
  -H "Content-Type: application/json" \
  -d '{
    "userid": "your_userid",
    "apikey": "your_apikey",
    "hostname": "your-hostname.sonic.net",
    "type": "A",
    "value": "203.0.113.42",
    "ttl": 300
  }'
```

Full API documentation: https://public-api.sonic.net/dyndns

## Support

- **Sonic.net API Issues**: Contact Sonic.net support
- **Service Issues**: Check logs in `logs/dyndns/`
- **Configuration Help**: See `.env.example` for all options
- **Feature Requests**: Submit an issue in the project repository

## See Also

- [Sonic.net DynDNS API Documentation](https://public-api.sonic.net/dyndns)
- [Docker Compose Documentation](../docker-compose.yml)
- [Environment Configuration](../.env.example)
- [Log Rotation Documentation](LOG_ROTATION.md)
