#!/bin/bash
# Apply scripts/harden_db_privileges.sql to the Docker MariaDB, then prove it with
# scripts/check_db_security.py (exits non-zero if any check fails).
#
#   ./deploy/harden-db.sh
#
# Run once after the first `docker compose up`, and again whenever a migration adds a table
# (add the table to scripts/harden_db_privileges.sql first).
# The SQL file is written for a local install ('specgrid_app'@'localhost'); in Docker the account
# is 'specgrid_app'@'%' (see deploy/mariadb/init/01-accounts.sh), so the host part is rewritten.
set -euo pipefail
cd "$(dirname "$0")/.."

. deploy/lib.sh
if [ "$(env_get DB_NAME specgrid)" != "specgrid" ] || [ "$(env_get DB_USER specgrid_app)" != "specgrid_app" ]; then
  echo "harden-db.sh: scripts/harden_db_privileges.sql assumes DB_NAME=specgrid, DB_USER=specgrid_app" >&2
  exit 1
fi

echo "== applying least-privilege grants"
sed "s/'@'localhost'/'@'%'/g" scripts/harden_db_privileges.sql \
  | docker compose exec -T db mariadb -uroot -p"$(env_get MARIADB_ROOT_PASSWORD)" --force
# --force: the final REVOKE errors harmlessly ("no such grant") when this already ran once.

echo
echo "== verifying with the app account"
docker compose exec -T app python -m scripts.check_db_security
