#!/usr/bin/env bash
# scripts/backup.sh - Enterprise backup: daily/weekly/restore/verify/status
# Usage: ./scripts/backup.sh [daily|weekly|restore <file>|verify|status]
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/opt/backups/galaxyvast}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/galaxyvast/docker-compose.prod.yml}"
RETAIN_DAILY="${RETAIN_DAILY:-7}"
RETAIN_WEEKLY="${RETAIN_WEEKLY:-4}"
S3_BUCKET="${S3_BUCKET:-}"
DATE=$(date +%Y%m%d_%H%M%S)
WEEK=$(date +%Y_W%V)
LOG_FILE="${BACKUP_DIR}/backup.log"
TIMESTAMP_FILE="${BACKUP_DIR}/.last_backup"

mkdir -p "${BACKUP_DIR}/daily" "${BACKUP_DIR}/weekly" \
         "${BACKUP_DIR}/redis" "${BACKUP_DIR}/restore"

log()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] INFO  $*" | tee -a "${LOG_FILE}"; }
warn() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] WARN  $*" | tee -a "${LOG_FILE}"; }
err()  { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] ERROR $*" | tee -a "${LOG_FILE}"; }

notify_telegram() {
  local msg="$1"
  if [[ -n "${TELEGRAM_BOT_TOKEN:-}" && -n "${TELEGRAM_ADMIN_CHAT_ID:-}" ]]; then
    curl -s --max-time 5 \
      "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      -d "chat_id=${TELEGRAM_ADMIN_CHAT_ID}&text=${msg}" > /dev/null || true
  fi
}

backup_redis() {
  log "Starting Redis backup..."
  local REDIS_CONTAINER
  REDIS_CONTAINER=$(docker compose -f "${COMPOSE_FILE}" ps -q redis 2>/dev/null || echo "")
  if [[ -z "${REDIS_CONTAINER}" ]]; then
    err "Redis container not found"
    return 1
  fi
  docker compose -f "${COMPOSE_FILE}" exec -T redis \
    redis-cli -a "${REDIS_PASSWORD:-}" BGSAVE 2>/dev/null || true
  sleep 3
  local RDB_PATH="${BACKUP_DIR}/redis/redis_${DATE}.rdb"
  docker cp "${REDIS_CONTAINER}:/data/dump.rdb" "${RDB_PATH}" 2>/dev/null || {
    warn "Could not copy dump.rdb directly"
    docker compose -f "${COMPOSE_FILE}" exec -T redis \
      redis-cli -a "${REDIS_PASSWORD:-}" --rdb "/data/dump_${DATE}.rdb" 2>/dev/null || true
    docker cp "${REDIS_CONTAINER}:/data/dump_${DATE}.rdb" "${RDB_PATH}" 2>/dev/null || true
  }
  if [[ -f "${RDB_PATH}" ]]; then
    gzip -f "${RDB_PATH}"
    local SIZE; SIZE=$(du -sh "${RDB_PATH}.gz" | cut -f1)
    log "Redis backup done: redis_${DATE}.rdb.gz (${SIZE})"
    verify_file "${RDB_PATH}.gz"
  else
    err "Redis backup file not found"
    return 1
  fi
}

backup_app() {
  log "Backing up app state..."
  local ARCHIVE="${BACKUP_DIR}/daily/app_${DATE}.tar.gz"
  tar -czf "${ARCHIVE}" --ignore-failed-read \
    /opt/galaxyvast/logs/ /opt/galaxyvast/models/ 2>/dev/null || true
  if [[ -f "${ARCHIVE}" ]]; then
    local SIZE; SIZE=$(du -sh "${ARCHIVE}" | cut -f1)
    log "App backup done: app_${DATE}.tar.gz (${SIZE})"
    verify_file "${ARCHIVE}"
  else
    warn "App backup created empty archive"
  fi
}

verify_file() {
  local FILE="$1"
  [[ ! -f "${FILE}" ]] && { err "Verify: ${FILE} not found"; return 1; }
  local SIZE; SIZE=$(stat -c%s "${FILE}" 2>/dev/null || stat -f%z "${FILE}")
  [[ "${SIZE}" -lt 64 ]] && { err "Verify: ${FILE} too small (${SIZE} bytes)"; return 1; }
  if [[ "${FILE}" == *.gz ]]; then
    gzip -t "${FILE}" 2>/dev/null || { err "Verify: ${FILE} corrupt"; return 1; }
  fi
  log "Verify OK: ${FILE} (${SIZE} bytes)"
}

upload_s3() {
  [[ -z "${S3_BUCKET}" ]] && return 0
  command -v aws &>/dev/null || { warn "aws CLI not found"; return 0; }
  log "Uploading to S3: ${S3_BUCKET}..."
  aws s3 sync "${BACKUP_DIR}/daily/" "${S3_BUCKET}/daily/" \
    --exclude "*" --include "app_${DATE}*" --storage-class STANDARD_IA 2>&1 | tee -a "${LOG_FILE}" || true
  aws s3 sync "${BACKUP_DIR}/redis/" "${S3_BUCKET}/redis/" \
    --exclude "*" --include "redis_${DATE}*" --storage-class STANDARD_IA 2>&1 | tee -a "${LOG_FILE}" || true
  log "S3 upload done"
}

