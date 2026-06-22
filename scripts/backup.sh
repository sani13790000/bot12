#!/usr/bin/env bash
# scripts/backup.sh - DO-8: Backup strategy
# Usage: ./scripts/backup.sh [daily|weekly|restore <file>]
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/backups/galaxyvast}"
RETAIN_DAILY=7
RETAIN_WEEKLY=4
DATE=$(date +%Y%m%d_%H%M%S)
WEEK=$(date +%Y_W%V)
LOG_FILE="${BACKUP_DIR}/backup.log"

mkdir -p "${BACKUP_DIR}/daily" "${BACKUP_DIR}/weekly" "${BACKUP_DIR}/redis"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "${LOG_FILE}"; }

backup_redis() {
  log "Starting Redis backup..."
  docker compose -f /opt/galaxyvast/docker-compose.prod.yml exec -T redis \
    redis-cli -a "${REDIS_PASSWORD}" --rdb "/data/dump_${DATE}.rdb" 2>/dev/null || true
  docker cp "$(docker compose -f /opt/galaxyvast/docker-compose.prod.yml ps -q redis):/data/dump_${DATE}.rdb" \
    "${BACKUP_DIR}/redis/redis_${DATE}.rdb" 2>/dev/null || true
  gzip -f "${BACKUP_DIR}/redis/redis_${DATE}.rdb" || true
  log "Redis backup: redis_${DATE}.rdb.gz"
}

backup_app() {
  log "Backing up app state..."
  tar -czf "${BACKUP_DIR}/daily/app_${DATE}.tar.gz" \
    /opt/galaxyvast/logs/ /opt/galaxyvast/models/ 2>/dev/null || true
  log "App backup: app_${DATE}.tar.gz"
}

cleanup() {
  log "Cleaning old backups..."
  find "${BACKUP_DIR}/daily"  -name "*.tar.gz" -mtime +${RETAIN_DAILY}  -delete
  find "${BACKUP_DIR}/weekly" -name "*.tar.gz" -mtime +$((RETAIN_WEEKLY * 7)) -delete
  find "${BACKUP_DIR}/redis"  -name "*.rdb.gz" -mtime +${RETAIN_DAILY}  -delete
  log "Cleanup done."
}

promote_weekly() {
  local DOW=$(date +%u)
  if [ "${DOW}" == "7" ]; then
    cp "${BACKUP_DIR}/daily/app_${DATE}.tar.gz" \
       "${BACKUP_DIR}/weekly/app_${WEEK}.tar.gz" 2>/dev/null || true
    log "Promoted to weekly: app_${WEEK}.tar.gz"
  fi
}

restore_redis() {
  local FILE="${1:?Usage: $0 restore <redis_backup.rdb.gz>}"
  log "Restoring Redis from ${FILE}..."
  gunzip -c "${FILE}" > /tmp/dump.rdb
  docker compose -f /opt/galaxyvast/docker-compose.prod.yml stop redis
  docker cp /tmp/dump.rdb \
    "$(docker compose -f /opt/galaxyvast/docker-compose.prod.yml ps -q redis):/data/dump.rdb"
  docker compose -f /opt/galaxyvast/docker-compose.prod.yml start redis
  log "Restore complete."
}

case "${1:-daily}" in
  daily)
    backup_redis; backup_app; promote_weekly; cleanup
    log "Daily backup complete."
    ;;
  weekly)
    backup_redis; backup_app; cleanup
    log "Weekly backup complete."
    ;;
  restore)
    restore_redis "${2:-}"
    ;;
  *)
    echo "Usage: $0 [daily|weekly|restore <file>]"
    exit 1
    ;;
esac
