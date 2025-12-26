FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements-related files first for better layer caching
COPY pyproject.toml README.md ./

# Copy src directory temporarily for dependency installation
COPY src ./src

# Install Python dependencies in editable mode
# This layer will be cached unless pyproject.toml or src changes
RUN pip install --no-cache-dir -e ".[all,schwab]"

# The actual source code will be mounted as a volume at runtime
# This allows live code updates during development

# Create tokens directory for schwabdev
RUN mkdir -p /app/tokens

# Health check - verify Python can import the package
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import sys; sys.path.insert(0, '/app/src'); from quant_vibe.data.timescale_store import TimescaleStore" || exit 1

# Default command (can be overridden in docker-compose)
CMD ["python", "scripts/stream_spxw_schwabdev.py"]
