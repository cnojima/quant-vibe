# Admin UI Frontend - Production Deployment

This document describes the production deployment of the Admin UI frontend using nginx.

## Architecture

The production setup uses a multi-stage Docker build:

1. **Build Stage**: Compiles React/TypeScript with Vite
2. **Production Stage**: Serves static files with nginx

```
┌──────────────────┐
│  Dockerfile      │
│  ├─ Stage 1:     │  node:18-alpine
│  │  Build React  │  → npm run build → dist/
│  └─ Stage 2:     │  nginx:1.25-alpine
│     Serve dist/  │  → Production server
└──────────────────┘
```

## Files

### `Dockerfile`
Multi-stage build file:
- **Stage 1** (`builder`): Builds the React application
- **Stage 2** (`production`): Serves with nginx

### `nginx.conf`
nginx configuration:
- Serves static files from `/usr/share/nginx/html`
- Proxies `/api` requests to backend (`admin_ui:8000`)
- Proxies `/ws` WebSocket connections to backend
- SPA fallback routing (serves `index.html` for all routes)
- Gzip compression for assets
- Cache headers for static files
- Security headers

### `.dockerignore`
Excludes unnecessary files from Docker build context

## Building

### Local Build

```bash
cd src/admin_ui/frontend

# Install dependencies
npm install

# Create production build
npm run build

# Output: dist/ directory
```

### Docker Build

```bash
# From project root
docker-compose build admin_ui_frontend

# Or force rebuild
docker-compose up -d --build admin_ui_frontend
```

## Running

### Start Production Container

```bash
# Start frontend (requires backend running)
docker-compose up -d admin_ui_frontend

# View logs
docker-compose logs -f admin_ui_frontend

# Check status
docker-compose ps admin_ui_frontend
```

### Access

- **Frontend**: http://localhost
- **API** (proxied): http://localhost/api
- **Docs** (proxied): http://localhost/docs
- **Health** (proxied): http://localhost/health

## nginx Configuration

### Proxy Rules

| Route | Backend | Purpose |
|-------|---------|---------|
| `/api` | `http://admin_ui:8000` | REST API endpoints |
| `/ws` | `http://admin_ui:8000` | WebSocket events |
| `/health` | `http://admin_ui:8000` | Health check |
| `/docs` | `http://admin_ui:8000` | API documentation |
| `/redoc` | `http://admin_ui:8000` | Alternative docs |
| `/openapi.json` | `http://admin_ui:8000` | OpenAPI schema |

### Static Assets

| File Type | Cache Policy |
|-----------|--------------|
| `.js`, `.css` | 1 year, immutable |
| `.jpg`, `.png`, `.svg` | 1 year, immutable |
| `.woff`, `.woff2`, `.ttf` | 1 year, immutable |
| `index.html` | No cache |

### Compression

Gzip compression enabled for:
- text/plain
- text/css
- text/javascript
- application/javascript
- application/json
- image/svg+xml

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs admin_ui_frontend

# Common issues:
# 1. Port 80 already in use
sudo lsof -i :80
# Kill process or change port in docker-compose.yml

# 2. Backend not healthy
docker-compose ps admin_ui
```

### nginx errors

```bash
# Test nginx configuration
docker exec quant-vibe-admin-ui-frontend nginx -t

# Reload nginx (without restart)
docker exec quant-vibe-admin-ui-frontend nginx -s reload

# View nginx error log
docker exec quant-vibe-admin-ui-frontend cat /var/log/nginx/error.log
```

### SPA routing not working

If direct URLs (e.g., `/dashboard`) return 404:
- Check `try_files` directive in nginx.conf
- Ensure `index.html` fallback is configured
- Verify React Router is using BrowserRouter

### API requests fail

```bash
# Check backend is running
docker-compose ps admin_ui

# Test proxy from inside container
docker exec quant-vibe-admin-ui-frontend wget -O- http://admin_ui:8000/health

# Check CORS settings in backend
# Environment: CORS_ORIGINS should include http://localhost
```

## Production Deployment (Non-Docker)

### Build Assets

```bash
npm run build
# Output: dist/
```

### Serve with nginx

```nginx
server {
    listen 80;
    root /path/to/dist;
    index index.html;

    # Copy proxy rules from nginx.conf
    # Update backend URL to your API server
}
```

### Serve with Apache

```apache
<VirtualHost *:80>
    DocumentRoot /path/to/dist

    <Directory /path/to/dist>
        Options Indexes FollowSymLinks
        AllowOverride All
        Require all granted

        # SPA fallback
        RewriteEngine On
        RewriteBase /
        RewriteRule ^index\.html$ - [L]
        RewriteCond %{REQUEST_FILENAME} !-f
        RewriteCond %{REQUEST_FILENAME} !-d
        RewriteRule . /index.html [L]
    </Directory>

    # Proxy API requests
    ProxyPass /api http://backend:8000/api
    ProxyPassReverse /api http://backend:8000/api
</VirtualHost>
```

## Environment Variables

The frontend uses build-time environment variables:

```bash
# .env.production (optional)
VITE_API_URL=http://your-api-server.com
```

If not set, defaults to relative URLs (proxied through nginx).

## Security

### Headers

nginx adds security headers:
- `X-Frame-Options: SAMEORIGIN`
- `X-Content-Type-Options: nosniff`
- `X-XSS-Protection: 1; mode=block`

### HTTPS

For production, use a reverse proxy with SSL:

```nginx
# SSL termination proxy
server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:80;  # nginx container
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
```

## Monitoring

### Health Check

```bash
# Container health
docker inspect quant-vibe-admin-ui-frontend --format='{{.State.Health.Status}}'

# nginx health
curl http://localhost/health
```

### Metrics

nginx exposes basic metrics:
- Access logs: `/var/log/nginx/access.log`
- Error logs: `/var/log/nginx/error.log`

## Performance

### Build Optimization

The production build:
- Minifies JavaScript and CSS
- Tree-shakes unused code
- Code-splits by route
- Optimizes images
- Generates source maps (optional)

### Runtime Performance

nginx optimizations:
- Gzip compression (reduce transfer size)
- Static asset caching (reduce server load)
- HTTP/2 support (multiplexing)
- Keep-alive connections

### Monitoring Bundle Size

```bash
# Analyze bundle
npm run build -- --report

# Check gzipped sizes
du -h dist/**/*.js | sort -h
```

## Backup and Restore

The frontend is stateless - no data to backup.

To restore:
1. Rebuild Docker image
2. Restart container

```bash
docker-compose up -d --build admin_ui_frontend
```
