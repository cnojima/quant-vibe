# Schwab OAuth Callback Setup

This guide explains how the OAuth callback system works and how to configure it.

## Overview

The Schwab OAuth2 flow requires a callback URL to redirect users after authentication. This system provides **two ways** to handle OAuth callbacks:

1. **Automated Web Flow** (Recommended) - Browser-based redirect to nginx proxy
2. **Manual Script Flow** - Copy/paste callback URL into a script

## Architecture

```
User clicks "Authorize" on Schwab
         ↓
Schwab redirects to: https://127.0.0.1:53430/?code=...
         ↓
Nginx (port 53430, HTTPS)
         ↓
Extracts code parameter
         ↓
Proxies to: http://admin_ui:8000/api/tokens/oauth-redirect?code=...
         ↓
Backend exchanges code for tokens
         ↓
Saves to tokens/schwabdev_tokens.db
         ↓
Shows success page to user
```

## Setup Instructions

### 1. Generate SSL Certificate

The OAuth callback requires HTTPS. Generate a self-signed certificate:

```bash
./scripts/generate_oauth_cert.sh
```

This creates:
- `src/admin_ui/frontend/ssl/nginx-selfsigned.crt`
- `src/admin_ui/frontend/ssl/nginx-selfsigned.key`

### 2. Configure Schwab App

