# Docker SQLAlchemy Missing Fix

## Problem
The streaming container was failing with:
```
ModuleNotFoundError: No module named 'sqlalchemy'
```

## Root Cause
The Dockerfile was attempting to install a non-existent optional dependency group:
```dockerfile
RUN pip install --no-cache-dir -e ".[dev,backtest,indicators,schwab]"
                                                    ^^^^^^^^^^
                                                    This doesn't exist!
```

The `indicators` group is not defined in `pyproject.toml`, causing the pip install to fail silently or incompletely.

## Fix Applied
Changed Dockerfile line 21 from:
```dockerfile
RUN pip install --no-cache-dir -e ".[dev,backtest,indicators,schwab]"
```

To:
```dockerfile
RUN pip install --no-cache-dir -e ".[schwab]"
```

This installs:
- Base dependencies (including `sqlalchemy`, `psycopg2-binary`, etc.)
- Schwab-specific dependencies (`schwabdev`, `schwab-py`)

## Deploying the Fix to Remote Instance

### Option 1: Rebuild Docker Container (Recommended)

```bash
# On your remote instance
cd /path/to/quant-vibe

# Pull latest code (if using git)
git pull

# Stop the running container
docker-compose down

# Rebuild the image (this will use the fixed Dockerfile)
docker-compose build --no-cache streaming

# Start services
docker-compose up -d

# Verify it's working
docker-compose logs -f streaming
```

### Option 2: Manual Fix (Quick Workaround)

If you can't rebuild right now, manually install sqlalchemy in the running container:

```bash
# Enter the running container
docker exec -it quant-vibe-streaming bash

# Install sqlalchemy
pip install sqlalchemy>=2.0.0

# Exit container
exit

# Restart the container
docker-compose restart streaming
```

**Note**: This is temporary - the fix will be lost if the container is recreated.

## Verification

After applying the fix, verify sqlalchemy is installed:

```bash
docker exec quant-vibe-streaming python -c "import sqlalchemy; print(f'✅ SQLAlchemy {sqlalchemy.__version__} installed')"
```

Expected output:
```
✅ SQLAlchemy 2.x.x installed
```

## Prevention

The Dockerfile now only references optional dependency groups that actually exist in `pyproject.toml`:
- ✅ `schwab` - Schwab API libraries
- ✅ `dev` - Development tools (pytest, black, ruff, mypy)
- ✅ `backtest` - Backtesting tools (backtrader, matplotlib)
- ✅ `all` - All optional dependencies
- ❌ `indicators` - Does not exist, removed from Dockerfile

## Date
Fixed: December 17, 2025
