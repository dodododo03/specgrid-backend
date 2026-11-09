-- SpecGrid: one-time database + account bootstrap. Run as MariaDB root (or another admin).
--   mariadb -u root -p -P 3307 < scripts/init_db.sql
-- Replace both passwords first (they must match .env). Never commit real passwords.
-- Tables are NOT created here: run `alembic upgrade head` afterwards.

CREATE DATABASE specgrid
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

-- Migration account (Alembic only): schema changes + alembic_version bookkeeping.
CREATE USER 'specgrid_migrator'@'localhost' IDENTIFIED BY '__MIGRATOR_PASSWORD__';
GRANT SELECT, INSERT, UPDATE, DELETE,
      CREATE, ALTER, DROP, INDEX, REFERENCES
  ON specgrid.* TO 'specgrid_migrator'@'localhost';

-- Runtime account (FastAPI): data only, cannot change or drop tables.
CREATE USER 'specgrid_app'@'localhost' IDENTIFIED BY '__APP_PASSWORD__';
GRANT SELECT, INSERT, UPDATE, DELETE
  ON specgrid.* TO 'specgrid_app'@'localhost';

FLUSH PRIVILEGES;
