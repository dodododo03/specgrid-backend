#!/bin/bash
# Runs ONCE, on the MariaDB container's first start (empty ./data/mysql), as part of the official
# image's init. Same two-account setup as scripts/init_db.sql, but for Docker:
#   - accounts are '@%' because the app connects from another container (the DB port itself is
#     never published, so only containers on the compose network can reach it);
#   - passwords come from .env instead of being pasted into SQL.
# Tables are created by the app container (alembic upgrade head) right after; then run
# deploy/harden-db.sh once to narrow the app account to least privilege.
set -euo pipefail

for v in DB_NAME DB_USER DB_PASSWORD DB_MIGRATION_USER DB_MIGRATION_PASSWORD; do
  # Only [A-Za-z0-9_-] so the values can be placed inside SQL quotes safely
  # (python -c "import secrets;print(secrets.token_urlsafe(32))" generates exactly that).
  if ! [[ "${!v}" =~ ^[A-Za-z0-9_-]+$ ]]; then
    echo "01-accounts.sh: $v must contain only letters, digits, '_' or '-'" >&2
    exit 1
  fi
done

mariadb -uroot -p"${MARIADB_ROOT_PASSWORD}" <<SQL
CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Migration account (Alembic + maintenance scripts): schema changes + data.
CREATE USER IF NOT EXISTS '${DB_MIGRATION_USER}'@'%' IDENTIFIED BY '${DB_MIGRATION_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, DROP, INDEX, REFERENCES
  ON \`${DB_NAME}\`.* TO '${DB_MIGRATION_USER}'@'%';

-- Runtime account (web server): data only. Narrowed further by deploy/harden-db.sh.
CREATE USER IF NOT EXISTS '${DB_USER}'@'%' IDENTIFIED BY '${DB_PASSWORD}';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`${DB_NAME}\`.* TO '${DB_USER}'@'%';

FLUSH PRIVILEGES;
SQL
echo "01-accounts.sh: created database ${DB_NAME} and accounts ${DB_MIGRATION_USER}, ${DB_USER}"
