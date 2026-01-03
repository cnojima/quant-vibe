# Admin UI - nginx Production Deployment

## Summary

The Admin UI frontend is now configured for production deployment using nginx in a Docker container. This provides a production-ready, optimized setup with proper caching, compression, and routing.

## Architecture

```
Client Browser
      ↓
nginx (Port 80) ────────────────┐
      ↓                          │
Static Assets (React build)      │ Proxy
      ↓                          │
/api, /ws, /health ──────────────┘
      ↓
FastAPI Backend (Port 8000)
```

## Components

### 1. **nginx Configuration** (`src/admin_ui/frontend/nginx.conf`)

Features:
- Serves production React build from `/usr/share/nginx/html`
- Proxies API requests to backend (`/api` → `admin_ui:8000`)
- Proxies WebSocket connections (`/ws` → `admin_ui:8000`)
- SPA routing (fallback to `index.html`)
- Gzip compression for text assets
- Cache headers (1 year for static assets, no-cache for HTML)
- Security headers (X-Frame-Options, X-Content-Type-Options, etc.)

### 2. **Multi-Stage Dockerfile** (`src/admin_ui/frontend/Dockerfile`)

**Stage 1: Builder**
- Base: `node:18-alpine`
- Installs dependencies with `npm ci`
- Builds production bundle with `npm run build`
- Output: `dist/` directory

**Stage 2: Production**
- Base: `nginx:1.25-alpine`
- Copies nginx configuration
- Copies built assets from builder stage
- Exposes port 80
- Includes healthcheck

### 3. **Docker Compose Service** (`docker-compose.yml`)

Added `admin_ui_frontend` service:
- Builds from `src/admin_ui/frontend/Dockerfile`
- Exposes port 80 (HTTP)
- Depends on `admin_ui` backend
- Includes healthcheck via `/health` endpoint
- Auto-restart policy

### 4. **Docker Ignore** (`src/admin_ui/frontend/.dockerignore`)

Optimizes build by excluding:
- `node_modules` (reinstalled during build)
- `dist` (generated during build)
- Development files (.vite, .cache)
- IDE files (.vscode, .idea)
- Environment files (.env)

## Usage

### Production Deployment

```bash
# Start all services (includes nginx frontend)
docker-compose up -d

# Or start just frontend
docker-compose up -d admin_ui_frontend

# Rebuild after code changes
docker-compose up -d --build admin_ui_frontend

# View logs
docker-compose logs -f admin_ui_frontend

# Access
# → http://localhost
```

### Development

```bash
# Use Vite dev server (not nginx)
cd src/admin_ui/frontend
npm run dev

# Access
# → http://localhost:5173
```

## URLs

### Production (nginx)
- **Frontend**: http://localhost
- **API**: http://localhost/api (proxied)
- **Docs**: http://localhost/docs (proxied)
- **Health**: http://localhost/health (proxied)
- **WebSocket**: ws://localhost/ws (proxied)

### Development (Vite)
- **Frontend**: http://localhost:5173
- **API**: Proxied by Vite to http://localhost:8000

## Benefits

### Performance
✅ **Optimized build**: Minified JS/CSS, tree-shaking
✅ **Gzip compression**: 60-80% size reduction
✅ **Asset caching**: 1-year cache for static files
✅ **HTTP/2**: Multiplexing and header compression

### Security
✅ **Security headers**: X-Frame-Options, CSP-ready
✅ **No CORS issues**: Same-origin requests
✅ **Isolated services**: Frontend and backend in separate containers

### Scalability
✅ **Stateless frontend**: Easy horizontal scaling
✅ **Independent deployment**: Update frontend without backend restart
✅ **CDN-ready**: Can serve `dist/` from CDN

### Developer Experience
✅ **Single port**: Everything on port 80
✅ **Automatic routing**: nginx handles SPA fallback
✅ **Easy updates**: `docker-compose up -d --build`

## File Structure

```
src/admin_ui/frontend/
├── Dockerfile              # Multi-stage build
├── nginx.conf              # nginx configuration
├── .dockerignore           # Build optimization
├── DEPLOYMENT.md           # Deployment guide
├── package.json
├── vite.config.ts
├── tsconfig.json
├── src/
│   ├── components/
│   ├── pages/
│   ├── api/
│   └── App.tsx
└── dist/                   # Production build (generated)
    ├── index.html
    ├── assets/
    │   ├── index-[hash].js
    │   └── index-[hash].css
    └── favicon.ico
```

## Troubleshooting

### Port 80 in use
```bash
# Find process
sudo lsof -i :80

# Change port in docker-compose.yml
ports:
  - "8080:80"  # Map to 8080 instead
```

### nginx won't start
```bash
# Test configuration
docker exec quant-vibe-admin-ui-frontend nginx -t

# View error log
docker logs quant-vibe-admin-ui-frontend
```

### API requests fail
```bash
# Ensure backend is healthy
docker-compose ps admin_ui

# Test proxy from container
docker exec quant-vibe-admin-ui-frontend \
  wget -O- http://admin_ui:8000/health
```

### SPA routes return 404
- Check `try_files` in nginx.conf
- Ensure `location /` has fallback to `/index.html`
- Verify React Router uses BrowserRouter (not HashRouter)

## Next Steps

### Optional Enhancements

1. **HTTPS/SSL**
   - Add SSL certificate
   - Configure nginx SSL termination
   - Redirect HTTP → HTTPS

2. **CDN Integration**
   - Upload `dist/` to CDN
   - Update API URL in environment
   - Configure CORS for CDN origin

3. **Monitoring**
   - Add nginx metrics exporter
   - Monitor response times
   - Track error rates

4. **Advanced Caching**
   - Add Redis cache layer
   - Implement service worker
   - Add offline support

## References

- **nginx Documentation**: https://nginx.org/en/docs/
- **Vite Production Build**: https://vitejs.dev/guide/build.html
- **Docker Multi-Stage**: https://docs.docker.com/build/building/multi-stage/
- **React Deployment**: https://react.dev/learn/start-a-new-react-project#deploying-to-production

## Changelog

- **2025-12-30**: Initial nginx deployment setup
  - Created Dockerfile with multi-stage build
  - Added nginx.conf with proxy rules
  - Updated docker-compose.yml
  - Added documentation
