#!/bin/sh
# PostgreSQL 备份策略：7 份日备份 + 4 份周备份 + 6 份月备份，gzip 压缩。
# 备份目录挂载在容器 /backups（宿主机 ./backups，独立于 pgdata volume）。
set -e

BACKUP_DIR=${BACKUP_DIR:-/backups}
PGHOST=${PGHOST:-postgres}
PGUSER=${PGUSER:-map}
PGDB=${PGDB:-map_platform}
KEEP_DAILY=${KEEP_DAILY:-7}
KEEP_WEEKLY=${KEEP_WEEKLY:-4}
KEEP_MONTHLY=${KEEP_MONTHLY:-6}

STAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly" "$BACKUP_DIR/monthly"

# 每日备份
pg_dump -h "$PGHOST" -U "$PGUSER" "$PGDB" | gzip > "$BACKUP_DIR/daily/backup_$STAMP.sql.gz"
echo "[backup] daily: $BACKUP_DIR/daily/backup_$STAMP.sql.gz"

# 周一保留为周备份（每周执行一次备份任务时触发）
DOW=$(date +%u)
if [ "$DOW" = "1" ]; then
  cp "$BACKUP_DIR/daily/backup_$STAMP.sql.gz" "$BACKUP_DIR/weekly/backup_week_$STAMP.sql.gz"
  echo "[backup] weekly saved"
fi

# 每月1日保留为月备份
DOM=$(date +%d)
if [ "$DOM" = "01" ]; then
  cp "$BACKUP_DIR/daily/backup_$STAMP.sql.gz" "$BACKUP_DIR/monthly/backup_month_$STAMP.sql.gz"
  echo "[backup] monthly saved"
fi

# 清理过期备份
ls -1t "$BACKUP_DIR/daily"/*.sql.gz 2>/dev/null | tail -n +$((KEEP_DAILY + 1)) | xargs -r rm -f
ls -1t "$BACKUP_DIR/weekly"/*.sql.gz 2>/dev/null | tail -n +$((KEEP_WEEKLY + 1)) | xargs -r rm -f
ls -1t "$BACKUP_DIR/monthly"/*.sql.gz 2>/dev/null | tail -n +$((KEEP_MONTHLY + 1)) | xargs -r rm -f

echo "[backup] done"