#!/bin/bash
# Daily backup: DB dump + uploaded photos, kept for KEEP_DAYS days in ./backups.
#
#   ./deploy/backup.sh                 (cron runs it at 03:30, see deploy/crontab.example)
#
# Restore a dump:
#   gunzip -c backups/db-YYYYmmdd-HHMM.sql.gz | docker compose exec -T db mariadb -uroot -p"<root pw>"
# Restore photos:
#   tar -xzf backups/media-YYYYmmdd-HHMM.tar.gz -C data/
#
# A backup on the same disk doesn't survive losing the server: copy ./backups elsewhere now and
# then (scp to your PC, or S3 later).
set -euo pipefail
cd "$(dirname "$0")/.."
. deploy/lib.sh

KEEP_DAYS="${KEEP_DAYS:-14}"
stamp=$(date +%Y%m%d-%H%M)
mkdir -p backups
chmod 700 backups
umask 077   # dumps contain personal data: owner-only

db_name=$(env_get DB_NAME specgrid)
# --single-transaction: consistent snapshot without locking the site while dumping.
docker compose exec -T db mariadb-dump -uroot -p"$(env_get MARIADB_ROOT_PASSWORD)" \
  --single-transaction --routines --triggers --databases "$db_name" \
  | gzip > "backups/db-$stamp.sql.gz.part"
mv "backups/db-$stamp.sql.gz.part" "backups/db-$stamp.sql.gz"   # never leave a half-written file named like a good one

tar -czf "backups/media-$stamp.tar.gz" -C data media

find backups -name 'db-*.sql.gz' -mtime +"$KEEP_DAYS" -delete
find backups -name 'media-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
find backups -name '*.part' -mtime +1 -delete

echo "$(date '+%F %T') backup ok: db-$stamp.sql.gz ($(du -h "backups/db-$stamp.sql.gz" | cut -f1)), media-$stamp.tar.gz"
