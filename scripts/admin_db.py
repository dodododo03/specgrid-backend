"""DB session for maintenance scripts (seed / log retention), using the migrator account from .env.

The running app's account (specgrid_app) is deliberately not allowed to read personal log columns or
to UPDATE/DELETE activity logs (scripts/harden_db_privileges.sql), so jobs that must do that use
this separate account, which the web server never holds.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import DB_CONNECT_ARGS, settings

admin_engine = create_engine(settings.migration_database_url, connect_args=DB_CONNECT_ARGS, pool_pre_ping=True)
AdminSession = sessionmaker(bind=admin_engine, autoflush=False, expire_on_commit=False)
