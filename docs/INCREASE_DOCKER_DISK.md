# Increase Docker Desktop Disk Size

## Current Status
- Docker VM Disk: 58.4GB (100% full)
- TimescaleDB using: ~55GB
- Available: 33.9MB (critically low)

## Option A: Increase via Docker Desktop GUI (Recommended)

1. **Open Docker Desktop**
   - Click the Docker icon in the menu bar
   - Select "Settings" or "Preferences"

2. **Navigate to Resources**
   - Click "Resources" in the left sidebar
   - Click "Advanced" (or "Disk" on newer versions)

3. **Increase Disk Image Size**
   - Find the "Virtual disk limit" slider
   - Current: ~60GB
   - **Increase to: 150GB** (or more if you plan to grow data significantly)

4. **Apply and Restart**
   - Click "Apply & Restart"
   - Wait for Docker to restart (~1-2 minutes)

5. **Verify the change**
   ```bash
   docker exec quant-vibe-timescaledb df -h /var/lib/postgresql/data
   ```

## Option B: Increase via CLI (Alternative)

If Docker Desktop GUI doesn't work, use the CLI:

1. **Stop all containers**
   ```bash
   docker-compose down
   ```

2. **Edit Docker settings file**
   ```bash
   # macOS location
   nano ~/Library/Group\ Containers/group.com.docker/settings.json
   ```

3. **Find and modify diskSizeMiB**
   ```json
   {
     "diskSizeMiB": 153600,  // Change from 61440 to 153600 (150GB)
     ...
   }
   ```

4. **Restart Docker Desktop**
   - Quit Docker Desktop completely
   - Reopen Docker Desktop
   - Wait for it to start

5. **Start containers**
   ```bash
   docker-compose up -d
   ```

## Option C: Create Bind Mount (Most Control)

If you want direct control over the database location:

1. **Stop containers**
   ```bash
   docker-compose down
   ```

2. **Create backup**
   ```bash
   mkdir -p ~/quant-vibe-backups
   docker run --rm \
     -v quant-vibe_timescaledb_data:/from \
     -v ~/quant-vibe-backups:/to \
     alpine sh -c "cd /from && tar czf /to/timescaledb-$(date +%Y%m%d).tar.gz ."
   ```

3. **Modify docker-compose.yml**
   ```yaml
   # Change from:
   volumes:
     - timescaledb_data:/var/lib/postgresql/data

   # To:
   volumes:
     - /Users/curisu/docker-data/timescaledb:/var/lib/postgresql/data
   ```

4. **Restore data**
   ```bash
   mkdir -p ~/docker-data/timescaledb
   cd ~/docker-data/timescaledb
   tar xzf ~/quant-vibe-backups/timescaledb-*.tar.gz
   ```

5. **Start containers**
   ```bash
   docker-compose up -d
   ```

## Verification Steps

After increasing disk space:

```bash
# Check Docker VM disk
docker exec quant-vibe-timescaledb df -h /var/lib/postgresql/data

# Check database size
PGPASSWORD=quantvibe_dev psql -h localhost -U quantvibe -d options_data -c "
SELECT
    pg_size_pretty(pg_database_size('options_data')) as database_size,
    pg_size_pretty(pg_total_relation_size('options_bars')) as options_bars_size;
"

# Check available space
docker system df
```

## Recommended: Clean Up After Migration

Once disk space is increased and the migration completes:

1. **Compress old chunks**
   ```sql
   SELECT compress_chunk(i, if_not_compressed => true)
   FROM show_chunks('options_bars', older_than => INTERVAL '7 days') i;
   ```

2. **Vacuum the database**
   ```sql
   VACUUM FULL ANALYZE options_bars;
   ```

3. **Check for unused data**
   ```bash
   docker system prune -a --volumes
   ```
