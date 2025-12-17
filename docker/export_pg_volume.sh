#!/usr/bin/env bash
# Export PostgreSQL Docker Volume Data
# This script exports data from a PostgreSQL Docker volume to a local directory.

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Configuration
VOLUME_NAME="quant-vibe_timescaledb_data"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPORT_DIR="${SCRIPT_DIR}/pg_export"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="pg_data_backup_${TIMESTAMP}.tar.gz"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}" >&2
    exit 1
fi

# Check if volume exists
if ! docker volume inspect "$VOLUME_NAME" > /dev/null 2>&1; then
    echo -e "${RED}Error: Volume '$VOLUME_NAME' does not exist${NC}" >&2
    exit 1
fi

# Create export directory
mkdir -p "$EXPORT_DIR"

echo -e "${YELLOW}Exporting PostgreSQL data from volume: $VOLUME_NAME${NC}"
echo "Backup file: $BACKUP_FILE"

# Export data (read-only mount of source volume)
if docker run --rm \
    -v "${VOLUME_NAME}:/var/lib/postgresql/data:ro" \
    -v "${EXPORT_DIR}:/backup" \
    busybox tar czf "/backup/${BACKUP_FILE}" -C /var/lib/postgresql/data .; then

    # Verify backup was created
    if [ -f "${EXPORT_DIR}/${BACKUP_FILE}" ]; then
        BACKUP_SIZE=$(du -h "${EXPORT_DIR}/${BACKUP_FILE}" | cut -f1)
        echo -e "${GREEN}✓ PostgreSQL data exported successfully${NC}"
        echo "  Location: ${EXPORT_DIR}/${BACKUP_FILE}"
        echo "  Size: ${BACKUP_SIZE}"

        # Optional: Keep only last 5 backups
        echo "Cleaning up old backups (keeping last 5)..."
        cd "$EXPORT_DIR"
        ls -t pg_data_backup_*.tar.gz 2>/dev/null | tail -n +6 | xargs -r rm
    else
        echo -e "${RED}Error: Backup file was not created${NC}" >&2
        exit 1
    fi
else
    echo -e "${RED}Error: Docker export command failed${NC}" >&2
    exit 1
fi
echo -e "${GREEN}Export completed.${NC}"