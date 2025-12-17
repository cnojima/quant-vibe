#!/usr/bin/env bash
# Import PostgreSQL Docker Volume Data
# This script imports data from a backup archive to a PostgreSQL Docker volume.

set -euo pipefail  # Exit on error, undefined vars, pipe failures

# Configuration
VOLUME_NAME="quant-vibe_timescaledb_data"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXPORT_DIR="${SCRIPT_DIR}/pg_export"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to display usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Import PostgreSQL data from backup to Docker volume"
    echo ""
    echo "Options:"
    echo "  -f, --file BACKUP_FILE    Specify backup file to restore"
    echo "  -l, --list                List available backups"
    echo "  -v, --volume VOLUME_NAME  Target volume name (default: quant-vibe_timescaledb_data)"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 --list                                    # List available backups"
    echo "  $0                                           # Restore latest backup"
    echo "  $0 --file pg_data_backup_20251216_143045.tar.gz"
    exit 1
}

# Function to list available backups
list_backups() {
    echo -e "${BLUE}Available backups in ${EXPORT_DIR}:${NC}"
    echo ""

    if [ ! -d "$EXPORT_DIR" ]; then
        echo -e "${RED}Error: Export directory does not exist: $EXPORT_DIR${NC}" >&2
        exit 1
    fi

    local backups=($(ls -t "${EXPORT_DIR}"/pg_data_backup_*.tar.gz 2>/dev/null || true))

    if [ ${#backups[@]} -eq 0 ]; then
        echo -e "${YELLOW}No backup files found${NC}"
        exit 0
    fi

    for i in "${!backups[@]}"; do
        local backup="${backups[$i]}"
        local basename=$(basename "$backup")
        local size=$(du -h "$backup" | cut -f1)
        local date=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" "$backup" 2>/dev/null || stat -c "%y" "$backup" 2>/dev/null | cut -d'.' -f1)

        if [ $i -eq 0 ]; then
            echo -e "  ${GREEN}[LATEST]${NC} $basename (${size}, created: $date)"
        else
            echo -e "           $basename (${size}, created: $date)"
        fi
    done

    exit 0
}

# Parse arguments
BACKUP_FILE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--file)
            BACKUP_FILE="$2"
            shift 2
            ;;
        -l|--list)
            list_backups
            ;;
        -v|--volume)
            VOLUME_NAME="$2"
            shift 2
            ;;
        -h|--help)
            usage
            ;;
        *)
            echo -e "${RED}Error: Unknown option: $1${NC}" >&2
            usage
            ;;
    esac
done

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo -e "${RED}Error: Docker is not running${NC}" >&2
    exit 1
fi

# Determine backup file to restore
if [ -z "$BACKUP_FILE" ]; then
    # Use latest backup
    LATEST_BACKUP=$(ls -t "${EXPORT_DIR}"/pg_data_backup_*.tar.gz 2>/dev/null | head -n1)

    if [ -z "$LATEST_BACKUP" ]; then
        echo -e "${RED}Error: No backup files found in $EXPORT_DIR${NC}" >&2
        echo -e "${YELLOW}Tip: Use --list to see available backups${NC}"
        exit 1
    fi

    BACKUP_FILE=$(basename "$LATEST_BACKUP")
    echo -e "${BLUE}No backup file specified, using latest: $BACKUP_FILE${NC}"
else
    # Check if file has path or just filename
    if [[ "$BACKUP_FILE" != *"/"* ]]; then
        # Just filename, prepend export dir
        BACKUP_FILE="${EXPORT_DIR}/${BACKUP_FILE}"
    fi
fi

# Verify backup file exists
if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}Error: Backup file not found: $BACKUP_FILE${NC}" >&2
    exit 1
fi

# Get backup file info
BACKUP_SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
BACKUP_NAME=$(basename "$BACKUP_FILE")

echo ""
echo -e "${YELLOW}⚠️  WARNING: This will REPLACE all data in volume: $VOLUME_NAME${NC}"
echo -e "${YELLOW}   Backup file: $BACKUP_NAME (${BACKUP_SIZE})${NC}"
echo ""

