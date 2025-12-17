# PostgreSQL Volume Backup & Restore Scripts

Scripts for backing up and restoring PostgreSQL data from Docker volumes.

## Scripts

### `export_pg_volume.sh` - Export/Backup Script

Exports PostgreSQL data from a Docker volume to a compressed tar archive.

**Features:**
- ✅ Timestamped backups (prevents overwriting)
- ✅ Read-only volume mount (safe)
- ✅ Automatic cleanup (keeps last 5 backups)
- ✅ Pre-flight checks (Docker running, volume exists)
- ✅ Colored output and progress feedback
- ✅ Backup verification

**Usage:**
```bash
./export_pg_volume.sh
```

**Output:**
```
Exporting PostgreSQL data from volume: quant-vibe_timescaledb_data
Backup file: pg_data_backup_20251216_143045.tar.gz
✓ PostgreSQL data exported successfully
  Location: /path/to/docker/pg_export/pg_data_backup_20251216_143045.tar.gz
  Size: 256M
Cleaning up old backups (keeping last 5)...
Export completed.
```

---

### `import_pg_volume.sh` - Import/Restore Script

Imports PostgreSQL data from a backup archive to a Docker volume.

**Features:**
- ✅ Interactive confirmation (prevents accidents)
- ✅ Automatic safety backup before restore
- ✅ Stops/restarts containers using the volume
- ✅ Lists available backups
- ✅ Auto-selects latest backup if none specified
- ✅ Full error handling and rollback support

**Usage:**

```bash
# List available backups
./import_pg_volume.sh --list

# Restore latest backup (interactive confirmation)
./import_pg_volume.sh

# Restore specific backup
./import_pg_volume.sh --file pg_data_backup_20251216_143045.tar.gz

# Restore to different volume
./import_pg_volume.sh --volume my_custom_volume
```

**Options:**
- `-f, --file BACKUP_FILE` - Specify backup file to restore
- `-l, --list` - List available backups
- `-v, --volume VOLUME_NAME` - Target volume name
- `-h, --help` - Show help message

**Example Output:**

```bash
$ ./import_pg_volume.sh --list
Available backups in /path/to/docker/pg_export:

  [LATEST] pg_data_backup_20251216_153045.tar.gz (256M, created: 2025-12-16 15:30:45)
           pg_data_backup_20251216_143045.tar.gz (254M, created: 2025-12-16 14:30:45)
           pg_data_backup_20251216_133045.tar.gz (252M, created: 2025-12-16 13:30:45)
```

```bash
$ ./import_pg_volume.sh

⚠️  WARNING: This will REPLACE all data in volume: quant-vibe_timescaledb_data
   Backup file: pg_data_backup_20251216_143045.tar.gz (256M)

Are you sure you want to continue? (yes/no): yes
Volume exists, backing up current data first...
✓ Safety backup created: safety_backup_20251216_154500.tar.gz
Stopping containers using this volume...
  Stopping: quant-vibe-timescaledb-1
Importing data from backup...
✓ Data imported successfully
  Volume: quant-vibe_timescaledb_data
  From: pg_data_backup_20251216_143045.tar.gz
Restarting containers...
  Starting: quant-vibe-timescaledb-1

✓ Import completed successfully
```

---

## Safety Features

### Export Script
1. **Read-only mount** - Source volume mounted as `:ro` to prevent accidents
2. **Backup verification** - Checks file exists and reports size
3. **Automatic cleanup** - Removes old backups (keeps last 5)
4. **Error handling** - Exits on any error with clear messages

### Import Script
1. **Safety backup** - Creates backup of existing data before import
2. **Interactive confirmation** - Requires "yes" to proceed
3. **Container management** - Automatically stops/restarts affected containers
4. **Volume validation** - Checks volume exists (creates if needed)
5. **Rollback support** - Safety backup stored in `pg_export/safety_backups/`

---

## Directory Structure

```
docker/
├── export_pg_volume.sh          # Export/backup script
├── import_pg_volume.sh          # Import/restore script
├── pg_export/                   # Backup storage
│   ├── pg_data_backup_20251216_143045.tar.gz
│   ├── pg_data_backup_20251216_133045.tar.gz
│   └── safety_backups/          # Safety backups created during import
│       └── safety_backup_20251216_154500.tar.gz
└── README_BACKUP.md             # This file
```

---

## Common Workflows

### Daily Backup
```bash
# Add to crontab for daily backups at 2 AM
0 2 * * * /path/to/docker/export_pg_volume.sh >> /var/log/pg_backup.log 2>&1
```

### Disaster Recovery
```bash
# 1. List available backups
./import_pg_volume.sh --list

# 2. Restore from specific backup
./import_pg_volume.sh --file pg_data_backup_20251215_020000.tar.gz
```

### Migration to New Server
```bash
# On old server:
./export_pg_volume.sh

# Copy backup file to new server
scp docker/pg_export/pg_data_backup_*.tar.gz newserver:/path/to/docker/pg_export/

# On new server:
./import_pg_volume.sh
```

### Testing/Development
```bash
# Create test volume with production data
./import_pg_volume.sh --volume test_timescaledb_data
```

---

## Troubleshooting

### "Docker is not running"
```bash
# Start Docker
sudo systemctl start docker  # Linux
# or open Docker Desktop      # macOS/Windows
```

### "Volume does not exist"
```bash
# List volumes
docker volume ls

# Check volume name in docker-compose.yml
grep volumes docker-compose.yml
```

### "Permission denied"
```bash
# Make scripts executable
chmod +x docker/export_pg_volume.sh
chmod +x docker/import_pg_volume.sh
```

### Import fails
```bash
# Check safety backup was created
ls -lh docker/pg_export/safety_backups/

# Restore from safety backup if needed
./import_pg_volume.sh --file safety_backups/safety_backup_YYYYMMDD_HHMMSS.tar.gz
```

---

## Configuration

Edit these variables at the top of each script to customize:

```bash
# In both scripts
VOLUME_NAME="quant-vibe_timescaledb_data"  # Change to match your volume name
EXPORT_DIR="${SCRIPT_DIR}/pg_export"        # Backup storage location
```

---

## Requirements

- Docker installed and running
- Bash shell (Linux/macOS)
- Sufficient disk space for backups
- No containers actively writing to volume during backup (recommended)

---

## Best Practices

1. **Regular backups**: Run export script daily or before major changes
2. **Test restores**: Periodically test import script to verify backups work
3. **Monitor disk space**: Cleanup keeps last 5, but monitor `pg_export/` size
4. **Stop containers first**: For cleanest backups, stop containers before export
5. **Safety backups**: Keep the safety backups created during imports
6. **Off-site storage**: Copy important backups to remote storage

---

## Security Notes

- ⚠️ Backup files contain **unencrypted** database data
- ⚠️ Protect `pg_export/` directory with appropriate permissions
- ⚠️ Consider encrypting backups for off-site storage
- ⚠️ Review and rotate safety backups regularly

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review script output for specific error messages
3. Verify Docker and volume status: `docker volume ls`
4. Check Docker logs: `docker logs <container_name>`
