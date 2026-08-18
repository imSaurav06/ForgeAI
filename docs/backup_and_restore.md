# Operational Backup and Restore Strategy

This guide documents the procedures for backup and restoration of persistent datastores and workspace volumes in the ForgeAI platform.

---

## 1. MongoDB Database Backup & Restore

### Backup Procedure
To perform a full snapshot backup of MongoDB (`forge_ai_db`):
```bash
docker exec -t forge_mongodb mongodump --db forge_ai_db --out /data/db/backup_$(date +%Y%m%d_%H%M%S)
```

### Restoration Procedure
To restore MongoDB from a backup directory:
```bash
docker exec -t forge_mongodb mongorestore --db forge_ai_db /data/db/backup_YYYYMMDD_HHMMSS/forge_ai_db
```

---

## 2. Qdrant Vector Database Backup & Restore

### Backup Procedure
To create a collection snapshot of `forge_ai_code` via Qdrant REST API:
```bash
curl -X POST "http://localhost:6333/collections/forge_ai_code/snapshots"
```
Snapshots are persisted in the named Docker volume `qdrant_data`.

### Restoration Procedure
To restore Qdrant vector collection from snapshot:
```bash
curl -X POST "http://localhost:6333/collections/forge_ai_code/snapshots/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "snapshot=@snapshot-forge_ai_code-YYYY-MM-DD.snapshot"
```

---

## 3. Workspace Volume Backup & Restore

### Backup Procedure
To create a tar archive of the workspace volume:
```bash
docker run --rm \
  --volumes-from forge_tools \
  -v $(pwd)/backups:/backup \
  alpine tar czf /backup/workspace_backup_$(date +%Y%m%d).tar.gz /app/workspace
```

### Restoration Procedure
To restore the workspace volume from an archive:
```bash
docker run --rm \
  --volumes-from forge_tools \
  -v $(pwd)/backups:/backup \
  alpine tar xzf /backup/workspace_backup_YYYYMMDD.tar.gz -C /
```