# Confirmation prompt
read -p "Are you sure you want to continue? (yes/no): " -r
echo
if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
    echo -e "${BLUE}Import cancelled${NC}"
    exit 0
fi

# Check if volume exists
VOLUME_EXISTS=false
if docker volume inspect "$VOLUME_NAME" > /dev/null 2>&1; then
    VOLUME_EXISTS=true
    echo -e "${YELLOW}Volume exists, backing up current data first...${NC}"

    # Create backup of existing volume
    SAFETY_BACKUP_DIR="${SCRIPT_DIR}/pg_export/safety_backups"
    mkdir -p "$SAFETY_BACKUP_DIR"
    SAFETY_BACKUP="safety_backup_$(date +%Y%m%d_%H%M%S).tar.gz"

    if docker run --rm \
        -v "${VOLUME_NAME}:/var/lib/postgresql/data:ro" \
        -v "${SAFETY_BACKUP_DIR}:/backup" \
        busybox tar czf "/backup/${SAFETY_BACKUP}" -C /var/lib/postgresql/data . 2>/dev/null; then
        echo -e "${GREEN}✓ Safety backup created: ${SAFETY_BACKUP}${NC}"
    else
        echo -e "${YELLOW}Warning: Could not create safety backup${NC}"
    fi
else
    echo -e "${BLUE}Creating new volume: $VOLUME_NAME${NC}"
    docker volume create "$VOLUME_NAME" > /dev/null
fi

# Stop any containers using this volume
CONTAINERS_USING_VOLUME=$(docker ps -q --filter volume="$VOLUME_NAME" 2>/dev/null || true)
STOPPED_CONTAINERS=()

if [ -n "$CONTAINERS_USING_VOLUME" ]; then
    echo -e "${YELLOW}Stopping containers using this volume...${NC}"
    for container in $CONTAINERS_USING_VOLUME; do
        CONTAINER_NAME=$(docker inspect --format='{{.Name}}' "$container" | sed 's/^\///')
        echo "  Stopping: $CONTAINER_NAME"
        docker stop "$container" > /dev/null
        STOPPED_CONTAINERS+=("$container")
    done
fi

# Import data
echo -e "${BLUE}Importing data from backup...${NC}"

# First, clear the volume
docker run --rm \
    -v "${VOLUME_NAME}:/var/lib/postgresql/data" \
    busybox sh -c "rm -rf /var/lib/postgresql/data/*" 2>/dev/null || true

# Then extract the backup
if docker run --rm \
    -v "$(dirname "$BACKUP_FILE"):/backup:ro" \
    -v "${VOLUME_NAME}:/var/lib/postgresql/data" \
    busybox tar xzf "/backup/$(basename "$BACKUP_FILE")" -C /var/lib/postgresql/data; then

    echo -e "${GREEN}✓ Data imported successfully${NC}"
    echo "  Volume: $VOLUME_NAME"
    echo "  From: $BACKUP_NAME"

    # Restart stopped containers
    if [ ${#STOPPED_CONTAINERS[@]} -gt 0 ]; then
        echo -e "${BLUE}Restarting containers...${NC}"
        for container in "${STOPPED_CONTAINERS[@]}"; do
            CONTAINER_NAME=$(docker inspect --format='{{.Name}}' "$container" | sed 's/^\///')
            echo "  Starting: $CONTAINER_NAME"
            docker start "$container" > /dev/null
        done
    fi

    echo ""
    echo -e "${GREEN}✓ Import completed successfully${NC}"
else
    echo -e "${RED}Error: Failed to import data${NC}" >&2

    # Try to restart containers anyway
    if [ ${#STOPPED_CONTAINERS[@]} -gt 0 ]; then
        echo -e "${YELLOW}Attempting to restart containers...${NC}"
        for container in "${STOPPED_CONTAINERS[@]}"; do
            docker start "$container" > /dev/null 2>&1 || true
        done
    fi

    exit 1
fi
