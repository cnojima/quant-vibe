# OAuth Callback Quick Start

**TL;DR**: Get Schwab OAuth working in 3 commands.

## Quick Setup

```bash
# 1. Generate SSL certificate
./scripts/generate_oauth_cert.sh

# 2. Update .env with callback URL
echo "SCHWAB_CALLBACK_URL=https://127.0.0.1:53430/" >> .env

# 3. Rebuild and restart nginx
docker compose build admin_ui_frontend
docker compose up -d admin_ui_frontend
```

## Update Schwab App Settings

1. Go to [Schwab Developer Portal](https://developer.schwab.com/)
2. Edit your app
3. Set **Callback URL**: `https://127.0.0.1:53430/`
4. Save

## Test It

1. Open: `http://localhost/tokens` (or your Admin UI)
2. Click "Get OAuth URL"
3. Click the generated URL
4. Log in to Schwab
5. Approve the app
6. You'll be redirected to `https://127.0.0.1:53430/?code=...`
7. Click "Advanced" → "Proceed" (self-signed cert warning)
8. See success page
9. Tokens saved! ✓

## How It Works

```
User authorizes → Schwab redirects to https://127.0.0.1:53430/
                  ↓
              Nginx (HTTPS)
                  ↓
          Extracts OAuth code
                  ↓
    Proxies to Backend API (/api/tokens/oauth-redirect)
                  ↓
      Exchanges code for tokens
                  ↓
    Saves to tokens/schwabdev_tokens.db
                  ↓
         Shows success page
```

## Alternative: Manual Script

If the web flow doesn't work:

```bash
# Get the OAuth URL
curl -s http://localhost:8000/api/tokens/oauth-url | jq -r '.oauth_url'

# Open in browser, authorize, copy the callback URL

# Run script with the URL
python scripts/schwab_oauth_callback.py "https://127.0.0.1:53430/?code=C0..."
```

## Troubleshooting

**Can't connect to 53430**: Check nginx is running:
```bash
docker compose ps admin_ui_frontend
docker compose logs admin_ui_frontend
```

**SSL certificate warning**: Click "Advanced" → "Proceed" (this is safe for localhost)

**Code expired**: OAuth codes expire in 30 seconds. Try again quickly.

**Token exchange failed**: Verify:
- Callback URL matches exactly in Schwab app: `https://127.0.0.1:53430/`
- `SCHWAB_API_KEY` and `SCHWAB_API_SECRET` are correct in `.env`
- App status is "Ready For Use" in Schwab portal

## Files

- `scripts/generate_oauth_cert.sh` - Generate SSL cert
- `scripts/schwab_oauth_callback.py` - Manual callback handler
- `src/admin_ui/frontend/nginx.conf` - Nginx OAuth proxy config
- `src/admin_ui/backend/api/tokens.py` - OAuth redirect endpoint
- `docs/OAUTH_CALLBACK_SETUP.md` - Full documentation

## See Full Docs

For detailed info: `docs/OAUTH_CALLBACK_SETUP.md`