cleanup() {
  log "Cleaning old backups..."
  find "${BACKUP_DIR}/daily"  -name "*.tar.gz" -mtime "+${RETAIN_DAILY}"            -delete 2>/dev/null || true
  find "${BACKUP_DIR}/weekly" -name "*.tar.gz" -mtime "+$(( RETAIN_WEEKLY * 7 ))"  -delete 2>/dev/null || true
  find "${BACKUP_DIR}/redis"  -name "*.rdb.gz" -mtime "+${RETAIN_DAILY}"            -delete 2>/dev/null || true
  if [[ -f "${LOG_FILE}" ]] && [[ $(stat -c%s "${LOG_FILE}" 2>/dev/null || echo 0) -gt 10485760 ]]; then
    tail -n 5000 "${LOG_FILE}" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "${LOG_FILE}"
    log "Log file trimmed"
  fi
  log "Cleanup done"
}

promote_weekly() {
  local DOW; DOW=$(date +%u)
  if [[ "${DOW}" == "7" ]]; then
    local SRC="${BACKUP_DIR}/daily/app_${DATE}.tar.gz"
    local DST="${BACKUP_DIR}/weekly/app_${WEEK}.tar.gz"
    [[ -f "${SRC}" ]] && cp "${SRC}" "${DST}" && log "Promoted to weekly: app_${WEEK}.tar.gz"
  fi
}

restore() {
  local FILE="${1:-}"
  [[ -z "${FILE}" ]] && { err "Usage: $0 restore <file>"; exit 1; }
  [[ ! -f "${FILE}" ]] && { err "File not found: ${FILE}"; exit 1; }
  verify_file "${FILE}" || { err "Restore aborted: corrupt file"; exit 1; }
  log "Restoring from: ${FILE}"
  if [[ "${FILE}" == *.rdb.gz ]]; then
    gunzip -c "${FILE}" > "${BACKUP_DIR}/restore/dump.rdb"
    log "Redis RDB extracted. Manual steps:"
    log "  docker compose -f ${COMPOSE_FILE} stop redis"
    log "  docker cp ${BACKUP_DIR}/restore/dump.rdb \$(docker compose -f ${COMPOSE_FILE} ps -q redis):/data/dump.rdb"
    log "  docker compose -f ${COMPOSE_FILE} start redis"
  elif [[ "${FILE}" == *.tar.gz ]]; then
    tar -xzf "${FILE}" -C "${BACKUP_DIR}/restore/" 2>&1 | tee -a "${LOG_FILE}"
    log "App state restored to ${BACKUP_DIR}/restore/"
  else
    err "Unknown format: ${FILE}"; exit 1
  fi
  log "Restore complete"
}

status() {
  echo "=== GalaxyVast Backup Status ==="
  echo "Backup dir : ${BACKUP_DIR}"
  echo "Last backup: $(cat "${TIMESTAMP_FILE}" 2>/dev/null || echo 'never')"
  echo ""; echo "Daily:"; ls -lhtr "${BACKUP_DIR}/daily/"  2>/dev/null | tail -5 || echo "  (none)"
  echo ""; echo "Weekly:"; ls -lhtr "${BACKUP_DIR}/weekly/" 2>/dev/null | tail -4 || echo "  (none)"
  echo ""; echo "Redis:"; ls -lhtr "${BACKUP_DIR}/redis/"  2>/dev/null | tail -5 || echo "  (none)"
  echo ""; echo "Disk: $(du -sh "${BACKUP_DIR}" 2>/dev/null | cut -f1)"
}

CMD="${1:-daily}"
case "${CMD}" in
  daily)
    log "=== Daily backup started ==="
    backup_redis  || warn "Redis backup failed"
    backup_app    || warn "App backup failed"
    promote_weekly
    upload_s3     || warn "S3 upload failed"
    cleanup
    date -u +%Y-%m-%dT%H:%M:%SZ > "${TIMESTAMP_FILE}"
    notify_telegram "\u2705 GalaxyVast backup OK: ${DATE}"
    log "=== Daily backup finished ==="
    ;;
  weekly)
    log "=== Weekly backup started ==="
    backup_redis  || warn "Redis backup failed"
    backup_app    || warn "App backup failed"
    [[ -f "${BACKUP_DIR}/daily/app_${DATE}.tar.gz" ]] && \
      cp "${BACKUP_DIR}/daily/app_${DATE}.tar.gz" "${BACKUP_DIR}/weekly/app_${WEEK}.tar.gz"
    upload_s3     || warn "S3 upload failed"
    cleanup
    log "=== Weekly backup finished ==="
    ;;
  restore) restore "${2:-}" ;;
  verify)
    log "Verifying backups..."
    find "${BACKUP_DIR}" -name "*.gz" -newer "${TIMESTAMP_FILE:-/dev/null}" \
      -exec bash -c 'gzip -t "$1" && echo "OK: $1" || echo "CORRUPT: $1"' _ {} \;
    ;;
  status) status ;;
  *) echo "Usage: $0 [daily|weekly|restore <file>|verify|status]"; exit 1 ;;
esac
