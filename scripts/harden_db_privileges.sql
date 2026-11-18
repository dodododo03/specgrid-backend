-- SpecGrid: least-privilege grants for the runtime account. Run as MariaDB root AFTER `alembic upgrade head`:
--   mariadb -u root -p -h 127.0.0.1 -P 3307 -e "source scripts/harden_db_privileges.sql"
-- Re-run whenever a migration adds a table (and add the table below), then check with:
--   python -m scripts.check_db_security
--
-- Why: specgrid_app (FastAPI) used to have SELECT/INSERT/UPDATE/DELETE on every table, so a bug,
-- SQL injection or a stolen app password could read who viewed/searched what from which IP, or
-- quietly edit/erase that history. After this script the app account:
--   * user_activity_logs : INSERT only (append-only) + SELECT on the 5 columns the rankings need.
--                          It can NOT read user_id / session_id / ip_address / user_agent / detail,
--                          and can NOT UPDATE or DELETE log rows.
--   * alembic_version    : no access at all.
--   * other tables       : SELECT/INSERT/UPDATE/DELETE as before (the service needs them).
-- Log retention/cleanup runs with the separate specgrid_migrator account (scripts/purge_activity_logs.py).
-- Test DBs (specgrid_test, specgrid_e2e) keep their broad grants: the tests inspect log rows directly.

GRANT SELECT, INSERT, UPDATE, DELETE ON specgrid.users          TO 'specgrid_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON specgrid.products       TO 'specgrid_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON specgrid.product_specs  TO 'specgrid_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON specgrid.product_images TO 'specgrid_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON specgrid.chat_rooms     TO 'specgrid_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON specgrid.chat_messages  TO 'specgrid_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON specgrid.trades         TO 'specgrid_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE ON specgrid.favorites      TO 'specgrid_app'@'localhost';

GRANT INSERT ON specgrid.user_activity_logs TO 'specgrid_app'@'localhost';
GRANT SELECT (id, activity_type, created_at, search_keyword, product_id)
  ON specgrid.user_activity_logs TO 'specgrid_app'@'localhost';

-- Drop the old database-wide grant last, so the app never loses access mid-way.
-- (Fails harmlessly with "There is no such grant" if this script already ran.)
REVOKE SELECT, INSERT, UPDATE, DELETE ON specgrid.* FROM 'specgrid_app'@'localhost';

FLUSH PRIVILEGES;
SHOW GRANTS FOR 'specgrid_app'@'localhost';
