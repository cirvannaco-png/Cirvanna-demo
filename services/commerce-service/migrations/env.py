from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from app.main import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

migration_database_url = os.getenv("COMMERCE_MIGRATION_DATABASE_URL", "").strip()
runtime_database_url = os.getenv("COMMERCE_DATABASE_URL", "").strip()
is_production = os.getenv("COMMERCE_ENVIRONMENT", "").strip().lower() in {"production", "prod"}

if is_production:
    if not migration_database_url or not runtime_database_url:
        raise RuntimeError(
            "Production migrations require separate COMMERCE_MIGRATION_DATABASE_URL "
            "and COMMERCE_DATABASE_URL credentials"
        )
    try:
        migration_role = make_url(migration_database_url).username
        runtime_role = make_url(runtime_database_url).username
    except Exception as exc:
        raise RuntimeError("Production Commerce database URLs are invalid") from exc
    if not migration_role or not runtime_role or migration_role == runtime_role:
        raise RuntimeError(
            "Production Commerce migrations and runtime must use distinct database roles"
        )

database_url = (
    migration_database_url
    or runtime_database_url
    or config.get_main_option("sqlalchemy.url")
)
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
