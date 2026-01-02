# Token Management Service

Centralized OAuth token management for Schwab API.

## Quick Start

### Docker (Recommended)
```bash
# Start token service
docker-compose up -d token_service

# Check health
curl http://localhost:8100/health

# View logs
docker-compose logs -f token_service
```

### Standalone
```bash
# Activate venv
source venv/bin/activate

# Install dependencies
pip install -e ".[dev,schwab]"

# Run service
python scripts/run_token_service.py
```

## API Examples

### Get Token Status
```bash
curl http://localhost:8100/token/status
```

### Get Access Token
```bash
curl http://localhost:8100/token/access
```

### Refresh Token
```bash
curl -X POST http://localhost:8100/token/refresh
```

## Python Client

```python
from token_service.client import TokenServiceClient

client = TokenServiceClient("http://localhost:8100")

# Get access token
token = client.get_access_token()

# Check if valid
is_valid = client.is_token_valid()

# Refresh
client.refresh_token()
```

## Configuration

Set environment variables in `.env`:

```bash
# Required
SCHWAB_API_KEY=your_api_key
SCHWAB_API_SECRET=your_app_secret

# Optional
TOKEN_SERVICE_PORT=8100
TOKEN_REFRESH_INTERVAL_MINUTES=14
```

## Documentation

See [docs/TOKEN_SERVICE.md](../../docs/TOKEN_SERVICE.md) for complete documentation.

## Features

✅ Automatic token refresh every 14 minutes
✅ Thread-safe concurrent access
✅ Redis event publishing
✅ Docker health checks
✅ Normalized logging
✅ REST API
