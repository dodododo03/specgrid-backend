from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import DB_CONNECT_ARGS, settings
from app.models import Base  # noqa: F401  (imports every model -> complete metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Migrations run with the DDL-capable account from .env, never from alembic.ini.
DATABASE_URL = settings.migration_database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout (`alembic upgrade head --sql`) without a DB connection."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool, connect_args=DB_CONNECT_ARGS)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