In the [Schwab Developer Portal](https://developer.schwab.com/):

1. Go to your app settings
2. Set the **Callback URL** to: `https://127.0.0.1:53430/`
3. Save changes

**Important**: Use the exact URL with port `53430` and trailing slash.

### 3. Update Environment Variables

In your `.env` file:

```bash
SCHWAB_CALLBACK_URL=https://127.0.0.1:53430/
SCHWAB_API_KEY=your_app_key
SCHWAB_API_SECRET=your_app_secret
```

### 4. Build and Start Services

```bash
# Rebuild nginx with SSL certificates
docker compose build admin_ui_frontend

# Start services
docker compose up -d
```

## Usage

### Option 1: Web Flow (Recommended)

1. Open the Admin UI: `http://localhost/tokens`
2. Click "Get OAuth URL" button
3. Click the generated OAuth URL
4. Log in to Schwab and approve
5. Browser redirects to `https://127.0.0.1:53430/?code=...`
6. Nginx automatically handles the callback
7. You'll see a success page
8. Tokens are saved automatically

**Browser Security Warning**: You'll see a warning about the self-signed certificate. Click "Advanced" → "Proceed" to continue. This is safe for local development.

### Option 2: Manual Script (Legacy)

If the web flow doesn't work:

```bash
# Interactive mode
python scripts/schwab_oauth_callback.py

# Or with URL as argument
python scripts/schwab_oauth_callback.py "https://127.0.0.1:53430/?code=C0..."
```

## Components

### Nginx Configuration

**File**: `src/admin_ui/frontend/nginx.conf`

```nginx
# OAuth callback listener (HTTPS on port 53430)
server {
    listen 53430 ssl;
    server_name localhost;

    ssl_certificate /etc/nginx/ssl/nginx-selfsigned.crt;
    ssl_certificate_key /etc/nginx/ssl/nginx-selfsigned.key;

    location / {
        # Extract OAuth code and proxy to backend
        if ($arg_code) {
            return 307 http://admin_ui:8000/api/tokens/oauth-redirect?code=$arg_code;
        }
        return 400 "Missing OAuth code parameter";
    }
}
```

### Backend API Endpoint

**File**: `src/admin_ui/backend/api/tokens.py`

**Endpoint**: `GET /api/tokens/oauth-redirect?code=...`

- Extracts authorization code from query parameter
- Exchanges code for access/refresh tokens
- Saves tokens to `tokens/schwabdev_tokens.db`
- Returns HTML success/error page
- **No authentication required** (public endpoint)

### Standalone Script

**File**: `scripts/schwab_oauth_callback.py`

- Accepts full callback URL or just the code
- Exchanges code for tokens
- Saves to database
- Can be run from command line

## Troubleshooting

### "Connection Refused" or "Can't Connect"

**Cause**: Nginx container not running or port not exposed

**Solution**:
```bash
docker compose ps  # Check if admin_ui_frontend is running
docker compose logs admin_ui_frontend  # Check for errors
docker compose up -d admin_ui_frontend  # Restart nginx
```

### "Invalid SSL Certificate" (Browser Blocks)

**Cause**: Browser doesn't trust self-signed certificate

**Solution**: Click "Advanced" → "Proceed to 127.0.0.1" in browser. This is safe for local development.

### "Authorization Code Expired"

**Cause**: OAuth codes expire in ~30 seconds

**Solution**: Start the OAuth flow again and complete it quickly.

### "Token Exchange Failed"

**Cause**: Callback URL mismatch or invalid credentials

**Solution**:
1. Verify callback URL in Schwab app matches exactly: `https://127.0.0.1:53430/`
2. Check `SCHWAB_API_KEY` and `SCHWAB_API_SECRET` in `.env`
3. Ensure app status is "Ready For Use" in Schwab portal

### Port Already in Use

**Cause**: Another service using port 53430

**Solution**:
```bash
# Check what's using the port
lsof -i :53430

# Change the port in:
# - src/admin_ui/frontend/nginx.conf (listen 53430 ssl;)
# - docker-compose.yml (ports: "53430:53430")
# - Schwab app callback URL
```

## Security Considerations

### Self-Signed Certificate

The self-signed certificate is **safe for local development** but:
- ⚠️ DO NOT use in production
- ⚠️ DO NOT expose port 53430 to the internet
- ✅ Only accessible from localhost (127.0.0.1)

### Production Deployment

For production:
1. Use a real SSL certificate from Let's Encrypt or CA
2. Use a proper domain name (not 127.0.0.1)
3. Update Schwab app callback URL to production domain
4. Ensure nginx is behind a firewall

## Port Configuration

The system uses **three ports**:

| Port  | Service          | Protocol | Purpose                    |
|-------|------------------|----------|----------------------------|
| 80    | Frontend         | HTTP     | Admin UI web interface     |
| 8000  | Backend API      | HTTP     | API endpoints              |
| 53430 | OAuth Callback   | HTTPS    | Schwab OAuth redirects     |

Port 53430 was chosen to:
- Avoid conflicts with common services
- Be high enough to not require root
- Be memorable (53 = "Schwab", 430 = "OAuth")

## Files Overview

```
quant-vibe/
├── scripts/
│   ├── generate_oauth_cert.sh           # Generate SSL certificate
│   └── schwab_oauth_callback.py         # Standalone callback handler
│
├── src/admin_ui/
│   ├── frontend/
│   │   ├── nginx.conf                   # Nginx config (OAuth proxy)
│   │   ├── Dockerfile                   # Nginx + SSL setup
│   │   └── ssl/                         # SSL certificates
│   │       ├── nginx-selfsigned.crt
│   │       └── nginx-selfsigned.key
│   │
│   └── backend/api/
│       ├── tokens.py                    # OAuth endpoints
│       └── tokens_helper.py             # Token exchange logic
│
├── docker-compose.yml                   # Port 53430 exposure
└── docs/
    └── OAUTH_CALLBACK_SETUP.md          # This file
```

## Advanced Configuration

### Custom Port

To use a different port:

1. Edit `src/admin_ui/frontend/nginx.conf`:
   ```nginx
   listen YOUR_PORT ssl;
   ```

2. Edit `docker-compose.yml`:
   ```yaml
   ports:
     - "YOUR_PORT:YOUR_PORT"
   ```

3. Update `.env`:
   ```bash
   SCHWAB_CALLBACK_URL=https://127.0.0.1:YOUR_PORT/
   ```

4. Update Schwab app callback URL

5. Rebuild and restart:
   ```bash
   docker compose build admin_ui_frontend
   docker compose up -d admin_ui_frontend
   ```

### Multiple Environments

You can have different callback URLs for different environments:

**Development** (`.env.development`):
```bash
SCHWAB_CALLBACK_URL=https://127.0.0.1:53430/
```

**Production** (`.env.production`):
```bash
SCHWAB_CALLBACK_URL=https://yourdomain.com/oauth-callback
```

## Testing

Test the OAuth flow:

1. **Check nginx is listening**:
   ```bash
   curl -k https://127.0.0.1:53430/
   # Should see "Missing OAuth code parameter"
   ```

2. **Test with fake code**:
   ```bash
   curl -k "https://127.0.0.1:53430/?code=test123"
   # Should see "Authorization Failed" HTML page
   ```

3. **Check backend endpoint**:
   ```bash
   curl "http://localhost:8000/api/tokens/oauth-redirect?code=test123"
   # Should see error about invalid code
   ```

4. **Full OAuth flow**:
   - Get OAuth URL from Admin UI
   - Complete Schwab login
   - Verify redirect works
   - Check tokens saved: `ls -la tokens/schwabdev_tokens.db`

## See Also

- [Schwab Developer Portal](https://developer.schwab.com/)
- [OAuth 2.0 RFC](https://tools.ietf.org/html/rfc6749)
- [schwabdev Library](https://github.com/tylerebowers/Schwabdev)
