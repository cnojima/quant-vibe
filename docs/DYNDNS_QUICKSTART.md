# DynDNS Quick Start Guide

Quick reference for setting up Sonic.net DynDNS on Quant-Vibe.

## 30-Second Setup

```bash
# 1. Get API credentials
python scripts/get_sonic_dyndns_apikey.py

# 2. Add to .env file
cat >> .env << EOF
SONIC_DYNDNS_USERID=your_userid_here
SONIC_DYNDNS_APIKEY=your_apikey_here
SONIC_DYNDNS_HOSTNAME=your-hostname.sonic.net
EOF

# 3. Start the service
docker-compose up -d dyndns

# 4. Verify it's working
docker-compose logs -f dyndns
```

## What You Need

1. **Sonic.net account** with DynDNS-enabled hostname
2. **API credentials** (userid + apikey)
3. **Hostname** to update (e.g., `server.sonic.net`)

## Getting API Credentials

### Option 1: Helper Script (Easiest)
```bash
python scripts/get_sonic_dyndns_apikey.py
```

### Option 2: Manual curl
```bash
curl -X POST https://public-api.sonic.net/dyndns/api_key \
  -H "Content-Type: application/json" \
  -d '{"username":"YOUR_USERNAME","password":"YOUR_PASSWORD"}'
```

## Configuration (.env)

**Required:**
```bash
SONIC_DYNDNS_USERID=your_userid
SONIC_DYNDNS_APIKEY=your_apikey
SONIC_DYNDNS_HOSTNAME=your-hostname.sonic.net
```

**Optional (with defaults):**
```bash
SONIC_DYNDNS_RECORD_TYPE=A           # A, AAAA, or TXT
SONIC_DYNDNS_TTL=300                 # seconds
SONIC_DYNDNS_UPDATE_INTERVAL=300     # check every 5 min
SONIC_DYNDNS_FORCE_UPDATE=true       # force on startup
```

## Common Commands

```bash
# Start service
docker-compose up -d dyndns

# View logs
docker-compose logs -f dyndns

# Restart service
docker-compose restart dyndns

# Stop service
docker-compose stop dyndns

# Check current IP
curl https://public-api.sonic.net/dyndns/ip
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Missing configuration" | Add required vars to `.env` |
| "Failed to connect" | Check network/firewall |
| "401 Unauthorized" | Verify credentials in `.env` |
| "Too many errors" | Check logs, restart service |

## Expected Log Output

```
[2025-12-30 12:00:00][dyndns][INFO    ] DynDNS Update Service Starting
[2025-12-30 12:00:01][dyndns][INFO    ] API connection successful
[2025-12-30 12:00:02][dyndns][INFO    ] Successfully updated server.sonic.net (A) to 203.0.113.42
[2025-12-30 12:00:02][dyndns][INFO    ] Entering update loop...
```

## How It Works

1. Service checks current public IP every 5 minutes (configurable)
2. Compares with last known IP
3. Updates DNS via Sonic.net API if changed
4. Logs all operations to `logs/dyndns/`

## Port Forwarding

After DynDNS is working, configure your router to forward ports:

| Service | Port | Protocol |
|---------|------|----------|
| Admin UI | 8000 | TCP |
| TimescaleDB | 5432 | TCP |
| Redis | 6379 | TCP |

Then access remotely via: `https://your-hostname.sonic.net:8000`

## Full Documentation

See [DYNDNS_SETUP.md](DYNDNS_SETUP.md) for complete documentation.

## Security Tips

- ✅ Never commit `.env` to version control
- ✅ Use strong passwords for exposed services
- ✅ Consider VPN for database access
- ✅ Rotate API credentials periodically
- ❌ Don't expose all ports publicly
